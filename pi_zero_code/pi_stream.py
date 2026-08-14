from threading import Event
import time
import os
import paho.mqtt.client as mqtt
import subprocess
import requests
import http.server
import socketserver
import threading
import posixpath

import pi_gpio

from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput
from picamera2.outputs import FfmpegOutput

MQTT_STATUS_TOPIC = "birdfeeder/pi/status"
MQTT_COMMAND_TOPIC = "birdfeeder/pi/commands"
HLS_OUTPUT_DIR = "/tmp/hls_stream"

MQTT_BROKER = "10.0.0.48"
MQTT_CLIENT_ID = "pi_zero"

stream_timeout = 120

stop_streaming_event = Event()
stream_confirmation_time_event = Event()
picam2 = None
ffmpeg_process = None
mqtt_client_ref = None
ngrok_process = None
http_server = None
initial_mqtt_connection = True
httpd = None

def start_ngrok(port=8080):
    global ngrok_process
    try:
        ngrok_process = subprocess.Popen(
            ["ngrok", "http", str(port), "--log=stdout"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        print(f"Ngrok started on port {port}.")
        time.sleep(3)
        
        if ngrok_process.poll() is not None:
            stdout_data, stderr_data = ngrok_process.communicate()
            print(f"Ngrok process terminated unexpectedly: {stderr_data}")
            return False
        
        return True
    except Exception as e:
        print(f"Failed to start ngrok: {e}")
        return False
    



def get_ngrok_url():
    api_url = "http://localhost:4040/api/tunnels"
    
    for _ in range(10):
        try:
            response = requests.get(api_url)
            if response.status_code == 200:
                tunnels = response.json().get('tunnels', [])
                for tunnel in tunnels:
                    if tunnel['proto'] == 'https':
                        public_url = tunnel['public_url']
                        print(f"Ngrok public URL: {public_url}")
                        return public_url
            time.sleep(2)
        except requests.exceptions.RequestException as e:
            print(f"Error fetching ngrok URL: {e}")
            time.sleep(2)

    print("Failed to retrieve ngrok URL.")
    return None



def serve_hls_files():
    global httpd
    try:
        os.makedirs(HLS_OUTPUT_DIR, exist_ok=True)
        with open(os.path.join(HLS_OUTPUT_DIR, "index.html"), "w") as f:
            f.write(
                """
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Live Stream</title>
                    <style>
                        body { background-color: #2c3e50; color: white; font-family: sans-serif; text-align: center; }
                        h1 { color: #ffffff; }
                        video { width: 90%; max-width: 800px; margin-top: 20px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.5); }
                    </style>
                    <!-- hls.js library for playing HLS streams in a browser -->
                    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
                </head>
                <body>
                    <h1>Birdfeeder Livestream</h1>
                    <video id="video" controls autoplay muted></video>
                    <script>
                        var video = document.getElementById('video');
                        var videoSrc = 'stream.m3u8';
                        if (Hls.isSupported()) {
                            var hls = new Hls();
                            hls.loadSource(videoSrc);
                            hls.attachMedia(video);
                            hls.on(Hls.Events.MANIFEST_PARSED, function() {
                                video.play();
                            });
                        } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
                            video.src = videoSrc;
                            video.addEventListener('loadedmetadata', function() {
                                video.play();
                            });
                        }
                    </script>
                </body>
                </html>
                """
            )

        class HLSHandler(http.server.SimpleHTTPRequestHandler):
            def translate_path(self, path):
                path = path.split('?', 1)[0].split('#', 1)[0]
                path = posixpath.normpath(path).lstrip('/')
                if path == '..' or path.startswith('../'):
                    self.send_error(403, "Forbidden")
                    return HLS_OUTPUT_DIR
                full_path = os.path.join(HLS_OUTPUT_DIR, path)
                real_root = os.path.realpath(HLS_OUTPUT_DIR)
                real_full = os.path.realpath(full_path)
                if not (real_full == real_root or real_full.startswith(real_root + os.sep)):
                    self.send_error(403, "Forbidden")
                    return HLS_OUTPUT_DIR

                return full_path
            
            def log_message(self, format, *args):
                pass
        class HLSServer(socketserver.TCPServer):
            allow_reuse_address = True
        with HLSServer(("", 8080), HLSHandler) as httpd:
            print(f"Serving HLS files at port {8080}")
            httpd.serve_forever(poll_interval=0.5)
    except Exception as e:
        print(f"HTTP server error: {e}")
    finally:
        print("Stopping HTTP server and cleaning up HLS files.")
        if os.path.exists(os.path.join(HLS_OUTPUT_DIR, "index.html")):
            os.remove(os.path.join(HLS_OUTPUT_DIR, "index.html"))
        if os.path.exists(HLS_OUTPUT_DIR):
            for file_name in os.listdir(HLS_OUTPUT_DIR):
                os.remove(os.path.join(HLS_OUTPUT_DIR, file_name))
            os.rmdir(HLS_OUTPUT_DIR)




def on_mqtt_message(client, userdata, message):
    if message.payload.decode() =="stop_stream":
        print("Received stop_stream command from MQTT. Stopping the stream...")
        stop_streaming_event.set()    
    if message.payload.decode().isdigit():
        global stream_timeout
        stream_timeout = int(message.payload.decode()) * 60
        print(f"Stream timeout updated to {stream_timeout} seconds based on MQTT message.")



def on_disconnect(client, userdata, rc):
    if stop_streaming_event.is_set():
        return
    if mqtt_client_ref.is_connected():
        return
    print("Disconnected from MQTT broker. Attempting to reconnect...")
    connect_mqtt()
    


def connect_mqtt():
    
    if mqtt_client_ref != None and not mqtt_client_ref.is_connected():
        try:
            if initial_mqtt_connection:
                mqtt_client_ref.connect(MQTT_BROKER, 1883, 60)
                mqtt_client_ref.loop_start()
                print("Attempting to connect to MQTT client...")
                time.sleep(1)
            else:
                mqtt_client_ref.reconnect()
                time.sleep(1)
        except Exception as e:
            print(f"Error connecting to MQTT client: {e}")
            return False
        
        if mqtt_client_ref.is_connected():
            print("MQTT client is connected.")
            return True
        else:
            print("MQTT client is not connected.")
            return False
    else:
        return True

def start_streaming(picam2, live_config):
    global stop_streaming_event, \
     ffmpeg_process, mqtt_client_ref, ngrok_process, http_server, httpd, initial_mqtt_connection

    stop_streaming_event.clear()
    
    mqtt_client_ref = mqtt.Client(client_id=MQTT_CLIENT_ID, protocol=mqtt.MQTTv311)
    mqtt_client_ref.on_disconnect = on_disconnect
    
    http_server_thread = threading.Thread(target=serve_hls_files)
    http_server_thread.daemon = True 
    http_server_thread.start()
         
    try:
        if not http_server_thread.is_alive():
            print("HTTP server thread is not alive. Exiting streaming function.")
            return

        timeout = 0
        while not connect_mqtt() and timeout < 5:
            print("Waiting for MQTT connection...")
            time.sleep(1)
            timeout += 1
            
        if timeout >= 5:
            print("Failed to connect to MQTT after multiple attempts. Exiting streaming function.")
            return
        initial_mqtt_connection = False
        if not start_ngrok():
            print("Failed to start ngrok. Exiting streaming function.")
            return
        
        ngrok_public_url = get_ngrok_url()
        if not ngrok_public_url:
            print("Failed to retrieve ngrok public URL. Exiting streaming function.")
            return

        web_view_url = f"{ngrok_public_url}/index.html"        
        
        ffmpeg_command = [
            "ffmpeg",
            "-f", "h264", 
            "-i", "pipe:0", 
            "-an",  
            "-c:v", "copy",
            "-f", "hls",
            "-hls_time", "2",  
            "-hls_list_size", "5",
            "-hls_flags", "delete_segments", 
            os.path.join(HLS_OUTPUT_DIR, "stream.m3u8")
        ]


        ffmpeg_process = subprocess.Popen(ffmpeg_command,
                                          stdin=subprocess.PIPE,
                                          stdout=subprocess.DEVNULL,
                                          stderr=open("/tmp/ffmpeg.log", "wb"),
                                          close_fds=True)
        
        picam2.configure(live_config)
        print("Picamera2 configured for streaming.")

        picam2.start_recording(H264Encoder(), FileOutput(ffmpeg_process.stdin))
        
        if picam2.started:
            print("Picamera2 started successfully.")
        else:
            print("Picamera2 failed to start.")
            return

        print(f'Streaming started at {web_view_url}')

        mqtt_client_ref.publish(MQTT_STATUS_TOPIC, f'Streaming started at {web_view_url}')
        mqtt_client_ref.subscribe(MQTT_COMMAND_TOPIC)
        mqtt_client_ref.message_callback_add(MQTT_COMMAND_TOPIC, on_mqtt_message)

        currentTime = 0
        timeout = 0
        while not stop_streaming_event.is_set():
            currentTime += 1
            time.sleep(1) 
            
            if not stream_confirmation_time_event.is_set() and currentTime >= stream_timeout:
                break
            if ffmpeg_process.poll() is not None:
                print("FFmpeg process terminated unexpectedly.")
                break
            if ngrok_process.poll() is not None:
                print("Ngrok process terminated unexpectedly.")
                break
            
            if not mqtt_client_ref.is_connected() or not pi_gpio.check_wifi_status():
                print("WiFi or MQTT disconnected. Attempting to reconnect...")
                if not pi_gpio.check_wifi_status():
                    print("WiFi is disconnected. Attempting to reconnect...")
                    pi_gpio.connect_wifi()
                connect_mqtt()
                time.sleep(1)
                timeout += 1
                
                if timeout >= 3:
                    print("Failed to connect to WiFi or MQTT after multiple attempts. Exiting.")
                    break
            elif timeout > 0:
                print("Reconnected to WiFi and MQTT. Continuing stream...")
                timeout = 0

        print("Streaming stopped by user or MQTT command.")
                   
    except Exception as e:
        print(f"Error in streaming loop: {e}")
        mqtt_client_ref.publish(MQTT_STATUS_TOPIC, "av_stream_failed:startup_error")
        stop_streaming_event.set() 
        
    finally:
        if picam2 and picam2.started:
            picam2.stop_recording()
            print("Stopped recording.")
        
        if ffmpeg_process and ffmpeg_process.poll() is None:
            ffmpeg_process.terminate()
            try:
                ffmpeg_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                ffmpeg_process.kill()
            print("FFmpeg process terminated.")
            
        if ngrok_process and ngrok_process.poll() is None:
            ngrok_process.terminate()
            try:
                ngrok_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                ngrok_process.kill()
            print("Ngrok process terminated.")
            
        if mqtt_client_ref:
            mqtt_client_ref.unsubscribe(MQTT_COMMAND_TOPIC)
            mqtt_client_ref.publish(MQTT_STATUS_TOPIC, 'Streaming stopped')
            mqtt_client_ref.message_callback_remove(MQTT_COMMAND_TOPIC)
            mqtt_client_ref.loop_stop()
            print("MQTT client disconnected.")
        
        if http_server_thread and http_server_thread.is_alive():
            print("Stopping HTTP server thread...")
            if httpd:
                httpd.shutdown()
            http_server_thread.join()
        
        httpd = None
        http_server_thread = None
        http_server = None
        ffmpeg_process = None
        mqtt_client_ref = None
        ngrok_process = None
        initial_mqtt_connection = True
        
        print("Exiting streaming function. All resources cleaned up.")
        return
