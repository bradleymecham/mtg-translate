from google.cloud import translate_v2 as translate
import json
import asyncio
import time
import queue
import concurrent.futures

class TranslationEngine:
    def __init__(self, config_manager, request_queue, network_server, 
                 tts_engine, stop_event):
        self.config = config_manager
        self.translation_queue = request_queue
        self.network_server = network_server
        self.tts_engine = tts_engine  # Text-to-speech engine
        self.stop_event = stop_event
        self.translate_client = translate.Client()

    def synchronous_translate(self, text, orig_code, dest_code):
        """
        Synchronous function for translation (must run in a thread)
        """
        # If the origin and target language are the same, 
        # just return the transcribed text
        if orig_code == dest_code:
            return text

        # Otherwise, perform the synchronous, blocking translation API call
        trans_code = self.config.LANGUAGE_MAP[dest_code].translation_code
        return self.translate_client.translate(text, 
            target_language=(trans_code))['translatedText']

    def process_and_broadcast_single_lang(self, loop, original_text, orig_code,
                                          dest_code):
        """
        Processes one language and broadcasts both text and audio
        """
        lang_name = self.config.LANGUAGE_MAP[dest_code].display_name

        # Perform blocking translation for a single language
        translated_text = self.synchronous_translate(original_text, 
                                                     orig_code, dest_code)

        # Create JSON payload for text (language code is mandatory for client filtering)
        payload = {
            "type": "text",
            "language_code": dest_code,
            "text": translated_text
        }
        message_to_send = json.dumps(payload)

        # Print only the translation
        if self.config.debug_mode:
            print_translation = (
                lambda name, lang_code, text: 
                print(f"{name} [{lang_code}]: {text}"))
            loop.call_soon_threadsafe(print_translation, lang_name, dest_code, 
                                      translated_text)

        # Safely schedule and WAIT for the async text broadcast to finish
        future = asyncio.run_coroutine_threadsafe(
            self.network_server.broadcast_message(message_to_send), loop)

        try:
            future.result(timeout=10)
        except concurrent.futures.TimeoutError:
            print(f"Warning: Network write for {dest_code} timed out.")
        except Exception as e:
            print(f"Error during network broadcast for {dest_code}: {e}")

        # Generate and broadcast audio
        if self.tts_engine:
            self.tts_engine.generate_and_broadcast(loop, translated_text, dest_code)

    def translate_loop(self, loop):
        """
        Main translation loop that processes transcribed text
        """
        while not self.stop_event.is_set():
            orig_code = self.config.curr_lang
            try:
                # Pull transcription result from the request queue
                original_text = self.translation_queue.get(timeout=1)
            
                # Loop through all languages
                for dest_code, lang_name in self.config.target_languages.items():
                    # Handle broadcasts in this synchronous function call.
                    self.process_and_broadcast_single_lang(
                        loop, original_text, orig_code, dest_code)
                
                self.translation_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in translation loop: {e}")
                time.sleep(1)