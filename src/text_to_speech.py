from google.cloud import texttospeech
import base64
import json
import asyncio
import concurrent.futures

class TextToSpeechEngine:
    def __init__(self, config_manager, network_server):
        self.config = config_manager
        self.network_server = network_server
        self.tts_client = texttospeech.TextToSpeechClient()
        
        # Voice configuration mapping for each language
        self.voice_config = {
            "en": {"language_code": "en-US", "name": "en-US-Neural2-F"},
            "es": {"language_code": "es-US", "name": "es-US-Neural2-A"},
            "es2": {"language_code": "es-MX", "name": "es-MX-Neural2-A"},
            "fr": {"language_code": "fr-FR", "name": "fr-FR-Neural2-A"},
            "ja": {"language_code": "ja-JP", "name": "ja-JP-Neural2-B"},
            "ru": {"language_code": "ru-RU", "name": "ru-RU-Wavenet-A"},
            "pt": {"language_code": "pt-BR", "name": "pt-BR-Neural2-A"},
            "cn": {"language_code": "cmn-CN", "name": "cmn-CN-Wavenet-A"},
            "sw": {"language_code": "sw-KE", "name": "sw-KE-Standard-A"},
            "sw2": {"language_code": "sw-KE", "name": "sw-KE-Standard-A"}
        }

    def generate_audio(self, text, lang_code):
        """
        Generates audio from text using Google Cloud Text-to-Speech.
        Returns base64-encoded audio data.
        """
        try:
            # Get voice configuration for the language
            voice_conf = self.voice_config.get(lang_code, self.voice_config["en"])
            
            # Set the text input to be synthesized
            synthesis_input = texttospeech.SynthesisInput(text=text)

            # Build the voice request
            voice = texttospeech.VoiceSelectionParams(
                language_code=voice_conf["language_code"],
                name=voice_conf["name"]
            )

            # Select the type of audio file you want returned
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=1.0,  # Normal speed
                pitch=0.0  # Normal pitch
            )

            # Perform the text-to-speech request
            response = self.tts_client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config
            )

            # Encode the audio content to base64 for transmission
            audio_base64 = base64.b64encode(response.audio_content).decode('utf-8')
            
            return audio_base64

        except Exception as e:
            print(f"Error generating audio for {lang_code}: {e}")
            return None

    async def broadcast_audio(self, audio_base64, lang_code):
        """
        Broadcasts the audio to all connected clients.
        """
        if audio_base64:
            payload = {
                "type": "audio",
                "language_code": lang_code,
                "audio_data": audio_base64
            }
            message = json.dumps(payload)
            await self.network_server.broadcast_message(message)

    def generate_and_broadcast(self, loop, text, lang_code):
        """
        Synchronous function to generate audio and schedule broadcast.
        This runs in a thread pool.
        """
        # Generate the audio (blocking operation)
        audio_base64 = self.generate_audio(text, lang_code)
        
        if audio_base64:
            # Schedule the async broadcast on the event loop
            future = asyncio.run_coroutine_threadsafe(
                self.broadcast_audio(audio_base64, lang_code), 
                loop
            )
            
            try:
                future.result(timeout=10)
            except concurrent.futures.TimeoutError:
                print(f"Warning: Audio broadcast for {lang_code} timed out.")
            except Exception as e:
                print(f"Error broadcasting audio for {lang_code}: {e}")