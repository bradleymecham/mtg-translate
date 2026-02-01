import pyaudio
import numpy as np
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description="Terminal Audio Volume Monitor")
    parser.add_argument("-d", "--device", type=int, default=0, help="Input device index")
    parser.add_argument("-c", "--channels", type=int, default=1, help="Number of channels to open")
    parser.add_argument("-s", "--select", type=int, default=0, help="Specific channel index to monitor")
    parser.add_argument("-r", "--rate", type=int, default=16000, help="Sampling rate (e.g. 16000, 44100)")
    args = parser.parse_args()

    p = pyaudio.PyAudio()

    # Validate channel selection
    if args.select >= args.channels:
        print(f"Error: Cannot monitor channel {args.select} on a {args.channels}-channel stream.")
        sys.exit(1)

    try:
        stream = p.open(
            format=pyaudio.paInt16,
            channels=args.channels,
            rate=args.rate,
            input=True,
            input_device_index=args.device,
            frames_per_buffer=1024
        )
    except Exception as e:
        print(f"Could not open stream: {e}")
        p.terminate()
        sys.exit(1)

    print(f"Monitoring Device {args.device} (Channel {args.select}) at {args.rate}Hz...")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            # Read audio data
            data = stream.read(1024, exception_on_overflow=False)
            
            # Convert to numpy array
            samples = np.frombuffer(data, dtype=np.int16)
            
            # If multi-channel, extract only the requested channel
            if args.channels > 1:
                # Samples are interleaved: [C0, C1, C0, C1...]
                samples = samples[args.select::args.channels]

            # Calculate RMS (Root Mean Square) for volume
            # We use float64 to avoid overflow during squaring
            rms = np.sqrt(np.mean(samples.astype(np.float64)**2))
            
            # Normalize for a terminal bar (0 to 100ish)
            # 16-bit audio max is 32767. 
            level = int((rms / 32768) * 500) 
            bar = "█" * min(level, 60)
            
            # ANSI escape to overwrite the line
            sys.stdout.write(f"\rVolume: [{bar:<60}] {rms:>7.1f} ")
            sys.stdout.flush()

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

if __name__ == "__main__":
    main()
