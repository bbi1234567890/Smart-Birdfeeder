# Smart Birdfeeder
Custom solar-powered smart birdfeeder powered by RPi Zero 2 W and ESP32

<img width="4032" height="3024" alt="IMG_9375" src="https://github.com/user-attachments/assets/3c843abe-2c71-4072-b840-5e109d606ce0" />
<img width="686" height="407" alt="image" src="https://github.com/user-attachments/assets/7ee0abe9-cdf9-4933-a5fc-0370b7c4935b" />

# Features

- Real-time motion detection and image capture with species classification using AI
- Live-streaming capabilities over the Internet
- Powered fully by solar energy along with custom power management

# Hardware

<img width="3534" height="2379" alt="IMG_9368" src="https://github.com/user-attachments/assets/9e175873-def4-49ab-b3e5-d31b3d1afc99" />
<img width="1100" height="950" alt="birdfeeder_diagram" src="https://github.com/user-attachments/assets/e68878c9-80b1-4537-b989-8ebe3becce0c" />


List of materials:
- Raspberry Pi Zero 2 W
- Raspberry Pi Camera Module 2
- ESP32-C6
- 10000mAh 3.7V Rechargeable Lithium Battery
- PIR Sensor
- 10W 18V Solar Panel
- WaveShare Solar Power Manager Board
- G75PO4 P-Channel MOSFET
- 2N3904 BJT Transistor
- 1k Ohm Resistors

I went with the Raspberry Pi Zero 2 W because it's a very compact computer that packs a lot of processing capabilities, which is needed for my AI classification and live-streaming tasks, while also staying quite power-efficient. I decided to also include the ESP32 for the Pi's power management, since I thought that controlling the power source from another microcontroller (that itself uses a miniscule amount of power) would be the easiest and most effective.

### Power Management

Firstly, the ESP32 is constantly powered, but mostly in deep sleep, which uses a negligible amount of power. The ESP32 wakes up from deep sleep periodically to check to see if any stream requests are pending via MQTT, and also if the Pi is still responsive (via the PULSE/heartbeat signal) or has crashed, with the latter causing the ESP32 to power cycle the Pi. Every once in a while, the ESP32 will obtain the current time from an NTP server, and if it is night, it will switch the Pi off until it is morning again.

The ESP32 controls power delivery to the Pi via a GPIO pin. When the MOSFET GPIO pin is pulled high, it allows GND to pass through the BJT transistor into the gate of the P-Channel MOSFET, which allows 5V to pass through it, turning on the Pi.

When I first designed this circuit, I didn't include the BJT transistor and routed the MOSFET GPIO pin directly to the gate of the MOSFET. What I didn't realize was that the ESP32 GPIO pins only output 3.3V, which was a problem because the MOSFET's input was 5V, meaning the output voltage wouldn't be enough for the Pi. I fixed this by adding the BJT transistor, which allows a full 5V to pass through to the MOSFET gate with only a 3.3V signal. One might think that I could've just used the BJT transistor without the MOSFET to control power delivery, but the BJT transistor can't handle nearly enough the amount of amperage the Pi uses, so the MOSFET is necessary after all.
