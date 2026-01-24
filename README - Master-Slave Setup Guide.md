# Master-Slave Translation System for Raspberry Pi

A headless real-time speech translation system designed for Raspberry Pi deployment. The master captures audio, transcribes, translates, and broadcasts to language-specific ports. Slaves connect to specific ports and play audio translations.

## Architecture

```
┌─────────────────────────────────────┐
│         MASTER (Pi 1)               │
│  - Audio capture & transcription    │
│  - Translation (Google API)         │
│  - Web interface (captions.local)   │
│  - Language port servers            │
│    • Port 9000: English             │
│    • Port 9001: Spanish             │
│    • Port 9002: French              │
│    • etc...                         │
└──────────────┬──────────────────────┘
               │
       ┌───────┴───────┬───────────┐
       │               │           │
┌──────▼──────┐ ┌──────▼──────┐ ┌─▼─────────┐
│  SLAVE 1    │ │  SLAVE 2    │ │  SLAVE 3  │
│  (Pi 2)     │ │  (Pi 3)     │ │  (Pi 4)   │
│  Port 9001  │ │  Port 9002  │ │  Port 9000│
│  Spanish    │ │  French     │ │  English  │
│  Audio Out  │ │  Audio Out  │ │  Audio Out│
└─────────────┘ └─────────────┘ └───────────┘
```

## Features

- **Headless Operation**: No GUI required, perfect for Raspberry Pi
- **Efficient Broadcasting**: Only translates when slaves are connected
- **Multiple Slaves**: Each slave gets a different language on its own port
- **Auto-reconnect**: Slaves automatically reconnect if connection drops
- **Web Interface**: Optional web monitoring on master at `captions.local:8080`
- **Low Latency**: Direct audio streaming to slaves

## Hardware Requirements

### Master Raspberry Pi
- Raspberry Pi 3B+ or newer (Pi 4 recommended)
- USB microphone or audio input device
- Network connection (WiFi or Ethernet)
- 8GB+ SD card

### Slave Raspberry Pi(s)
- Raspberry Pi Zero W or newer
- Speakers or headphones (3.5mm jack or USB audio)
- Network connection
- 8GB+ SD card

## Software Installation

### Master Setup

1. **Install system dependencies**
```bash
sudo apt-get update
sudo apt-get install -y python3-pip portaudio19-dev python3-pyaudio
```

2. **Install Python packages**
```bash
pip3 install google-cloud-speech google-cloud-translate google-cloud-texttospeech \
    pyaudio asyncio websockets aiohttp aiofiles zeroconf psutil aioconsole
```

3. **Copy master files**
Place these files on the master Pi:
- `master.py`
- `config_manager.py`
- `transcription.py`
- `translation.py` (uses MasterTranslationEngine from master.py)
- `networking.py`
- `text_to_speech.py`
- `config.ini`
- `static/TranslationClient.html` (for web interface)
- Google Cloud credentials JSON file

4. **Configure `config.ini`**
```ini
[AUTHENTICATION]
google_credentials_json = /home/pi/credentials.json

[AUDIO]
num_channels = 1

[TRANSLATION]
target_language_codes = en, es, fr, ja

[SPEECH]
custom_keywords = 
```

### Slave Setup

1. **Install system dependencies**
```bash
sudo apt-get update
sudo apt-get install -y python3-pip mpg123
```

2. **Install Python packages** (choose one option)

Option A - Using pygame (recommended):
```bash
pip3 install pygame
```

Option B - Using mpg123 (already installed above):
```bash
# mpg123 is already installed, no additional Python packages needed
```

3. **Copy slave file**
```bash
# Copy slave.py to each slave Pi
scp slave.py pi@slave-pi-ip:/home/pi/
```

## Running the System

### Start Master (on Master Pi)

```bash
# Basic mode (no debug output)
python3 master.py

# Verbose mode (shows transcriptions and translations)
python3 master.py -v

# Custom starting port
python3 master.py --start-port 10000
```

The master will display port assignments:
```
=== Language Port Assignments ===
English (en): port 9000
Spanish (es): port 9001
French (fr): port 9002
Japanese (ja): port 9003
```

### Start Slaves (on each Slave Pi)

Connect to the master using the appropriate port for your desired language:

```bash
# Spanish slave
python3 slave.py captions.local 9001

# French slave  
python3 slave.py captions.local 9002

# English slave
python3 slave.py captions.local 9000

# With custom volume (0.0 to 1.0)
python3 slave.py captions.local 9001 --volume 0.6

# Verbose mode
python3 slave.py captions.local 9001 -v
```

If mDNS isn't working, use the master's IP address:
```bash
python3 slave.py 192.168.1.100 9001
```

## Headless/Autostart Configuration

### Master Autostart (systemd service)

Create `/etc/systemd/system/translation-master.service`:

```ini
[Unit]
Description=Translation Master Server
After=network.target sound.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/translation
ExecStart=/usr/bin/python3 /home/pi/translation/master.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable translation-master.service
sudo systemctl start translation-master.service

# Check status
sudo systemctl status translation-master.service

# View logs
sudo journalctl -u translation-master.service -f
```

