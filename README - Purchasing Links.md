
# 🛠️ Translation System: Hardware Requirements

This document outlines the necessary hardware to host the translation server. The system is centered around a Raspberry Pi 4, which acts as the hub for audio capture, transcription processing, and local network broadcasting.

## 1. Core Server Components (Required)

These items constitute the "brain" of the translation system.

| Item | Description | Source | Price |
| --- | --- | --- | --- |
| **Raspberry Pi 4 Model B** | 2GB RAM version. Handles the OS and Python engine. | [PiShop.us](https://www.pishop.us/product/raspberry-pi-4-model-b-2gb/) | $55 |
| **Case & Power Adapter** | Argon POLY+ Case and UL-listed 5.1V 3A Power Supply. | [Amazon](https://a.co/d/02NCQaxC) | $15 |
| **Micro SD Card** | 64GB High-speed storage for the OS and software. | [Amazon](https://a.co/d/01MMUlCU) | $12 |
| **Core Subtotal** |  |  | **$82** |

---

## 2. Audio Input Hardware (Optional/As Needed)

Since the Raspberry Pi does not have a native XLR or 1/4" audio input, you will need an interface to bridge your church soundboard to the Pi.

### USB Audio Interface

Used to convert the analog signal from your soundboard into a high-quality digital stream for the Raspberry Pi.

* **Focusrite Scarlett Solo (3rd Gen)**
* **Price:** ~$110
* **Link:** [Sweetwater](https://www.sweetwater.com/store/detail/ScarSG3--focusrite-scarlett-solo-3rd-gen-usb-audio-interface)

### Compact Audio Mixer

Useful if you need to blend multiple audio sources (e.g., a pulpit mic and a room mic) before sending them to the translation engine.

* **Mackie Mix8 8-Channel Mixer**
* **Price:** ~$100
* **Link:** [Sweetwater](https://www.sweetwater.com/store/detail/Mix8--mackie-mix8-8-channel-compact-mixer)

### Combination Mixer and Interface

If you need both mixer and interface (or just want to save space) this will likely work well.

* **Behringer Xenyx 802S 8-Channel Mixer**
* **Price:** ~#100
* **Link** [Sweetwater](https://www.sweetwater.com/store/detail/802S--behringer-xenyx-802s-8-channel-analog-streaming-mixer)

---

## 📐 System Connection Diagram

1. **Audio Source** (Mixer/Mic) → **Scarlett Solo** (via XLR/TRS).
2. **Scarlett Solo** → **Raspberry Pi 4** (via USB).
3. **Raspberry Pi 4** → **Local Router** (via Ethernet or Wi-Fi).
4. **Congregants** → **Local Wi-Fi** (via Smartphone/Hearing Aids).

---

## 💡 Purchasing Notes

* **Storage:** The SD card price is calculated based on a multi-pack split; ensure you have at least a 16GB Class 10 card for reliable performance.
* **Power:** Do not use a standard phone charger for the Raspberry Pi. The linked 3A power adapter is required to prevent "under-voltage" errors during heavy audio processing.
* **Network:** For the lowest possible latency for hearing aid users, connecting the Raspberry Pi to your router via an **Ethernet cable** is highly recommended over Wi-Fi.
