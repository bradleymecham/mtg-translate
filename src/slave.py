#!/usr/bin/env python3
"""
Slave Audio Client for Translation System
Connects to master server and plays audio for a specific language
"""

import asyncio
import json
import base64
import argparse
import sys
import os
from io import BytesIO

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    print("Warning: pygame not available, trying alternative audio playback")

class AudioPlayer:
    """Handles audio playback using pygame or mpg123"""
    def __init__(self, volume=0.8):
        self.volume = volume
        self.use_pygame = PYGAME_AVAILABLE
        
        if self.use_pygame:
            pygame.mixer.init()
            pygame.mixer.music.set_volume(volume)
            print("Using pygame for audio playback")
        else:
            # Check if mpg123 is available
            if os.system("which mpg123 > /dev/null 2>&1") == 0:
                print("Using mpg123 for audio playback")
            else:
                print("Error: No audio playback available. Install pygame or mpg123")
                sys.exit(1)
    
    def play_audio(self, audio_base64):
        """Play audio from base64 encoded MP3 data"""
        try:
            # Decode base64 to bytes
            audio_bytes = base64.b64decode(audio_base64)
            
            if self.use_pygame:
                # Use pygame for playback
                audio_file = BytesIO(audio_bytes)
                pygame.mixer.music.load(audio_file)
                pygame.mixer.music.play()
                
                # Wait for playback to finish
                while pygame.mixer.music.get_busy():
                    pygame.time.Clock().tick(10)
            else:
                # Use mpg123 for playback
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                    f.write(audio_bytes)
                    temp_file = f.name
                
                os.system(f"mpg123 -q {temp_file}")
                os.unlink(temp_file)
                
        except Exception as e:
            print(f"Error playing audio: {e}")
    
    def set_volume(self, volume):
        """Set playback volume (0.0 to 1.0)"""
        self.volume = max(0.0, min(1.0, volume))
        if self.use_pygame:
            pygame.mixer.music.set_volume(self.volume)

class SlaveClient:
    """Connects to master server and plays audio"""
    def __init__(self, host, port, verbose=False):
        self.host = host
        self.port = port
        self.verbose = verbose
        self.audio_player = AudioPlayer()
        self.running = True
        self.reader = None
        self.writer = None
        
    async def receive_message(self):
        """Receive a length-prefixed JSON message"""
        try:
            # Read 4-byte length prefix
            length_bytes = await self.reader.readexactly(4)
            message_length = int.from_bytes(length_bytes, byteorder='big')
            
            # Read the actual message
            message_bytes = await self.reader.readexactly(message_length)
            message_str = message_bytes.decode('utf-8')
            
            return json.loads(message_str)
        except asyncio.IncompleteReadError:
            print("Connection closed by master")
            return None
        except Exception as e:
            print(f"Error receiving message: {e}")
            return None
    
    async def connect_and_listen(self):
        """Connect to master and listen for audio"""
        retry_delay = 5
        
        while self.running:
            try:
                print(f"Connecting to master at {self.host}:{self.port}...")
                self.reader, self.writer = await asyncio.open_connection(
                    self.host, self.port
                )
                print(f"✓ Connected to master server")
                
                # Listen for messages
                while self.running:
                    message = await self.receive_message()
                    
                    if message is None:
                        break
                    
                    await self.process_message(message)
                    
            except ConnectionRefusedError:
                print(f"Connection refused. Retrying in {retry_delay}s...")
                await asyncio.sleep(retry_delay)
            except Exception as e:
                print(f"Connection error: {e}")
                await asyncio.sleep(retry_delay)
            finally:
                if self.writer:
                    self.writer.close()
                    await self.writer.wait_closed()
                    self.writer = None
                    self.reader = None
                
                if self.running:
                    print(f"Disconnected. Reconnecting in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
    
    async def process_message(self, message):
        """Process received message and play audio"""
        try:
            msg_type = message.get("type")
            
            if msg_type == "audio":
                lang_code = message.get("language_code")
                text = message.get("text")
                audio_data = message.get("audio_data")
                
                if self.verbose:
                    print(f"[{lang_code}] {text}")
                else:
                    print(f"Playing: {text[:50]}..." if len(text) > 50 else f"Playing: {text}")
                
                if audio_data:
                    # Play audio in executor to avoid blocking
                    await asyncio.get_event_loop().run_in_executor(
                        None, self.audio_player.play_audio, audio_data
                    )
            else:
                if self.verbose:
                    print(f"Unknown message type: {msg_type}")
                    
        except Exception as e:
            print(f"Error processing message: {e}")
    
    def stop(self):
        """Stop the client"""
        self.running = False

async def main():
    parser = argparse.ArgumentParser(
        description="Slave client for translation system"
    )
    parser.add_argument(
        'host',
        help="Master server hostname or IP (e.g., captions.local or 192.168.1.100)"
    )
    parser.add_argument(
        'port',
        type=int,
        help="Port number for desired language (e.g., 9000 for first language)"
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help="Show detailed output"
    )
    parser.add_argument(
        '--volume',
        type=float,
        default=0.8,
        help="Audio volume (0.0 to 1.0, default: 0.8)"
    )
    
    args = parser.parse_args()
    
    # Validate volume
    if args.volume < 0.0 or args.volume > 1.0:
        print("Error: Volume must be between 0.0 and 1.0")
        sys.exit(1)
    
    print("\n=== Translation System Slave Client ===")
    print(f"Master: {args.host}:{args.port}")
    print(f"Volume: {int(args.volume * 100)}%")
    print("Press Ctrl+C to quit\n")
    
    client = SlaveClient(args.host, args.port, args.verbose)
    client.audio_player.set_volume(args.volume)
    
    try:
        await client.connect_and_listen()
    except KeyboardInterrupt:
        print("\nShutting down...")
        client.stop()
    finally:
        print("Slave client stopped")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass