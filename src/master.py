import asyncio
import queue
import aioconsole
import concurrent.futures
import argparse
import json
import socket
from config_manager import ConfigManager
from transcription import TranscriptionEngine
from translation import TranslationEngine
from networking import NetworkServer
from text_to_speech import TextToSpeechEngine

class LanguagePortServer:
    """Manages individual port servers for each language"""
    def __init__(self, lang_code, port, config, tts_engine, loop):
        self.lang_code = lang_code
        self.port = port
        self.config = config
        self.tts_engine = tts_engine
        self.loop = loop
        self.clients = set()
        self.server = None
        
    async def handle_client(self, reader, writer):
        """Handle a new slave connection"""
        addr = writer.get_extra_info('peername')
        print(f"[{self.lang_code}:{self.port}] Slave connected from {addr}")
        self.clients.add((reader, writer))
        
        try:
            # Keep connection alive and wait for disconnect
            while True:
                data = await reader.read(100)
                if not data:
                    break
                await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[{self.lang_code}:{self.port}] Connection error: {e}")
        finally:
            print(f"[{self.lang_code}:{self.port}] Slave disconnected from {addr}")
            self.clients.discard((reader, writer))
            writer.close()
            await writer.wait_closed()
    
    async def start(self):
        """Start the port server"""
        self.server = await asyncio.start_server(
            self.handle_client, '0.0.0.0', self.port)
        lang_name = self.config.LANGUAGE_MAP[self.lang_code].display_name
        print(f"✓ Language server started: {lang_name} on port {self.port}")
        
    async def stop(self):
        """Stop the port server"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            
    async def broadcast_audio(self, text):
        """Generate and broadcast audio to all connected slaves"""
        if not self.clients:
            return  # No clients, skip TTS generation
            
        # Generate audio in thread pool (blocking operation)
        audio_base64 = await asyncio.get_event_loop().run_in_executor(
            None, self.tts_engine.generate_audio, text, self.lang_code
        )
        
        if not audio_base64:
            return
            
        # Create message with audio data
        message = {
            "type": "audio",
            "language_code": self.lang_code,
            "text": text,
            "audio_data": audio_base64
        }
        
        # Serialize to JSON and encode
        json_data = json.dumps(message).encode('utf-8')
        # Send length prefix (4 bytes) followed by data
        length_prefix = len(json_data).to_bytes(4, byteorder='big')
        full_message = length_prefix + json_data
        
        # Broadcast to all connected clients
        disconnected = []
        for reader, writer in self.clients:
            try:
                writer.write(full_message)
                await writer.drain()
            except Exception as e:
                print(f"[{self.lang_code}:{self.port}] Error sending to client: {e}")
                disconnected.append((reader, writer))
        
        # Remove disconnected clients
        for client in disconnected:
            self.clients.discard(client)

class MasterTranslationEngine:
    """Enhanced translation engine that broadcasts to port servers"""
    def __init__(self, config_manager, request_queue, network_server, 
                 port_servers, stop_event):
        self.config = config_manager
        self.translation_queue = request_queue
        self.network_server = network_server
        self.port_servers = port_servers
        self.stop_event = stop_event
        from google.cloud import translate_v2 as translate
        self.translate_client = translate.Client()

    def synchronous_translate(self, text, orig_code, dest_code):
        if orig_code == dest_code:
            return text
        trans_code = self.config.LANGUAGE_MAP[dest_code].translation_code
        return self.translate_client.translate(text, 
            target_language=(trans_code))['translatedText']

    def process_and_broadcast_single_lang(self, loop, original_text, orig_code,
                                          dest_code):
        lang_name = self.config.LANGUAGE_MAP[dest_code].display_name
        
        # Get the port server for this language
        port_server = self.port_servers.get(dest_code)
        if not port_server:
            return
            
        # Only translate and broadcast if there are connected slaves
        if not port_server.clients and not self.network_server.clients:
            if self.config.debug_mode:
                print(f"Skipping {lang_name} - no clients connected")
            return

        # Perform translation
        translated_text = self.synchronous_translate(original_text, 
                                                     orig_code, dest_code)

        # Print translation
        if self.config.debug_mode:
            print(f"{lang_name} [{dest_code}]: {translated_text}")

        # Broadcast to web clients (original functionality)
        if self.network_server.clients:
            payload = {
                "language_code": dest_code,
                "text": translated_text
            }
            message_to_send = json.dumps({"text": json.dumps(payload)})
            
            future = asyncio.run_coroutine_threadsafe(
                self.network_server.broadcast_message(message_to_send), loop)
            try:
                future.result(timeout=10)
            except Exception as e:
                print(f"Error broadcasting to web clients for {dest_code}: {e}")

        # Broadcast audio to port server slaves
        if port_server.clients:
            future = asyncio.run_coroutine_threadsafe(
                port_server.broadcast_audio(translated_text), loop)
            try:
                future.result(timeout=15)
            except Exception as e:
                print(f"Error broadcasting audio to slaves for {dest_code}: {e}")

    def translate_loop(self, loop):
        while not self.stop_event.is_set():
            orig_code = self.config.curr_lang
            try:
                original_text = self.translation_queue.get(timeout=1)
                
                for dest_code, lang_name in self.config.target_languages.items():
                    self.process_and_broadcast_single_lang(
                        loop, original_text, orig_code, dest_code)
                
                self.translation_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in translation loop: {e}")
                import time
                time.sleep(1)

async def wait_for_keypress(stop_event, translation_queue, cfg, transcriber):
    langs = ", ".join(cfg.LANGUAGE_MAP.keys())
    print("Commands: 'q' to quit, 'nt' for New Talk, 'p':pause/resume, "
          f"or a lang code ({langs})")

    while not stop_event.is_set():
        try:
            user_input = (await aioconsole.ainput()).strip().lower()
            if user_input == 'q':
                stop_event.set()
                break
            elif user_input == 'nt':
                translation_queue.put("New Talk")
            elif user_input == 'p':
                transcriber.toggle_pause()
            elif user_input in cfg.LANGUAGE_MAP:
                print(f"Switching transcription to: {cfg.LANGUAGE_MAP[user_input].display_name}")
                cfg.curr_lang = user_input
                transcriber.restart_signal()
            else:
                print(f"Unknown command or language code: {user_input}")
        except Exception as e:
            print(f"Error reading input: {e}")

async def main():
    parser = argparse.ArgumentParser(description="Master Translation Server")
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="Enable debug mode")
    parser.add_argument('--start-port', type=int, default=9000,
                        help="Starting port for language servers (default: 9000)")
    args = parser.parse_args()

    # Setup shared resources
    stop_event = asyncio.Event()
    translation_queue = queue.Queue()
    loop = asyncio.get_running_loop()
    executor = concurrent.futures.ThreadPoolExecutor()

    # Initialize modules
    cfg = ConfigManager()
    cfg.debug_mode = args.verbose

    transcriber = TranscriptionEngine(cfg, translation_queue, stop_event)
    net = NetworkServer(transcriber)
    tts = TextToSpeechEngine(cfg, net)

    # Create port servers for each language
    port_servers = {}
    current_port = args.start_port
    
    print("\n=== Language Port Assignments ===")
    for lang_code, lang_name in cfg.target_languages.items():
        port_servers[lang_code] = LanguagePortServer(
            lang_code, current_port, cfg, tts, loop
        )
        print(f"{lang_name} ({lang_code}): port {current_port}")
        current_port += 1
    print()

    # Create master translation engine with port servers
    translator = MasterTranslationEngine(cfg, translation_queue, net, 
                                        port_servers, stop_event)

    # Start all servers
    await net.register_mDNS()
    await net.start_servers()
    
    # Start language port servers
    for port_server in port_servers.values():
        await port_server.start()
    
    print("\n=== Master Server Ready ===")
    print("Web interface: http://captions.local:8080")
    print("Slaves can connect to language-specific ports listed above\n")
    
    tasks = [
        loop.run_in_executor(executor, transcriber.audio_stream, loop),
        loop.run_in_executor(executor, transcriber.transcribe_loop, loop),
        loop.run_in_executor(executor, translator.translate_loop, loop),
        wait_for_keypress(stop_event, translation_queue, cfg, transcriber)
    ]

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    finally:
        # Cancel tasks
        for task in tasks[:3]:
            task.cancel()

        executor.shutdown(wait=True)

        # Stop language port servers
        for port_server in port_servers.values():
            await port_server.stop()

        await net.stop_servers()
        await net.unregister_mDNS()

        stop_event.clear()

        print("Master server stopped and resources cleaned up")

if __name__ == "__main__":
    asyncio.run(main())