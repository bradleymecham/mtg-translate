import pyaudio
audio = pyaudio.PyAudio()

print("\n--- Available Audio Devices ---")
for i in range(audio.get_device_count()):
    info = audio.get_device_info_by_index(i)
    print(f"Index {i}: {info['name']}")
    print(f"  Max Input Channels: {info['maxInputChannels']}")
    print(f"  Max Output Channels: {info['maxOutputChannels']}")
    print(f"  Default Sample Rate: {info['defaultSampleRate']}")
    print("-" * 30)
audio.terminate()
