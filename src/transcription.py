from google.cloud import speech
import pyaudio
import queue
import time
import struct

class TranscriptionEngine:
    def __init__(self, config_manager, translation_queue, stop_event):
        self.config = config_manager
        self.translation_queue = translation_queue
        self.stop_event = stop_event
        self.audio_queue = queue.Queue() # Now internal to this class
        self.speech_client = speech.SpeechClient()

    # Function for processing the audio stream
    def audio_stream(self, loop):

        audio = pyaudio.PyAudio()
        stream = None

        FORMAT = pyaudio.paInt16
        CHANNELS = self.config.num_channels
        RATE = 16000
        CHUNK = 1024


        try:
            stream = audio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE, 
                input=True, 
                frames_per_buffer=CHUNK)

            while not self.stop_event.is_set():
                try:
                    audio_chunk = stream.read(1024, exception_on_overflow=False)

                    mono_chunk = audio_chunk

                    if CHANNELS == 2:
                        # Unpack the stereo data (2* CHUNK 16-bit shorts)
                        data = struct.unpack('<' + str(2*CHUNK) + 'h', 
                                             audio_chunk)

                        # Extract right channel (every other sample, start at 1)
                        right_channel_data = data[1::2]
                    
                        # Repack the mono data back into a byte string
                        mono_chunk = (
                            struct.pack('<' + str(CHUNK) + 'h', 
                                        *right_channel_data)
                        )
                    # Send resulting chunk to transcription
                    loop.call_soon_threadsafe(self.audio_queue.put_nowait, 
                                              mono_chunk)
                except IOError as e:
                    print(f"IO Error: {e}")
        except Exception as e:
            print(f"Buffer overflow: {e}")
        finally:
            if stream:
                stream.stop_stream()
                stream.close()
            audio.terminate()

        pass

    # Function for transcribing the audio
    def transcribe_loop(self, loop):
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code="en-US"
        )

        streaming_config = speech.StreamingRecognitionConfig(
            config=config,
            interim_results=True
        )

        while not self.stop_event.is_set():
            start_time = time.time()

            def audio_requests_generator():
                try:
                    first_audio_chunk = self.audio_queue.get(timeout=5)
                    yield speech.StreamingRecognizeRequest(
                        audio_content=first_audio_chunk)
                except queue.Empty:
                    print(
                        "Waited for 5 seconds but no audio was received. "
                        "Restarting recognition.")
                    return

                while not (
                        self.stop_event.is_set() and 
                        time.time() - start_time < 290):
                    try:
                        audio_chunk = self.audio_queue.get(timeout=1)
                        yield speech.StreamingRecognizeRequest(
                            audio_content=audio_chunk)
                    except queue.Empty:
                        continue

            try:
                responses = self.speech_client.streaming_recognize(
                    config=streaming_config,
                    requests=audio_requests_generator()
                )

                for response in responses:
                    if self.stop_event.is_set():
                        break
                    for result in response.results:
                        if result.is_final:
                            original_text = (
                                result.alternatives[0].transcript.strip())
                        
                            # Print transcription safely on the main loop
                            print_english = (
                                    lambda text: print(f"English: {text}"))
                            loop.call_soon_threadsafe(print_english, 
                                                      original_text)
                        
                            # Send result to the translation thread queue
                            self.translation_queue.put(original_text)
            except Exception as e:
                if "Stream removed" in str(e):
                    print("Stream timed out. Restarting transcription session.")
                else:
                    print(f"Error in streaming recognition: {e}")
                time.sleep(1)
        pass
