import os
from google.cloud import speech, translate_v2 as translate
import json
import pyaudio
import asyncio
import concurrent
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
audio_queue = queue.Queue()

# WebSocket clients
clients = set()

# For elegant program exit
stop_event = asyncio.Event()

async def wait_for_keypress():
    print("Press 'q' to quit.")
    while not stop_event.is_set():
        #print("Waiting")
        try:
            key = await aioconsole.ainput()
            if key.strip().lower() == 'q':
                stop_event.set()
                break
            elif key.strip().lower() == 'nt':
                await translate_and_broadcast("New Talk")
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

async def translate_and_broadcast(text):
    translation = translate_client.translate(text, target_language=lang_abbrev)
    translated_text = translation['translatedText']
    print(f"English: {text}\n{lang_name}: {translated_text}")
    await broadcast_message(translated_text)

def audio_stream():
    audio = pyaudio.PyAudio()
    stream = None
    try:
        stream = audio.open(
            format=pyaudio.paInt16, channels=1, 
            rate=16000, input=True, frames_per_buffer=1024)
        
        while not stop_event.is_set():
            audio_chunk = stream.read(1024, exception_on_overflow=False)
            audio_queue.put(audio_chunk)  # Add to queue for transcription
    finally:
        if stream:
            stream.stop_stream()
            stream.close()
        audio.terminate()


def transcribe_loop():
    #print("Transcribing loop")
    while not stop_event.is_set():
        #print("Starting new recognition setup")
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code="en-US"
        )

        streaming_config = speech.StreamingRecognitionConfig(
            config=config,
            interim_results=True
        )

        #print("Starting new recognition session")
        start_time = time.time()

        def request_generator():
            """Yields audio chunks from the queue."""
            #print("Entered request generator")
            while not stop_event.is_set():
                if time.time() - start_time > 290:  # Restart stream every 290s
                    #print("Restarting stream...")
                    break
                try:
                    audio_chunk = audio_queue.get_nowait()
                    yield speech.StreamingRecognizeRequest(audio_content=audio_chunk)
                except queue.Empty:
                    time.sleep(0.1)
        

        responses = speech_client.streaming_recognize(streaming_config, request_generator())

        try:
            #print("Streaming responses")
            for response in responses:
                if stop_event.is_set():
                    break
                for result in response.results:
                    if result.is_final:
                        text = result.alternatives[0].transcript.strip()
                        #print("Final text")
                        return text  # Return the text instead of translating directly
        except Exception as e:
            print(f"Error in streaming recognition: {e}")
            time.sleep(1)  # Small delay before retrying
            return None

async def transcribe_and_translate():
    """Async wrapper that handles the transcription and translation."""
    while not stop_event.is_set():
        text = await asyncio.get_running_loop().run_in_executor(None, transcribe_loop)
        if text:
            await translate_and_broadcast(text)

async def transcribe_stream():
    #print("In transcribe_stream")
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, audio_stream)

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
            continue  # skip interfaces that are down

        for addr in addr_list:
            if addr.family == socket.AF_INET:
                ip = addr.address
                ip_obj = ipaddress.ip_address(ip)
                if ip_obj.is_loopback or ip_obj.is_link_local:
                    continue  # skip 127.0.0.1 and 169.254.x.x

                interface_type = get_interface_type(interface)
                result.append((interface, interface_type, ip))
    return result

async def main():
    for iface, iface_type, ip in get_ip_addresses():
        print(f"{iface} ({iface_type}): {ip}")

    server = await websockets.serve(handler, "0.0.0.0", 8765)
    print("WebSocket server started on ws://localhost:8765")
    
    # Create thread pool for synchronous operations
    loop = asyncio.get_running_loop()
    executor = concurrent.futures.ThreadPoolExecutor()
    
    # Start audio streaming and transcription in separate tasks
    audio_task = loop.run_in_executor(executor, audio_stream)
    transcribe_task = asyncio.create_task(transcribe_and_translate())
    
    try:
        # Wait for keypress or tasks to complete
        await asyncio.gather(
            audio_task,
            transcribe_task,
            wait_for_keypress()
        )
    except asyncio.CancelledError:
        pass
    finally:
        # Cancel all tasks
        audio_task.cancel()
        transcribe_task.cancel()
        
        # Shutdown the executor
        executor.shutdown(wait=True)
        
        # Close the server
        server.close()
        await server.wait_closed()
        
        # Clear the stop event
        stop_event.clear()
        
        print("Server stopped and resources cleaned up")

asyncio.run(main())
