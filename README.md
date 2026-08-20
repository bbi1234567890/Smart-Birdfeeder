# Smart Birdfeeder
A custom solar-powered smart birdfeeder powered by RPi Zero 2 W and ESP32.


<img width="4032" height="3024" alt="IMG_9375" src="https://github.com/user-attachments/assets/1efc5c30-0358-4618-b9c9-5ca29b601185" />
<img width="695" height="409" alt="image" src="https://github.com/user-attachments/assets/f362e258-c046-48c3-8c1c-d6a928ea3dca" />


# Features

- Real-time motion detection and image capture with species classification using AI.
- Live-streaming capabilities over the Internet.
- Powered fully by solar energy along with custom power management.

# Hardware


<img width="3024" height="4032" alt="IMG_9374" src="https://github.com/user-attachments/assets/373bad4b-54ec-4c6b-8de5-c7b3c9a44296" />
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

Firstly, the ESP32 is constantly powered, but mostly in deep sleep, which uses a negligible amount of power. The ESP32 wakes up from deep sleep periodically to check to see if any stream requests are pending via MQTT, and also if the Pi is still responsive (via the PULSE/heartbeat signal) or has crashed, with the latter causing the ESP32 to power cycle the Pi.

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

As stated previously, the ESP32 is used for power management for the birdfeeder. The ESP32 wakes up from deep sleep periodically, attempts to connect to WiFi and the MQTT client, and listens for commands while monitoring the Pi's status (checking to see if the Pi has frozen). 

If the Pi stops sending a periodic heartbeat signal via the PULSE pin, the ESP32 will power-cycle the Pi and go back to sleep. When a go-live message hasn't been received after several seconds, the ESP32 will also go back to sleep. When a go-live message is received, the ESP32 attempts to send a go-live signal to the Pi. If it succeeds and a livestream confirmation is received from the Pi via the RESPONSE pin, the ESP32 monitors the Pi's status while the Pi is livestreaming up until the Pi sends a shutdown confirmation to the ESP32 via the same pin.

Occasionally, at startup, the ESP32 will connect to an NTP server to obtain the current time. If it is night, the ESP32 will cut power to the Pi until the ESP32 realizes it is day again.

Originally, in order to maximize power efficiency, the plan was to attach the PIR sensor to the ESP32 instead of the Pi, and to keep the Pi completely off until there was motion detected or a livestream was requested. However, during testing, I found that the birdfeeder took a total of about 30 seconds after motion was detected to start taking pictures, even after optimizing the Pi's startup, which is incredibly slow. Soon after, I changed the power management to how it is now, where the Pi sits idle without WiFi connection until it receives a signal from the PIR sensor, which only takes about 7 seconds, which is a huge improvement in latency. 

### Raspberry Pi

To start, I have the script pi_gpio.py running as a systemd service, which automatically runs during startup. If the script somehow crashes, it will automatically restart the process. pi_gpio.py will continuously check for incoming signals from the GPIO pins. If a signal from the PIR sensor is detected, pi_snap_and_classify.py will be executed, and if a livestream signal from the ESP32 is received, pi_stream.py will be executed. pi_gpio.py also contains the heartbeat code that pulses the ESP32's PULSE pin to make sure that it is alive.

pi_snap_and_classify works by capturing 5 images, classifying them using the AI model, and pushing the image with the highest confidence value to Discord via a webhook. If WiFi isn't connected, the Pi will save the image locally and push it to Discord the next time WiFi is connected. If the Pi receives a livestream request in the middle of the pi_snap_and_classify process, it will run pi_stream and begin streaming immediately after the pi_snap_and_classify process has finished.

pi_stream works by using FFmpeg to convert camera video data into an HLS stream and hosting it on an HTTP server. ngrok is used to forward this HTTP server to a public URL so that the livestream can be viewed outside of the local network. The Pi connects to the MQTT to listen for stop streaming commands from the Discord bot, and also for an adjustable livestream duration set by the user. If a livestream duration isn't set, the birdfeeder automatically stops streaming after 2 minutes.

### AI Training

train_model.py first augments the training data (which consists of hundreds of bird pictures I screenshotted from the web) using ImageDataGenerator to artificially expand the dataset. It then loads a pretrained CNN model, MobileNetV2, freezes the base layers to preserve its already learned features, and only trains and fine-tunes the head to identify different bird species. To make classification more efficient on my Pi, I quantized the model resulting from train_model.py in quantize.py, converting the weights from float32 to int8.

# Conclusion

I learned how CNN AI models work and how they are trained, and also how to train them in the best possible way. Though I had trained my model with several hundred bird images, the iamges I trained them on were high-quality stock images taken from online, rather than images taken from my birdfeeder (I didn't have any yet), so the AI model will be quite inaccurate until I have enough images taken by the feeder itself.

I also improved my systems thinking while designing the relationship between the ESP32, Raspberry Pi, and the Discord bot, and also improved my overall coding skills in both C and Python.

I also challenged myself by making the feeder self-sufficient power-wise using solar energy, which required complex power mangement code for the ESP32. With my current power management, I estimate that I save around 40-50% of power compared to leaving the Raspberry Pi on 24/7, which is a huge improvement in efficiency.

Overall, this project was an incredible learning experience for me, and also very successful.