### Slave Autostart (systemd service)

Create `/etc/systemd/system/translation-slave.service`:

```ini
[Unit]
Description=Translation Slave Client
After=network.target sound.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi
ExecStart=/usr/bin/python3 /home/pi/slave.py captions.local 9001
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Note**: Change `9001` to the appropriate port for each slave's language.

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable translation-slave.service
sudo systemctl start translation-slave.service

# Check status
sudo systemctl status translation-slave.service

# View logs
sudo journalctl -u translation-slave.service -f
```

## Network Configuration Tips

### Static IP for Master (Recommended)

Edit `/etc/dhcpcd.conf`:
```
interface wlan0
static ip_address=192.168.1.100/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1 8.8.8.8
```

### Finding Master IP

On master:
```bash
hostname -I
```

On slave (if mDNS not working):
```bash
ping captions.local
```

## Monitoring and Control

### Master Commands (when run interactively)

- `q` - Quit the server
- `nt` - Send "New Talk" marker
- `p` - Pause/resume transcription
- Language codes (`en`, `es`, `fr`, etc.) - Switch transcription language

### Checking Slave Connections

On master, view connected slaves:
```bash
# If running with systemd
sudo journalctl -u translation-master.service -f | grep "connected"
```

### Audio Testing

Test slave audio output:
```bash
# On slave Pi
speaker-test -t wav -c 2

# Or play a test file
mpg123 test.mp3
```

### Web Interface

Access the web interface from any device on the network:
- `http://captions.local:8080` (if mDNS working)
- `http://192.168.1.100:8080` (using master's IP)

## Troubleshooting

### Master Issues

**No audio input detected:**
```bash
# List audio devices
arecord -l

# Test microphone
arecord -d 5 test.wav
aplay test.wav
```

**Google API errors:**
- Verify credentials file path in `config.ini`
- Check APIs are enabled in Google Cloud Console
- Verify billing is enabled

**Port already in use:**
```bash
# Find what's using a port
sudo netstat -tulpn | grep 9000

# Change starting port
python3 master.py --start-port 10000
```

### Slave Issues

**Cannot connect to master:**
```bash
# Test network connectivity
ping captions.local
# or
ping 192.168.1.100

# Test port connectivity
telnet captions.local 9001
```

**No audio output:**
```bash
# Check audio devices
aplay -l

# Set default audio output
sudo raspi-config
# Select: System Options > Audio > Select output

# Test audio
speaker-test -t wav
```

**pygame installation fails:**
```bash
# Use mpg123 instead (already installed)
# Or install pygame dependencies
sudo apt-get install libsdl2-dev libsdl2-mixer-dev
pip3 install pygame
```

### Network Issues

**mDNS not working:**
```bash
# Install avahi
sudo apt-get install avahi-daemon

# Use IP address instead
python3 slave.py 192.168.1.100 9001
```

**Firewall blocking ports:**
```bash
# Allow ports on master
sudo ufw allow 9000:9010/tcp
sudo ufw allow 8080/tcp
sudo ufw allow 8765/tcp
```

## Performance Optimization

### Master Pi Optimization

```bash
# Disable GUI (free up memory)
sudo systemctl set-default multi-user.target

# Reduce GPU memory (add to /boot/config.txt)
gpu_mem=16

# Overclock (Pi 4 only, optional)
# Add to /boot/config.txt
over_voltage=2
arm_freq=1750
```

### Slave Pi Optimization

```bash
# Disable unnecessary services
sudo systemctl disable bluetooth
sudo systemctl disable hciuart

# Use minimal audio buffer
export SDL_AUDIODRIVER=alsa
```

## Language Port Reference

Default port assignments (starting from 9000):

| Language | Code | Port |
|----------|------|------|
| English | en | 9000 |
| Spanish (US) | es | 9001 |
| Spanish (MX) | es2 | 9002 |
| French | fr | 9003 |
| Japanese | ja | 9004 |
| Russian | ru | 9005 |
| Portuguese | pt | 9006 |
| Chinese | cn | 9007 |
| Swahili | sw | 9008 |
| Swahili (Kenya) | sw2 | 9009 |

## Cost Considerations

Google Cloud API costs:
- **Speech-to-Text**: ~$0.006/15 seconds
- **Translation**: ~$20/million characters
- **Text-to-Speech**: ~$16/million characters

For continuous use, estimate monthly costs and consider Google Cloud's free tier.

## Security Notes

- Run services as non-root user (pi)
- Keep Google credentials secure (chmod 600)
- Consider VPN if accessing over public networks
- Update Raspberry Pi OS regularly: `sudo apt-get update && sudo apt-get upgrade`

## Future Enhancements

- [ ] Add authentication for slave connections
- [ ] Implement SSL/TLS encryption
- [ ] Add recording/playback features
- [ ] Support multiple simultaneous audio sources
- [ ] Add local caching to reduce API costs
- [ ] Implement offline translation fallback