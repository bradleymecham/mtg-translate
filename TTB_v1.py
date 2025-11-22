import os
from google.cloud import speech, translate_v2 as translate
import json
import pyaudio
import asyncio
import concurrent.futures
import websockets
import time
import queue
import aioconsole
import configparser
import sys
import struct

import psutil
import socket
import ipaddress

# These are for running a local http service
from aiohttp import web
import aiofiles

# These are for mDNS, so we can call this
# server 'captions.local' temporarily
from zeroconf import ServiceInfo
from zeroconf.asyncio import AsyncZeroconf

# Multi-language definitions for the server logic
LANGUAGE_MAP = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "sw": "Swahili",
    "ja": "Japanese",
    "zh-CN": "Chinese (PRC)"
    # Add future language codes here
}

# --- CONFIGURATION ---
config = configparser.ConfigParser()
config.read('config.ini')

google_credentials_json = config['AUTHENTICATION']['google_credentials_json']

# Read num_channels with a safe default
try:
    CONFIGURED_CHANNELS = int(config['AUDIO']['num_channels'])
except (KeyError, ValueError):
    # Default to 1 channel
    CONFIGURED_CHANNELS = 1

# Read the comma-separated string from the config
try:
    language_codes_string = config['TRANSLATION']['target_language_codes']

    codes_list = [code.strip() for code in language_codes_string.split(',')]

    TARGET_LANGUAGES = {}
    for code in codes_list:
        # Look up the code in the master map
        if code in LANGUAGE_MAP:
            TARGET_LANGUAGES[code] = LANGUAGE_MAP[code]
        else:
            print(f"Warning: Language code {code} in config.ini is invalid and skipped.")

except (KeyError, ValueError):
    # Fallback to a safe default if the config entry is missing or invalid
    print("Error: Valid 'target_language_codes' not found in config.ini. Defaulting to English.")
    TARGET_LANGUAGES = {"en": "English"}

# --- END CONFIGURATION ---

# Google Cloud clients
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = google_credentials_json
speech_client = speech.SpeechClient()
translate_client = translate.Client()

# Queues for inter-thread communication (the stable architecture)
audio_queue = queue.Queue()
translation_request_queue = queue.Queue() # Sync queue for English text awaiting translation

# WebSocket clients
clients = set()

# For elegant program exit
stop_event = asyncio.Event()

# --- UTILITY FUNCTIONS ---

def get_interface_type(interface_name):
    name = interface_name.lower()
    if "wi-fi" in name or "wlan" in name or "wifi" in name:
        return "Wi-Fi"
    elif "eth" in name or "en" in name:
        return "Ethernet"
    else:
        return "Unknown"

def get_ip_addresses():
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    result = []
    for interface, addr_list in addrs.items():
        if not stats.get(interface) or not stats[interface].isup:
            continue
        for addr in addr_list:
            if addr.family == socket.AF_INET:
                ip = addr.address
                ip_obj = ipaddress.ip_address(ip)
                if ip_obj.is_loopback or ip_obj.is_link_local:
                    continue
                interface_type = get_interface_type(interface)
                result.append((interface, interface_type, ip))
    return result

# HTTP Server Handler
async def http_handler(request):
    # Serve the HTML client file
    try:
        async with aiofiles.open('TranslationClient.html', mode='r') as f:
            html_content = await f.read()
        return web.Response(text=html_content, content_type='text/html')
    except FileNotFoundError:
        return web.Response(text="TranslationClient.html not found", status=404)

# --- ASYNC HANDLERS ---

async def wait_for_keypress():
    print("Press 'q' to quit.")
    while not stop_event.is_set():
        try:
            key = await aioconsole.ainput()
            if key.strip().lower() == 'q':
                stop_event.set()
                break
            elif key.strip().lower() == 'nt':
                translation_request_queue.put("New Talk")
        except Exception as e:
            print(f"Error reading input: {e}")

async def handler(websocket):
    print(f"Client connected: {websocket.remote_address}")
    clients.add(websocket)
    try:
        async for message in websocket:
            pass
    finally:
        print(f"Client disconnected: {websocket.remote_address}")
        clients.remove(websocket)

