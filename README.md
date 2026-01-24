# Real-Time Speech Translation System

A Python-based real-time speech transcription and translation system that captures audio, transcribes it using Google Cloud Speech-to-Text, translates it into multiple languages, and broadcasts the results to connected web clients via WebSocket.

## Features

- Real-time audio capture and transcription
- Multi-language translation support (English, Spanish, French, Japanese, Russian, Portuguese, Swahili, Chinese)
- WebSocket-based live broadcasting to web clients
- mDNS support for easy local network discovery (`captions.local`)
- Configurable audio input (mono/stereo)
- Custom keyword boosting for improved transcription accuracy
- Pause/resume functionality
- Dynamic language switching during runtime

## Prerequisites

### Required Accounts & Services
- **Google Cloud Account** with billing enabled
- **Google Cloud Speech-to-Text API** enabled
- **Google Cloud Translation API** enabled
- **Service Account** with credentials JSON file

### System Requirements
- Python 3.7 or higher
- Audio input device (microphone or audio interface)
- Local network for client connections

## Installation

### 1. Clone or Download the Repository

Ensure you have all the following files:
- `main.py`
- `config_manager.py`
- `transcription.py`
- `translation.py`
- `networking.py`
- `config.ini`
- `static/TranslationClient.html`

### 2. Install Python Dependencies

```bash
pip install google-cloud-speech google-cloud-translate pyaudio asyncio websockets aiohttp aiofiles zeroconf psutil aioconsole
```

**Note for macOS users:** If you encounter issues installing `pyaudio`, you may need to install PortAudio first:
```bash
brew install portaudio
pip install pyaudio
```

**Note for Linux users:**
```bash
sudo apt-get install portaudio19-dev python3-pyaudio
pip install pyaudio
```

### 3. Set Up Google Cloud Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the following APIs:
   - Cloud Speech-to-Text API
   - Cloud Translation API
4. Create a Service Account:
   - Go to **IAM & Admin** > **Service Accounts**
   - Click **Create Service Account**
   - Grant it the following roles:
     - Cloud Speech Client
     - Cloud Translation API User
5. Create and download a JSON key file:
   - Click on the service account
   - Go to **Keys** tab
   - Click **Add Key** > **Create New Key** > **JSON**
   - Save the file to your project directory

### 4. Configure the Application

Edit `config.ini` and update the following sections:

```ini
[AUTHENTICATION]
google_credentials_json = /path/to/your/credentials.json

[AUDIO]
num_channels = 1  # Use 1 for mono, 2 for stereo

[TRANSLATION]
# Comma-separated language codes
target_language_codes = en, es, fr, ja

[SPEECH]
# Custom keywords for better transcription (optional)
custom_keywords = YourWord1, YourWord2
```

**Available language codes:**
- `en` - English
- `es` - Spanish (US)
- `es2` - Spanish (Mexico)
- `fr` - French
- `ja` - Japanese
- `ru` - Russian
- `pt` - Portuguese (Brazil)
- `cn` - Chinese (PRC)
- `sw` - Swahili
- `sw2` - Swahili (Kenya)

### 5. Create the Static Directory

Ensure you have a `static/` directory with `TranslationClient.html`:

```bash
mkdir -p static
```

Place the `TranslationClient.html` file in the `static/` directory.

## Running the Application

### Start the Server

**Basic mode:**
```bash
python main.py
```

**Debug mode** (prints transcripts and translations to console):
```bash
python main.py -v
```
or
```bash
python main.py --verbose
```

### What Happens on Startup

The server will:
1. Display available network interfaces and IP addresses
2. Register mDNS service as `captions.local`
3. Start WebSocket server on port 8765
4. Start HTTP server on port 8080
5. Begin listening for audio input

### Accessing the Client Interface

Clients can connect to view live translations by visiting:
- **Recommended:** `http://captions.local:8080`
- **Alternative:** `http://[YOUR_IP_ADDRESS]:8080`

The web interface will display translations in real-time as speech is detected.

## Usage

### Runtime Commands

While the server is running, you can enter the following commands:

- **`q`** - Quit the application
- **`nt`** - Signal "New Talk" (sends a marker to clients)
- **`p`** - Pause/resume transcription
- **Language codes** (`en`, `es`, `fr`, `ja`, etc.) - Switch transcription language on the fly

### Example Workflow

1. Start the server: `python main.py -v`
2. Open the client page in a web browser: `http://captions.local:8080`
3. Select your desired translation language(s) in the client interface
4. Start speaking into your microphone
5. Watch real-time transcriptions and translations appear on the client
6. Press `p` to pause if needed
7. Type a language code (e.g., `ja`) to switch transcription language
8. Press `q` when done to shut down gracefully

## Troubleshooting

### No Audio Input Detected
- Check your microphone/audio device is connected and selected as the default input
- Verify `num_channels` in `config.ini` matches your audio input (1 for mono, 2 for stereo)
- Check system audio permissions

### Google Cloud API Errors
- Verify your credentials JSON file path is correct in `config.ini`
- Ensure both Speech-to-Text and Translation APIs are enabled in your Google Cloud project
- Check that your service account has the required permissions
- Verify billing is enabled on your Google Cloud project

### Stream Stalls or Timeout Errors
- The application automatically restarts streams after Google's 5-minute limit
- If you see "Stream Stall Detected," the transcription language may not match the spoken language - try switching languages with the appropriate code

### Client Cannot Connect
- Ensure your firewall allows connections on ports 8080 and 8765
- Try connecting via IP address instead of `captions.local`
- Verify the server and client are on the same network

### Translation Not Appearing
- Check that the language code is correctly specified in `config.ini`
- Ensure the client interface has the correct language selected
- Verify translations are being printed in verbose mode (`-v`)

## Project Structure

```
.
├── main.py                          # Application entry point
├── config_manager.py                # Configuration and language mapping
├── transcription.py                 # Audio capture and speech-to-text
├── translation.py                   # Translation and broadcasting
├── networking.py                    # WebSocket/HTTP servers and mDNS
├── config.ini                       # Configuration file
├── static/
│   └── TranslationClient.html      # Web client interface
└── [credentials].json              # Google Cloud credentials
```

## Known Limitations

- Text-to-speech output is not yet implemented
- Maximum stream duration is 290 seconds (Google API limit) before automatic restart
- Transcription currently supports one source language at a time (switchable)

## Future Enhancements

- Text-to-speech audio output
- Multi-speaker support
- Recording and playback features
- Additional language support
- Enhanced client interface with more controls

## License

This project uses Google Cloud services which are subject to their respective terms of service and pricing.

## Support

For issues or questions:
1. Check the Troubleshooting section above
2. Verify all configuration settings in `config.ini`
3. Run in verbose mode (`-v`) to see detailed logs
4. Review Google Cloud API quotas and billing