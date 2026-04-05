import asyncio
import queue
import json
import html
from google.cloud import translate_v2 as translate

class TranslationEngine:
    """Enhanced translation engine that broadcasts to port servers"""
    def __init__(self, config_manager, request_queue, network_server, 
                 port_servers, stop_event):
        self.config = config_manager
        self.translation_queue = request_queue
        self.network_server = network_server
        self.port_servers = port_servers
        self.stop_event = stop_event
        self.translate_client = translate.Client()

    def synchronous_translate(self, text, orig_code, dest_code):
        if orig_code == dest_code:
            return text
        trans_code = self.config.LANGUAGE_MAP[dest_code].translation_code
        return self.translate_client.translate(text, 
            target_language=(trans_code))['translatedText']

    def process_and_broadcast_single_lang(self, loop, original_text, orig_code,
                                          dest_code, segment_id):
        lang_name = self.config.LANGUAGE_MAP[dest_code].display_name

        # Get the port server for this language
        port_server = self.port_servers.get(dest_code)
        if not port_server:
            print(f"Port server for {dest_code} language not found.")
            return

        # Only translate and broadcast if there are connected slaves
        if not port_server.clients and not self.network_server.clients:
            if self.config.debug_mode:
                print(f"Skipping {lang_name} - no clients connected")
            return

        # Perform translation
        translated_text = self.synchronous_translate(original_text, 
                                                     orig_code, dest_code)

        translated_text = html.unescape(translated_text)

        # Print translation
        if self.config.debug_mode:
            print(f"{lang_name} [{dest_code}]: {translated_text}")

        audio_base64 = port_server.tts_engine.generate_audio(
            translated_text, dest_code)

        payload = {
            "type": "audio",
            "id": segment_id,
            "is_final": True,
            "language_code": dest_code,
            "text": translated_text,
            "audio": audio_base64
        }

        # Broadcast to web clients (original functionality)
        if self.network_server.clients:

            message_to_send = json.dumps(payload)

            future = asyncio.run_coroutine_threadsafe(
                self.network_server.broadcast_message(message_to_send), loop)
            try:
                future.result(timeout=10)
            except Exception as e:
                print(f"Error broadcasting to web clients for {dest_code}: {e}")

        # Broadcast audio to port server slaves
        if port_server.clients:

            future = asyncio.run_coroutine_threadsafe(
                port_server.broadcast_audio(payload), loop)
            try:
                future.result(timeout=15)
            except Exception as e:
                print(f"Error broadcasting audio to slaves for {dest_code}: {e}")

    def translate_loop(self, loop):
        while not self.stop_event.is_set():
            orig_code = self.config.curr_lang
            try:
                data = self.translation_queue.get(timeout=1)

                if self.network_server.clients:
                    peek_payload = {
                        "type": "peek",
                        "id": data["id"],
                        "text": data["text"],
                        "is_final": data["is_final"],
                        "language_code": data["language_code"]
                    }
                    asyncio.run_coroutine_threadsafe(
                        self.network_server.broadcast_message(
                            json.dumps(peek_payload)), loop)

                # Only translate and do TTS when the sentence is finished
                if data["is_final"]:
                    for dest_code, lang_name in self.config.target_languages.items():
                        self.process_and_broadcast_single_lang(
                            loop, data["text"], orig_code,
                            dest_code, data["id"])

                self.translation_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in translation loop: {e}")
                import time
                time.sleep(1)