async def broadcast_message(message):
    """Sends the JSON payload string to all connected clients."""
    if clients:
        # Note: 'message' is already the final JSON string, so we send it directly
        await asyncio.wait([asyncio.create_task(client.send(message)) for client in clients])
    else:
        pass 

# --- SYNCHRONOUS (THREAD) FUNCTIONS ---

def audio_stream(loop):
    global audio_queue
    audio = pyaudio.PyAudio()
    stream = None

    FORMAT = pyaudio.paInt16
    CHANNELS = CONFIGURED_CHANNELS
    RATE = 16000
    CHUNK = 1024


    try:
        stream = audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE, 
            input=True, 
            frames_per_buffer=CHUNK)

        while not stop_event.is_set():
            try:
                audio_chunk = stream.read(1024, exception_on_overflow=False)

                mono_chunk = audio_chunk

                if CHANNELS == 2:
                    # Unpack the stereo data (2* CHUNK 16-bit shorts)
                    data = struct.unpack('<' + str(2*CHUNK) + 'h', audio_chunk)

                    # Extract only the right channel (every other sample, starting at 1)
                    right_channel_data = data[1::2]
                    
                    # Repack the mono data back into a byte string
                    mono_chunk = struct.pack('<' + str(CHUNK) + 'h', *right_channel_data)

                # Send the resulting mono or isolated-right chunk to transcription
                loop.call_soon_threadsafe(audio_queue.put_nowait, mono_chunk)
            except IOError as e:
                print(f"IO Error: {e}")
    except Exception as e:
        print(f"Buffer overflow: {e}")
    finally:
        if stream:
            stream.stop_stream()
            stream.close()
        audio.terminate()

def transcribe_loop(loop):
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code="en-US"
    )

    streaming_config = speech.StreamingRecognitionConfig(
        config=config,
        interim_results=True
    )

    while not stop_event.is_set():
        start_time = time.time()

        def audio_requests_generator():
            try:
                first_audio_chunk = audio_queue.get(timeout=5)
                yield speech.StreamingRecognizeRequest(audio_content=first_audio_chunk)
            except queue.Empty:
                print("Waited for 5 seconds but no audio was received. Restarting recognition.")
                return

            while not stop_event.is_set() and time.time() - start_time < 290:
                try:
                    audio_chunk = audio_queue.get(timeout=1)
                    yield speech.StreamingRecognizeRequest(audio_content=audio_chunk)
                except queue.Empty:
                    continue

        try:
            responses = speech_client.streaming_recognize(
                config=streaming_config,
                requests=audio_requests_generator()
            )

            for response in responses:
                if stop_event.is_set():
                    break
                for result in response.results:
                    if result.is_final:
                        original_text = result.alternatives[0].transcript.strip()
                        
                        # CRITICAL ADDITION: Print English transcription safely on the main loop
                        print_english = lambda text: print(f"English: {text}")
                        loop.call_soon_threadsafe(print_english, original_text)
                        
                        # Send result to the translation thread queue
                        translation_request_queue.put(original_text)
        except Exception as e:
            if "Stream removed" in str(e):
                print("Stream timed out. Restarting transcription session.")
            else:
                print(f"Error in streaming recognition: {e}")
            time.sleep(1)


# Synchronous function for translation (must run in a thread)
def synchronous_translate(text, lang_code):
    if text == "New Talk":
        return "New Talk"
    
    # If the language is English, just return the transcribed text
    if lang_code == "en":
        return text

    # Otherwise, perform the synchronous, blocking translation API call
    return translate_client.translate(text, target_language=lang_code)['translatedText']

# FINAL STABLE LOGIC: Processes one language and broadcasts it
def process_and_broadcast_single_lang(loop, original_text, lang_code, lang_name):
    # 1. Perform blocking translation for a single language
    translated_text = synchronous_translate(original_text, lang_code)
    
    # 2. Create the JSON payload (language code is mandatory for client filtering)
    # The client expects a JSON string containing the language payload,
    # so we nest the JSON strings.
    payload = {
        "language_code": lang_code,
        "text": translated_text
    }
    # The message sent is the first level JSON (containing the second level JSON string)
    message_to_send = json.dumps({"text": json.dumps(payload)})
    
    # 3. CRITICAL ADJUSTMENT: Print only the translation (safely)
    print_translation = lambda name, text: print(f"{name} [{lang_code}]: {text}")
    loop.call_soon_threadsafe(print_translation, lang_name, translated_text)
    
    # 4. Safely schedule and WAIT for the async broadcast to finish
    future = asyncio.run_coroutine_threadsafe(broadcast_message(message_to_send), loop)
    
    try:
        # .result() waits for the network write to finish
        future.result(timeout=10) 
    except concurrent.futures.TimeoutError:
        print(f"Warning: Network write for {lang_code} timed out.")
    except Exception as e:
        print(f"Error during network broadcast for {lang_code}: {e}")


