# Smart Birdfeeder
Custom solar-powered smart birdfeeder powered by RPi Zero 2 W and ESP32


<img width="4032" height="3024" alt="IMG_9375" src="https://github.com/user-attachments/assets/1efc5c30-0358-4618-b9c9-5ca29b601185" />
<img width="695" height="409" alt="image" src="https://github.com/user-attachments/assets/f362e258-c046-48c3-8c1c-d6a928ea3dca" />


# Features

- Real-time motion detection and image capture with species classification using AI
- Live-streaming capabilities over the Internet
- Powered fully by solar energy along with custom power management

# Hardware


<img width="3534" height="2379" alt="IMG_9368" src="https://github.com/user-attachments/assets/a0aa229b-21ab-49cb-b506-dc8f67567ef5" />
<img width="1100" height="950" alt="birdfeeder_diagram" src="https://github.com/user-attachments/assets/455f704b-3b6b-4adf-972f-45cc30c0de38" />


### List of Materials


| Item | Reason |
| ------------- | ------------- |
| Raspberry Pi Zero 2 W  | Compact computer packing a lot of processing capability, which is needed for my AI classification and live-streaming tasks, and is also quite power efficient.  |
| Raspberry Pi Camera Module 2  | Camera officially marketed for the Raspberry Pi.  |
| ESP32-C6  | For Pi's power management, since I thought that controlling the power source from another microcontroller (that itself uses a miniscule amount of power) would be the easiest and most effective.  |
| 10000mAh 3.7V Rechargeable Lithium Battery  | Compact, rechargeable, and stores plenty of power for my project.  |
| PIR Sensor  | Needed for motion detection.  |
| 10W 18V Solar Panel  | Charges battery fast, and is compatible with my solar charger.  |
| WaveShare Solar Power Manager Board  | Compatible with my battery, and can convert 3.7V (battery voltage) to 5V easily (voltage needed for my project).  |
| G75PO4 P-Channel MOSFET  | Needed for my power management implementation.  |
| 2N3904 BJT Transistor  | Needed for my power management implementation.  |
| 1k Ohm Resistors  | Pull-up/pull-down resistors.  |

### Power Management

Firstly, the ESP32 is constantly powered, but mostly in deep sleep, which uses a negligible amount of power. The ESP32 wakes up from deep sleep periodically to check to see if any stream requests are pending via MQTT, and also if the Pi is still responsive (via the PULSE/heartbeat signal) or has crashed, with the latter causing the ESP32 to power cycle the Pi. Every once in a while, the ESP32 will obtain the current time from an NTP server, and if it is night, it will switch the Pi off until it is morning again.

The ESP32 controls power delivery to the Pi via a GPIO pin. When the MOSFET GPIO pin is pulled high, it allows GND to pass through the BJT transistor into the gate of the P-Channel MOSFET, which allows 5V to pass through it, turning on the Pi.

When I first designed this circuit, I didn't include the BJT transistor and routed the MOSFET GPIO pin directly to the gate of the MOSFET. What I didn't realize was that the ESP32 GPIO pins only output 3.3V, which was a problem because the MOSFET's input was 5V, meaning the output voltage wouldn't be enough for the Pi. I fixed this by adding the BJT transistor, which allows a full 5V to pass through to the MOSFET gate with only a 3.3V signal. One might think that I could've just used the BJT transistor without the MOSFET to control power delivery, but the BJT transistor can't handle nearly enough the amount of amperage the Pi uses, so the MOSFET is necessary after all.

# Software

### Discord Bot

I have a Raspberry Pi 4 plugged in 24/7 in my room serving as the intermediary between the birdfeeder and the outside world. The Pi 4 runs a Discord bot equipped with several commands that, when sent on the Birdfeeder's Discord server, attempts to ping either the ESP32 or Pi via MQTT, depending on the command. The commands are listed below.

| Command | Description |
| ------------- | ------------- |
| request_stream | Tells the ESP32 to send a go-live signal to the Pi.  |
| request_url  | Used to obtain the current stream URL.  |
| off | Tells the ESP32 to turn the Pi off.  |
| on | Tells the ESP32 to turn the Pi on.  |
| restart_esp32  | Tells the ESP32 to restart (in case of any errors).  |
| restart_pi  | Tells the ESP32 to restart the Pi (in case of any error, or to re-enter the script after a Pi script update).  |
| exit  | Tells the ESP32 to tell the Pi to exit its script (only used for Pi script updates). |

### ESP32

The ESP32 has the ability to connect to WiFI and, subsequently, the MQTT client. When 
