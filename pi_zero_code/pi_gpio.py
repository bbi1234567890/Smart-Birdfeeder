import RPi.GPIO as GPIO
import time
import os
import threading
import subprocess
import pi_snap_and_classify
from picamera2 import Picamera2
import sys
import signal

LIVE_PIN = 19
PIC_PIN = 26
EXIT_PIN = 21
PULSE_PIN = 16
RESPONSE_PIN = 20
SHUTDOWN_PIN = 12



def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(LIVE_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(EXIT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(PIC_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(SHUTDOWN_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(PULSE_PIN, GPIO.OUT)
    GPIO.setup(RESPONSE_PIN, GPIO.OUT)
    GPIO.output(RESPONSE_PIN, GPIO.LOW)
    print("GPIO setup complete.")

def obtain_credentials():
    try:
        with open("/home/birdfeeder/home/credentials.txt", "r") as f:
            lines = f.readlines()
            ssid = lines[0].strip()
            password = lines[1].strip()
            webhook_url = lines[2].strip()
            return ssid, password, webhook_url
    except Exception as e:
        print("Error reading credentials:", e)
        return None, None, None

def connect_wifi():
    if check_wifi_status():
        print("Already connected to WiFi.")
        return True
    
    ssid, password, webhook_url = obtain_credentials()
    if not ssid or not password or not webhook_url:
        print("WiFi credentials or webhook URL not found. Cannot connect to WiFi.")
        return False
    
    try:
        result = subprocess.run(["nmcli", "device", "connect", "wlan0"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        
        if result.returncode != 0:
            print("nmcli failed to connect using saved profile:", result.stderr.decode().strip())

            result = subprocess.run(["nmcli", "device", "wifi", "connect", ssid, "password", password, "ifname", "wlan0"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        if result.returncode != 0:
            print("nmcli failed to connect with explicit credentials:", result.stderr.decode().strip())
            return False
 
        if not check_wifi_status():
            print("Failed to connect to WiFi.")
            return False
        
        if os.path.exists("/home/birdfeeder/home/images/failed/") and len(os.listdir("/home/birdfeeder/home/images/failed/")) != 0:
                    
            for image in os.listdir("/home/birdfeeder/home/images/failed/"):
                image_path = os.path.join("/home/birdfeeder/home/images/failed/", image)
                
                if os.path.isfile(image_path):
                    pi_snap_and_classify.send_to_discord(image_path, "Failed Image", "Failed Image", webhook_url)
                    print(f"Sent failed image: {image_path} to Discord.")
                    os.remove(image_path)
        
        return True
    
    except subprocess.TimeoutExpired:
        print("nmcli connection attempt timed out.")
        return False
    
    except Exception as e:
        print("Error connecting to WiFi:", e)
        return False
        
def disconnect_wifi():
    try:
        subprocess.run(["nmcli", "device", "disconnect", "wlan0"],stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    except Exception as e:
        print("Error disconnecting WiFi:", e)
        
def check_wifi_status():
    try:
        ip_result = subprocess.run(['hostname', '-I'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        has_ip = len(ip_result.stdout.decode('utf-8').strip()) > 0
        if not has_ip:
            return False

        ping_result = subprocess.run(['ping', '-c', '1', '-W', '2', '8.8.8.8'],stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return ping_result.returncode == 0
    except Exception as e:
        print("Error checking WiFi status:", e)
        return False



def pulse_esp():

    while True:
        GPIO.output(PULSE_PIN, GPIO.HIGH)
        time.sleep(0.1)
        GPIO.output(PULSE_PIN, GPIO.LOW)
        print("Pulse sent to ESP.")
        time.sleep(1.5)



def signal_shutdown():

    GPIO.output(RESPONSE_PIN, GPIO.HIGH)
    time.sleep(1)
    GPIO.output(RESPONSE_PIN, GPIO.LOW)
    print("Shutdown signal sent.")
    subprocess.run(["shutdown", "-h", "now"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)



def setup_camera():
    global picam2, pic_config, live_config
    print("Setting up camera...")
    picam2 = Picamera2()
    pic_config = picam2.create_still_configuration(main={"size": (2304, 1296)})
    live_config = picam2.create_video_configuration(main={"size": (1280, 720), "format": "RGB888"})

def handle_sigterm(signum, frame):
    print("SIGTERM received, cleaning up...")
    GPIO.cleanup()
    sys.exit(0)
    
if __name__ == "__main__":

    setup_gpio()
    
    thread = threading.Thread(target=pulse_esp, daemon=True)
    thread.start()
    print("Pulse ESP thread started.")
    signal.signal(signal.SIGTERM, handle_sigterm)
    
    while True:
                            
        if GPIO.input(PIC_PIN):
            print("Picture signal detected.")
            try:
                setup_camera()
                pi_snap_and_classify.run_task(picam2, pic_config)
            finally:
                picam2.close()
                disconnect_wifi()

        if GPIO.input(EXIT_PIN):
            
            timeout = 0
            while GPIO.input(EXIT_PIN) and timeout < 3:
                time.sleep(1)
                timeout += 1
                
            if timeout < 3:
                print("Exit signal detected, but not held long enough. Ignoring.")
                continue
            
            print("Exit signal detected. Attempting to exit...")
            for attempt in range(3):
                if connect_wifi():
                    break
                else:
                    print(f"Attempt {attempt + 1} to connect to WiFi failed. Retrying...")
                    time.sleep(2)
                    
            if not check_wifi_status():
                print("Failed to connect to WiFi after multiple attempts. Aborting exit.")
                disconnect_wifi()
                continue
            else: 
                GPIO.cleanup()
                sys.exit(0)

        if GPIO.input(LIVE_PIN):
            
            timeout = 0
            while GPIO.input(LIVE_PIN) and timeout < 2:
                time.sleep(1)
                timeout += 1
            if timeout < 2:
                print("Live signal detected, but not held long enough. Ignoring.")
                continue
        
            print("Live signal detected.")
            import pi_stream
            for attempt in range(3):
                if connect_wifi():
                    break
                else:
                    print(f"Attempt {attempt + 1} to connect to WiFi failed. Retrying...")
                    time.sleep(2)
                    
            if not check_wifi_status():
                print("Failed to connect to WiFi after multiple attempts. Exiting.")
                disconnect_wifi()
                continue
            else:
                print("Starting live stream...")
                try:
                    setup_camera()
                    pi_stream.start_streaming(picam2, live_config)
                finally:
                    picam2.close()
                    GPIO.output(RESPONSE_PIN, GPIO.HIGH)
                    time.sleep(1)
                    GPIO.output(RESPONSE_PIN, GPIO.LOW)
                    disconnect_wifi()
        
        if GPIO.input(SHUTDOWN_PIN):
            print("Shutdown signal detected.")
            timeout = 0
            while GPIO.input(SHUTDOWN_PIN) and timeout < 3:
                time.sleep(1)
                timeout += 1
                
            if timeout < 3:
                print("Shutdown signal detected, but not held long enough. Ignoring.")
                continue
            else:
                print("Shutting down...")
                signal_shutdown()
                disconnect_wifi()
        time.sleep(0.5)
        
