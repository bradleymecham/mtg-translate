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

import psutil
import socket
import ipaddress


config = configparser.ConfigParser()
config.read('config.ini')

google_credentials_json = config['AUTHENTICATION']['google_credentials_json']
lang_abbrev = config['TRANSLATION']['language']
lang_name = config['TRANSLATION']['language_name']

# Google Cloud clients
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = google_credentials_json
speech_client = speech.SpeechClient()
translate_client = translate.Client()

# This is a standard, synchronous queue for communication between threads
audio_queue = queue.Queue()

# This is a new asynchronous queue for sending messages to the async world
translation_queue = asyncio.Queue()

# WebSocket clients
clients = set()

# For elegant program exit
stop_event = asyncio.Event()

# Global reference to the executor
executor = None


def get_interface_type(interface_name):
    """Heuristically determine interface type based on common naming."""
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


async def wait_for_keypress():
    print("Press 'q' to quit.")
    while not stop_event.is_set():
        try:
            key = await aioconsole.ainput()
            if key.strip().lower() == 'q':
                stop_event.set()
                break
            elif key.strip().lower() == 'nt':
                await broadcast_message("New Talk")
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
    if clients:
        await asyncio.wait([asyncio.create_task(client.send(json.dumps({"text": message}))) for client in clients])
    else:
        print("No clients connected to broadcast to.")

# This is the new synchronous function for translation
def synchronous_translate(text):
    return translate_client.translate(text, target_language=lang_abbrev)['translatedText']

# This function is now the consumer of the translation queue
async def broadcast_loop():
    while not stop_event.is_set():
        try:
            # Wait for translated text to be available
            text = await translation_queue.get()
            print(f"English: {text['original']}\n{lang_name}: {text['translated']}")
            await broadcast_message(text['translated'])
            translation_queue.task_done()
        except asyncio.CancelledError:
            break


def audio_stream(loop):
    global audio_queue
    audio = pyaudio.PyAudio()
    stream = None
    try:
        stream = audio.open(
            format=pyaudio.paInt16, channels=1,
            rate=16000, input=True, frames_per_buffer=1024,
            input_device_index=1)
        
        while not stop_event.is_set():
            try:
                audio_chunk = stream.read(1024, exception_on_overflow=False)
                audio_queue.put(audio_chunk)
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
                        translated_text = executor.submit(synchronous_translate, original_text).result()
                        # Pass the result to the new async queue
                        loop.call_soon_threadsafe(
                            translation_queue.put_nowait,
                            {"original": original_text, "translated": translated_text}
                        )
        except Exception as e:
            if "Stream removed" in str(e):
                print("Stream timed out. Restarting transcription session.")
            else:
                print(f"Error in streaming recognition: {e}")
            time.sleep(1)


async def main():
    for iface, iface_type, ip in get_ip_addresses():
        print(f"{iface} ({iface_type}): {ip}")

    server = await websockets.serve(handler, "0.0.0.0", 8765)
    print("WebSocket server started on ws://localhost:8765")
    
    loop = asyncio.get_running_loop()
    global executor
    executor = concurrent.futures.ThreadPoolExecutor()
    
    audio_task = loop.run_in_executor(executor, audio_stream, loop)
    transcribe_task = loop.run_in_executor(executor, transcribe_loop, loop)
    # The new task that handles broadcasting
    broadcast_task = asyncio.create_task(broadcast_loop())
    
    try:
        await asyncio.gather(
            audio_task,
            transcribe_task,
            broadcast_task,
            wait_for_keypress()
        )
    except asyncio.CancelledError:
        pass
    finally:
        audio_task.cancel()
        transcribe_task.cancel()
        broadcast_task.cancel()
        
        executor.shutdown(wait=True)
        
        server.close()
        await server.wait_closed()
        
        stop_event.clear()
        
        print("Server stopped and resources cleaned up")

if __name__ == "__main__":
    asyncio.run(main())
