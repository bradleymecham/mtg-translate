from google.cloud import speech
import pyaudio
import audioop
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
        self._restart_signal = "RESTART_STREAM" 
        self.is_paused = True 
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

    # Function for processing the audio stream
    def audio_stream(self, loop):

        audio = pyaudio.PyAudio()
        stream = None

        FORMAT = pyaudio.paInt16
        CHANNELS = self.config.num_channels
        HW_RATE = self.config.hw_rate
        GOOGLE_RATE = 16000
        DEVICE_INDEX = self.config.input_device_index
        CHUNK = 1024


        try:
            stream = audio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=HW_RATE, 
                input=True,
                input_device_index=DEVICE_INDEX,
                frames_per_buffer=CHUNK)

            while not self.stop_event.is_set():
                try:
                    audio_chunk = stream.read(1024, exception_on_overflow=False)


                    if CHANNELS == 2:
                       mono_chunk = audioop.tomono(audio_chunk, 2, 1, 0) 
                    else:
                        mono_chunk = audio_chunk

                    resampled_chunk, _ = audioop.ratecv(
                        mono_chunk, 2, 1, HW_RATE, GOOGLE_RATE, None)

                    # Send resulting chunk to transcription
                    loop.call_soon_threadsafe(self.audio_queue.put_nowait, 
                                              resampled_chunk)
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
        while not self.stop_event.is_set():
            curr_lang_key = self.config.curr_lang
            curr_lang = self.config.LANGUAGE_MAP[curr_lang_key]
            curr_lang_code = curr_lang.speech_code

            if not self.is_paused:
                print("--- Starting Stream: "
                      f"{curr_lang.display_name} "
                      f"({curr_lang.speech_code}) ---")
 
            speech_contexts = []

            if curr_lang_key == 'en':
                speech_context = speech.SpeechContext(
                    phrases=self.config.church_keywords,
                    boost=10.0
                )

                speech_contexts = [speech_context]

                if self.config.debug_mode:
                    loop.call_soon_threadsafe(
                        print, "DEBUG: Applying English Church Keywords..."
                    )
                    
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                language_code=curr_lang_code,
                speech_contexts=speech_contexts
            )

            streaming_config = speech.StreamingRecognitionConfig(
                config=config,
                interim_results=True
            )

            start_time = time.time()
            # Reset for the new stream
            self.last_google_response_time = time.time() 
            STREAM_LIMIT = 290

            def audio_requests_generator():
                while not self.stop_event.is_set():
                    now = time.time()

                    if now - start_time >= STREAM_LIMIT:
                        print("Reached Google 5-minute limit. Refreshing stream...")
                        return # Exit generator to trigger a fresh stream
 
                    # If we have been sending audio for > 10s but Google hasn't
                    # sent a single interim or final result back, it's stuck.
                    if ((now - self.last_audio_received_time < 2) and 
                        (now - self.last_google_response_time > 10)):

                        loop.call_soon_threadsafe(print, 
                            "--- Stream Stall Detected (Potential language mismatch). "
                            "Restarting...")
                        return # This kills the current gRPC session

                    try:
                        chunk = self.audio_queue.get(timeout=1)

                        # POISON PILL CHECK
                        if chunk == self._restart_signal:
                            return

                        # If paused, don't yield the audio to Google
                        if self.is_paused:
                            now = time.time()
                            self.last_audio_received_time = now
                            self.last_google_response_time = now
                            continue

                        self.last_audio_received_time = now

                        yield speech.StreamingRecognizeRequest(
                            audio_content=chunk)
 
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
                    config=streaming_config,
                    requests=audio_requests_generator()
                )

                for response in responses:
 
                    # Note the return fom Google
                    self.last_google_response_time = time.time() 

                    if self.stop_event.is_set():
                        break

                    # Record that Google sent something
                    self.last_google_response_time = time.time()

                    for result in response.results:
                        if not result.is_final:
                            # Show what Google is "thinking" in real-time
                            # Useful for debugging
                            #loop.call_soon_threadsafe(print, 
                            #    f"Interim: {result.alternatives[0].transcript}")
                            pass
                        if result.is_final:
                            original_text = (
                                result.alternatives[0].transcript.strip())
 
                            # Print transcription safely on the main loop
                            if self.config.debug_mode:
                                 print_transcript = (
                                      lambda text: 
                                      print(f"Orig.: {text}"))
                                 loop.call_soon_threadsafe(print_transcript,
                                                           original_text)
 
                            # Send result to the translation thread queue
                            self.translation_queue.put(original_text)
            except Exception as e:
                err_str = str(e)
                # Define common strings for "expected" stream closures
                expected_errors = [
                    "Stream removed",
                    "Deadline Exceeded",
                    "Audio Timeout Error"
                ]
                # Check if this is one of those expected closures
                is_expected = any(msg in err_str for msg in expected_errors)

                if is_expected:
                    # If we aren't paused, a quick status update is helpful.
                    # If we ARE paused, we stay silent because this is normal.
                    if not self.is_paused:
                        print("Stream timed out or limit reached. "
                              "Restarting session...")
                else:
                    # If something else (like a real network failure), print it.
                    print(f"Error in streaming recognition: {e}")
                # Brief cooldown before the loop restarts the stream
                time.sleep(1)
        pass
