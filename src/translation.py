from google.cloud import translate_v2 as translate
import json
import asyncio
import time
import queue

class TranslationEngine:
    def __init__(self, config_manager, request_queue, network_server, 
                 stop_event):
        self.config = config_manager
        self.translation_queue = request_queue
        self.network_server = network_server # Reference to trigger broadcasts
        self.stop_event = stop_event
        self.translate_client = translate.Client()


    # Synchronous function for translation (must run in a thread)
    def synchronous_translate(self, text, lang_code):
        if text == "New Talk":
            return "New Talk"
    
        # If the language is English, just return the transcribed text
        if lang_code == "en":
            return text

        # Otherwise, perform the synchronous, blocking translation API call
        return self.translate_client.translate(
            text, target_language=lang_code)['translatedText']


    # FINAL STABLE LOGIC: Processes one language and broadcasts it
    def process_and_broadcast_single_lang(self, loop, original_text, 
                                          lang_code, lang_name):
        # Perform blocking translation for a single language
        translated_text = self.synchronous_translate(original_text, lang_code)

        # Create JSON payload (language code is mandatory for client filtering)
        # The client expects a JSON string containing the language payload,
        # so we nest the JSON strings.
        payload = {
            "language_code": lang_code,
            "text": translated_text
        }
        # Message sent is 1st level JSON (containing the 2nd level JSON string)
        message_to_send = json.dumps({"text": json.dumps(payload)})

        # Print only the translation
        print_translation = (
            lambda name, text: print(f"{name} [{lang_code}]: {text}"))
        loop.call_soon_threadsafe(print_translation, lang_name, translated_text)

        # Safely schedule and WAIT for the async broadcast to finish
        future = asyncio.run_coroutine_threadsafe(
            self.network_server.broadcast_message(message_to_send), loop)

        try:
            # .result() waits for the network write to finish
            future.result(timeout=10)
        except concurrent.futures.TimeoutError:
            print(f"Warning: Network write for {lang_code} timed out.")
        except Exception as e:
            print(f"Error during network broadcast for {lang_code}: {e}")


    def translate_loop(self, loop):
        while not self.stop_event.is_set():
            try:
                # Pull transcription result from the request queue
                original_text = self.translation_queue.get(timeout=1)
            
                # Loop through all languages
                for lang_code,lang_name in self.config.target_languages.items():
                
                    # Handle broadcasts in this synchronous function call.
                    self.process_and_broadcast_single_lang(
                        loop, original_text, lang_code, lang_name)
                
                self.translation_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in translation loop: {e}")
                time.sleep(1)

        pass