# Dedicated Thread for Translation and Final Output (Parallel Processing)
def translate_loop(loop):
    while not stop_event.is_set():
        try:
            # Pull transcription result from the request queue
            original_text = translation_request_queue.get(timeout=1)
            
            # CRITICAL CHANGE: Loop through all languages and process/broadcast each immediately
            for lang_code, lang_name in TARGET_LANGUAGES.items():
                
                # Each translation/broadcast is handled in this synchronous function call.
                process_and_broadcast_single_lang(loop, original_text, lang_code, lang_name)
                
            translation_request_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            print(f"Error in translation loop: {e}")
            time.sleep(1)


# --- MAIN EXECUTION ---

async def main():
    print("\n=== Real-Time Translation Server ===")
    print("\nAvailable network interfaces:")
    
    ip_addresses = get_ip_addresses()
    for iface, iface_type, ip in ip_addresses:
        print(f"{iface} ({iface_type}): {ip}")

    # Start mDNS broadcasting
    zeroconf = AsyncZeroconf()

    # Get the first non-loopback IP for mDNS registration
    server_ip = None
    http_info = None
    ws_info = None
    if ip_addresses:
        server_ip = ip_addresses[0][2]  # Get IP from first interface

        # Convert IP string to bytes
        ip_bytes =  socket.inet_aton(server_ip)

        # Register both HTTP and WebSocket services
        http_info = ServiceInfo(
            "_http._tcp.local.",
            "Captions._http._tcp.local.",
            addresses=[ip_bytes],
            port=8080,
            properties={'path': '/', 'version': '1.0'},
            server="captions.local."
        )

        ws_info = ServiceInfo(
            "_ws._tcp.local.",
            "Captions._ws._tcp.local.",
            addresses=[ip_bytes],
            port=8765,
            properties={'version': '1.0'},
            server="captions.local."
        )

        await zeroconf.async_register_service(http_info)
        await zeroconf.async_register_service(ws_info)
        print(f"\n✓ mDNS services registered as 'captions.local' (IP: {server_ip})")
    
    # Start WebSocket server
    ws_server = await websockets.serve(handler, "0.0.0.0", 8765)
    print("\n✓ WebSocket server started on port 8765")

    # Start HTTP server
    app = web.Application()
    app.router.add_get('/', http_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    print("\n✓ HTTP server started on port 8080")

    print("\nClients can connect by visiting:")
    print("  http://captions.local:8080  (recommended)")
    for iface, iface_type, ip in ip_addresses:
        print(f"  http://{ip}:8080")
    print("\n")

    loop = asyncio.get_running_loop()
    executor = concurrent.futures.ThreadPoolExecutor()

    # Start all three main threads in the executor
    audio_task = loop.run_in_executor(executor, audio_stream, loop)
    transcribe_task = loop.run_in_executor(executor, transcribe_loop, loop)
    translate_task = loop.run_in_executor(executor, translate_loop, loop) # Dedicated translation thread

    try:
        await asyncio.gather(
            audio_task,
            transcribe_task,
            translate_task,
            wait_for_keypress()
        )
    except asyncio.CancelledError:
        pass
    finally:
        audio_task.cancel()
        transcribe_task.cancel()
        translate_task.cancel()

        executor.shutdown(wait=True)

        ws_server.close()
        await ws_server.wait_closed()

        await runner.cleanup()

        # Unregister mDNS services
        if server_ip and http_info and ws_info:
            await zeroconf.async_unregister_service(http_info)
            await zeroconf.async_unregister_service(ws_info)
        await zeroconf.async_close()

        stop_event.clear()

        print("Server stopped and resources cleaned up")

if __name__ == "__main__":
    asyncio.run(main())
