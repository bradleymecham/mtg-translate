from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech
from google.protobuf import duration_pb2
import pyaudio
import numpy as np
from scipy import signal
import queue
import time
import struct

class TranscriptionEngine:
    def __init__(self, config_manager, translation_queue, stop_event):
        self.config = config_manager
        self.translation_queue = translation_queue
        self.stop_event = stop_event
        self.audio = pyaudio.PyAudio()
        self.audio_queue = queue.Queue()
        self.monitor_queue = queue.Queue()
        self.monitor_enabled = False
        self.speech_client = SpeechClient()
        self.project_id = "englishtexttojapanese"
        self.recognizer = f"projects/{self.project_id}/locations/global/recognizers/_"

        self._restart_signal = "RESTART_STREAM" 
        self.is_paused = True 
        self.STREAM_LIMIT = 290

        print("--- Initialized in SLEEP mode. Waiting for clients. ---")
        
        # This tracks the last time input audio was received
        self.last_audio_received_time = time.time()
        # This tracks the last time we heard from Google re transcription
        self.last_google_response_time = time.time()

    def restart_signal(self):
        """Public method to trigger a stream restart."""
        print("Restarting transcription stream for language change...")
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
        self.audio_queue.put(self._restart_signal)

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        state = "PAUSED" if self.is_paused else "ACTIVE"
        print(f"*** Transcription is now {state} ***")

    def toggle_monitor(self):
        self.monitor_enabled = not self.monitor_enabled
        status = "ENABLED" if self.monitor_enabled else "DISABLED"
        print(f"*** Monitor is now {status} ***")

    # Function for processing the audio stream
    def audio_stream(self, loop):

        stream = None

        FORMAT = pyaudio.paInt16
        CHANNELS = self.config.num_channels
        INPUT_CHANNEL = self.config.input_channel
        HW_RATE = self.config.hw_rate
        GOOGLE_RATE = 16000
        DEVICE_INDEX = self.config.input_device_index
        CHUNK = 1024


        try:
            stream = self.audio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=HW_RATE, 
                input=True,
                input_device_index=DEVICE_INDEX,
                frames_per_buffer=CHUNK)

            while not self.stop_event.is_set():
                try:
                    audio_chunk = stream.read(1024, exception_on_overflow=False)

                    samples = np.frombuffer(audio_chunk, dtype=np.int16)

                    if CHANNELS == 2:
                        # [0::2] is the Left channel, [1::2] is the Right
                        channel_data = samples[INPUT_CHANNEL::2]
                    else:
                        channel_data = samples

                    try:
                        num_samples = int(len(channel_data) * GOOGLE_RATE / HW_RATE)
                        resampled = signal.resample(channel_data, num_samples).astype(np.int16)
                    except ImportError:
                        # Fallback to linear interpolation
                        num_samples = int(len(channel_data) * GOOGLE_RATE / HW_RATE)
                        resampled = np.interp(
                            np.linspace(0, len(channel_data), num_samples, endpoint=False),
                            np.arange(len(channel_data)),
                            channel_data
                        ).astype(np.int16)

                    # Send resulting 16k mono bytes to transcription
                    resampled_bytes = resampled.tobytes()

                    loop.call_soon_threadsafe(self.audio_queue.put_nowait, 
                                              resampled_bytes)
                    # Add bytes to monitor
                    if self.monitor_enabled:
                        try:
                            self.monitor_queue.put_nowait(resampled_bytes)
                        except queue.Full:
                            pass  # Drop frame if montor can't keep up

                except IOError as e:
                    print(f"IO Error: {e}")
        except Exception as e:
            print(f"Buffer overflow: {e}")
        finally:
            if stream:
                stream.stop_stream()
                stream.close()

        pass

    def monitor_loop(self, loop):
        """Plays the processed audio to the default output for monitoring."""
        stream = None
        GOOGLE_RATE = 16000

        FORMAT = pyaudio.paInt16
        CHANNELS = 1  # Mono output
        RATE = GOOGLE_RATE # Match Google's expected rate (purpose is to check)
        CHUNK = 1024

        try:
            # Open output stream
            stream = self.audio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                output=True,
                output_device_index=self.config.output_device_index,
                frames_per_buffer=CHUNK
            )

            print("--- Audio monitor initialized ---")

            while not self.stop_event.is_set():
                try:
                    # Get audio from monitor queue
                    audio_chunk = self.monitor_queue.get(timeout=1)

                    # Play it
                    stream.write(audio_chunk)

                except queue.Empty:
                    continue
                except exception as e:
                    print(f"Monitor error: {e}")
        except Exception as e:
            print(f"Monitor initialization error: {e}")
        finally:
            if stream:
                stream.stop_stream()
                stream.close()
            print("--- Audio monitor stopped ---")


    # Function for transcribing the audio
    def transcribe_loop(self, loop):
        keywords = self.config.church_keywords
        adaptation = None
        if keywords:
            phrase_set = cloud_speech.PhraseSet(
                phrases =[{"value": word,
                           "boost": 15.0} for word in keywords]
            )
            adaptation = cloud_speech.SpeechAdaptation(
                    phrase_sets = [
                        cloud_speech.SpeechAdaptation.AdaptationPhraseSet(
                            inline_phrase_set = phrase_set
                        )]
            )

            if self.config.debug_mode:
                loop.call_soon_threadsafe(
                    print, "DEBUG: Applying English Church Keywords..."
                )

        while not self.stop_event.is_set():
            curr_lang_key = self.config.curr_lang
            curr_lang = self.config.LANGUAGE_MAP[curr_lang_key]
            curr_lang_code = curr_lang.speech_code

            if not self.is_paused:
                print("--- Starting Stream: "
                      f"{curr_lang.display_name} "
                      f"({curr_lang.speech_code}) ---")

            start_time = time.time()
            # Reset for the new stream
            self.last_google_response_time = time.time() 

            def audio_requests_generator():
            
                decode_conf = cloud_speech.ExplicitDecodingConfig(
                    encoding=cloud_speech.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
                        sample_rate_hertz=16000,
                        audio_channel_count=1,
                    )

                recognition_config = cloud_speech.RecognitionConfig(
                    explicit_decoding_config=decode_conf,
                    language_codes=[curr_lang_code],
                    model="long",
                    adaptation=adaptation
                )
    
                print(f"Language code: {curr_lang_code}")

                # Set to 1s (minimum allowed is 500ms)
                voice_activity_timeout = cloud_speech.StreamingRecognitionFeatures.VoiceActivityTimeout(
                    speech_end_timeout=duration_pb2.Duration(
                        seconds=1, nanos=00000000)
                )
    
                streaming_features = cloud_speech.StreamingRecognitionFeatures(
                    enable_voice_activity_events=True,
                    interim_results=True,
                    voice_activity_timeout=voice_activity_timeout
                )
    
                streaming_config = cloud_speech.StreamingRecognitionConfig(
                    config=recognition_config,
                    streaming_features=streaming_features
                )
    
                # First request must be the config
                yield cloud_speech.StreamingRecognizeRequest(
                    recognizer=self.recognizer,
                    streaming_config=streaming_config
                )

                while not self.stop_event.is_set():
                    now = time.time()

                    if now - start_time >= self.STREAM_LIMIT:
                        loop.call_soon_threadsafe(print,
                            "Reached Google 5-min limit. Refreshing stream.")
                        return # Exit generator to trigger a fresh stream
 
                    # If we have been sending audio for > 10s but Google hasn't
                    # sent a single interim or final result back, it's stuck.
                    if ((now - self.last_audio_received_time < 2) and 
                        (now - self.last_google_response_time > 10)):

                        loop.call_soon_threadsafe(print, 
                            "--- Stream Stall Detected. Restarting. ---")
                        return # This kills the current gRPC session

                    try:
                        chunk = self.audio_queue.get(timeout=1)

                        self.last_audio_received_time = now

                        # POISON PILL CHECK
                        if chunk == self._restart_signal:
                            return

                        # If paused, don't yield the audio to Google
                        if self.is_paused:
                            now = time.time()
                            self.last_google_response_time = now
                            continue

                        yield cloud_speech.StreamingRecognizeRequest(
                            audio=chunk)
 
                    except queue.Empty:

                        if now - self.last_audio_received_time > 5:
                            loop.call_soon_threadsafe(print,
                                "Waited for 5 seconds but no audio "
                                "was received. Check input source. "
                                "Restarting recognition.")
                            self.last_audio_received_time = now
                        continue

            try:
                responses = self.speech_client.streaming_recognize(
                    requests=audio_requests_generator()
                )

                for response in responses:
 
                    # Note the return fom Google
                    self.last_google_response_time = time.time() 

                    if self.stop_event.is_set():
                        break

                    if not response.results or len(response.results) == 0:
                        continue

                    result = response.results[0]

                    if not result.is_final:
                        # Show what Google is "thinking" in real-time
                        # Useful for debugging
                        #loop.call_soon_threadsafe(print, 
                        #    f"Interim: {result.alternatives[0].transcript}")
                        pass
                    if result.is_final:
                        if (not result.alternatives or
                            len(result.alternatives) == 0):
                            original_text = ""
                        else:
                            original_text = (
                                result.alternatives[0].transcript.strip())

                        if not original_text:
                            continue

                        # Print transcription safely on the main loop
                        if self.config.debug_mode:
                            loop.call_soon_threadsafe(print,
                                f"Orig.: {original_text}")
 
                        # Send result to the translation thread queue
                        self.translation_queue.put(original_text)

            except Exception as e:
                err_str = str(e)
                # Define common strings for "expected" stream closures
                expected_errors = [
                    "Stream timed out",
                    "Stream removed",
                    "Deadline Exceeded",
                    "Audio Timeout Error",
                    "499"
                ]
                # Check if this is one of those expected closures
                is_expected = any(msg in err_str for msg in expected_errors)

                if is_expected:
                    # If we aren't paused, a quick status update is helpful.
                    # If we ARE paused, we stay silent because this is normal.
                    if not self.is_paused:
                        print("Stream timed out, limit reached, or 499 error. "
                              "Restarting session...")
                    # Immediately restart the gRPC session
                    continue
                else:
                    # If something else (like a real network failure), print it.
                    print(f"Error in streaming recognition: {e}")
                    # Brief cooldown before the loop restarts the stream
                    time.sleep(1)
        pass

def __del__(self):
    """Automatic cleanup when the object is destroyed."""
    try:
        if hasattr(self, 'audio'):
            self.audio.terminate()
            print("PyAudio terminated.")
    except Exception:
        pass
