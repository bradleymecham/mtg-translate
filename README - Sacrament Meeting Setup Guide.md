# README - Sacrament Meeting Setup Guide

This guide outlines the physical and software setup for the Master-Slave translation system during a Sacrament Meeting. The setup is divided into three tiers that build upon each other.

---

## Situation 1: Personal Device Only
*Use this for "Live Captions only" or testing on a single laptop/tablet via the web interface.*

### 1. Hardware Cabling & Audio Generation
* **Chapel Audio**: Ensure the building audio system is powered on.
* **Audio Interface**: Connect the building’s audio out (XLR or 1/4") into the **Scarlett Solo** input.
* **Master Connection**: Connect the Scarlett Solo USB cable into the computer acting as the **Master**.

### 2. Master Software Initialization
* **Access Terminal**: Open the terminal on the Master computer.
* **Navigate**: `cd` to the directory containing the code.
* **Environment**: Source Python libraries or activate your virtual environment if necessary.
* **Run Master**: 
    * Basic mode: `python3 src/master.py`
    * Verbose mode: `python3 src/master.py -v`
* **Activate**: Press `p` and hit **'Return'** in the terminal to activate transcription.
* **Web View**: Users on the network can now view captions at `http://captions.local:8080`.

---

## Situation 2: One Language Transmitter
*Use this to broadcast a single translated language (e.g., Spanish) to radio receivers.*

### 3. Set up Slave Computer
* **Power/Network**: Cable power and Ethernet for the **Slave Computer**.
* **Power On**: Turn on the slave computer and allow it to boot.

### 4. Set up Transmitter
* **Power**: Cable power for the FM/Digital transmitter.
* **Antenna**: Attach the antenna to the transmitter if it is not already connected.
* **Audio Link**: Connect a **3.5mm audio cable** between the Slave computer audio output and the transmitter "Audio In."
* **Sync**: Ensure the transmitter broadcasting address/frequency matches the label on the device.

### 5. Slave Software Initialization
* **Access Terminal**: Access the terminal of the slave computer.
* **Navigate**: `cd` to the code location.
* **Run Slave**: Run the slave script pointing to the master and the specific language port (e.g., **9001** for Spanish).
    * `python3 src/slave.py captions.local 9001`

### 6. Configure Receivers
* **Power**: Turn on the handheld receiver.
* **Tune**: Either adjust dials to the configured channel on the transmitter or press the **Seek** button inside the receiver.
* **Volume**: Adjust volume to a comfortable level.

---

## Situation 3: Multiple Language Transmitters
*Use this for multi-language support (e.g., Spanish, French, Portuguese).*

### 2.5 Set up Network Switch
* **Power/Ethernet**: Cable the network switch power and connect the building Ethernet wall jack to the switch.
* **Distribution**: Connect all Slave computers to the switch rather than a single wall jack.

### 7. Scale Hardware & Software
* **Repeat Steps 3–6**: Repeat the slave and transmitter setup for each additional language.
* **Port Mapping**: Ensure each slave is configured to the unique port assigned by the Master.

| Language | Default Port | Command Example |
| :--- | :--- | :--- |
| English | 9000 | `python3 src/slave.py captions.local 9000` |
| Spanish | 9001 | `python3 src/slave.py captions.local 9001` |
| French | 9002 | `python3 src/slave.py captions.local 9002` |

---

## Troubleshooting Tips
* **No Input**: Check the Scarlett Solo gain; if the ring is not green, the AI cannot "hear" the chapel audio.
* **Connection Refused**: Verify the Master is running and that the Slave can `ping captions.local`.
* **Static**: Ensure transmitter antennas are not touching metal or overlapping with other transmitters.
