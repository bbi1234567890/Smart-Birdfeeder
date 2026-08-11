import time
import os
from picamera2 import Picamera2
from datetime import datetime

NUM_PICS = 5 
LIVE_PIN = 19
RESPONSE_PIN = 20
live_requested = False

picam2 = None

def capture_image(directory="/home/birdfeeder/home/images"):
    if not os.path.exists(directory):
        os.makedirs(directory)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{directory}/image_{timestamp}.jpg"

    try:
        picam2.capture_file(filename)
        print(f"Image captured and saved as {filename}")
        return filename
    except Exception as e:
        print("Error capturing image:", e)
        return None



def load_model(model_path="/home/birdfeeder/home/model.tflite"):
    try:
        
        import tflite_runtime.interpreter as tf
        
        interpreter = tf.Interpreter(model_path=model_path)
        interpreter.allocate_tensors()
        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()
        print("Model loaded successfully.")
    except Exception as e:
        print("Error loading model:", e)
        return None, None, None
    return interpreter, input_details, output_details



def classify_image(interpreter, input_details, output_details, image_path):
    
    bird_species = []
    if os.path.exists("/home/birdfeeder/home/bird_species.txt"):
        print("Loading bird species from file...")
        with open ("/home/birdfeeder/home/bird_species.txt", "r") as file:
            bird_species = [line.strip() for line in file.readlines()]
    else:
        print("Bird species file not found. Using default species list.")

    image = Image.open(image_path).convert("RGB")
    image = image.resize((224, 224))

    input_index = input_details[0]['index']
    input_shape = input_details[0]['shape']
    input_dtype = input_details[0]['dtype']

    input_quantization_params = input_details[0].get('quantization_parameters', {}) # Use .get() for safety
    if not input_quantization_params: # Fallback for older models/runtimes using 'quantization' key
        input_quantization_params = input_details[0].get('quantization', {})

    input_scale = input_quantization_params.get('scales', [0.0])[0] # Get first scale
    input_zero_point = input_quantization_params.get('zero_points', [0])[0] # Get first zero_point

    # --- Get output tensor details and quantization parameters ---
    output_index = output_details[0]['index']
    output_quantization_params = output_details[0].get('quantization_parameters', {}) # Use .get() for safety
    if not output_quantization_params: # Fallback for older models/runtimes using 'quantization' key
        output_quantization_params = output_details[0].get('quantization', {})

    output_scale = output_quantization_params.get('scales', [0.0])[0] # Get first scale
    output_zero_point = output_quantization_params.get('zero_points', [0])[0] # Get first zero_point


    # --- Preprocessing the image for INT8 model input ---
    # Start with the image as float32 (0-255)
    input_data = np.array(image, dtype=np.float32)

    # Apply quantization: (real_value / scale) + zero_point
    # Ensure scale is not zero to avoid division by zero
    if input_scale == 0.0:
        # If scale is zero, it usually means the tensor is not quantized or is a constant.
        # Handle this case by assuming it's already in the correct range for its dtype.
        # This often happens for unquantized models or specific layers.
        # For a truly INT8 model, scale should not be zero.
        if input_dtype == np.int8:
            # If it expects int8 but scale is 0, it might imply values are already in int8 range (-128 to 127)
            input_scaled = np.array(image, dtype=np.int8)
        elif input_dtype == np.uint8:
            # If it expects uint8 but scale is 0, it might imply values are already in uint8 range (0 to 255)
            input_scaled = np.array(image, dtype=np.uint8)
        else:
            # Default to float32 conversion if scale is 0 and not explicitly int8/uint8
            input_scaled = input_data
    else:
        # Quantize the float data to the integer range
        input_scaled = input_data / input_scale + input_zero_point

    # Clip values to the valid range for the target integer type
    # For int8, this is typically -128 to 127
    # For uint8, this is typically 0 to 255
    if input_dtype == np.int8:
        input_scaled = np.clip(input_scaled, -128, 127)
    elif input_dtype == np.uint8:
        input_scaled = np.clip(input_scaled, 0, 255)
    else:
        # If the input_dtype is float32 (e.g., if you only did dynamic range quantization)
        # then no clipping to integer range is needed here.
        pass # The initial float32 conversion is fine.

    input_data = input_scaled.astype(input_dtype) # Cast to the model's expected integer type
    input_data = np.expand_dims(input_data, axis=0) # Add batch dimension

    # --- Set the tensor and invoke the interpreter ---
    interpreter.set_tensor(input_index, input_data)
    interpreter.invoke()

    # --- Get the raw quantized output ---
    output_data = interpreter.get_tensor(output_index)

    # --- Post-processing: De-quantize the output ---
    # The formula is: real_value = (quantized_value - zero_point) * scale
    
    # Check if the output is quantized (scale and zero_point will be non-zero for quantized outputs)
    # Be careful: sometimes scale is not exactly 0.0 but very close for unquantized outputs.
    # A common check is to see if output_details[0]['dtype'] is not float32.
    if output_scale != 0.0 and output_quantization_params: # Also check if quantization params were actually found
        output_data = (output_data.astype(np.float32) - output_zero_point) * output_scale
    # If the output is already float32, no de-quantization is needed.
    # Check its dtype from output_details[0]['dtype'] if unsure.

    predicted_class = bird_species[np.argmax(output_data[0])] if bird_species else np.argmax(output_data[0])
    confidence = output_data[0][np.argmax(output_data[0])]
    
    print(f"Predicted class: {predicted_class}, Confidence: {confidence:.4f}")
    return predicted_class, confidence

def send_to_discord(image_path, prediction, confidence, webhook_url):
    
    import requests, shutil
    
    if not os.path.exists(image_path):
        print("Image file does not exist:", image_path)
        return

    with open(image_path, 'rb') as f:
        image_data = f.read()

    payload = {
        "content": f"Prediction: {prediction}, Confidence: {confidence:.2f}"
    }
    
    files = {
        'file': (os.path.basename(image_path), image_data, 'image/jpeg')
    }

    try:
        response = requests.post(webhook_url, data=payload, files=files)
        
        if response.status_code == 200:
            print("Image sent to Discord successfully.")
        else:
            print(f"Failed to send image to Discord. Status code: {response.status_code}")
            shutil.copy(image_path, "/home/birdfeeder/home/images/failed/")
            
    except requests.exceptions.RequestException as e:
        print("Error sending image to Discord:", e)
        shutil.copy(image_path, "/home/birdfeeder/home/images/failed/")
    except Exception as e:
        print("Error sending image to Discord:", e)
        shutil.copy(image_path, "/home/birdfeeder/home/images/failed/")



def handle_live_pin_event(channel):
    global live_requested
    print("Live pin event detected.")
    live_requested = True



def run_task(picam, pic_config):

    global shutil, pi_gpio, Image, np, subprocess, pi_stream
    global picam2, live_requested
    picam2 = picam

    image_paths = []
    predicted_classes = []
    confidences = []
    maxConfidence = -1.0
    maxIndex = -1
    live_requested = False

    if not os.path.exists("/home/birdfeeder/home/images/failed"):
        os.makedirs("/home/birdfeeder/home/images/failed")

    try:
        
        import RPi.GPIO as GPIO
        import pi_gpio
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(LIVE_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.add_event_detect(LIVE_PIN, GPIO.RISING, callback=handle_live_pin_event)
        GPIO.setup(RESPONSE_PIN, GPIO.OUT)
        
        print("Starting camera...")

        picam2.configure(pic_config)
        picam2.start()
        time.sleep(1)

        print("Starting image capture task...")
        for i in range(NUM_PICS):
            print(f"Capturing image {i + 1}/{NUM_PICS}...")
            image_path = capture_image()
            if image_path:
                image_paths.append(image_path)
            time.sleep(1) 
            
        import subprocess, shutil
        import pi_stream
        from PIL import Image
        import numpy as np

        picam2.stop()
        print("Image capture task completed.")

        interpreter, input_details, output_details = load_model()
        print("Model loaded. Starting classification...")

        if interpreter is None or input_details is None or output_details is None:
            print("Model loading failed. Exiting.")
            for image_path in image_paths:
                if os.path.exists(image_path):
                    shutil.copy(image_path, "/home/birdfeeder/home/images/failed/")
                    print(f"Copied failed image: {image_path} to /home/birdfeeder/home/images/failed/")
            return
        
        for image_path in image_paths:
            print(f"Classifying image: {image_path}")
            predicted_class, confidence = classify_image(interpreter, input_details, output_details, image_path)
            if confidence is not None and predicted_class is not None:
                predicted_classes.append(predicted_class)
                confidences.append(confidence)

        if not predicted_classes or not confidences:
            print("No predictions made. Exiting.")
            for image_path in image_paths:
                if os.path.exists(image_path):
                    shutil.copy(image_path, "/home/birdfeeder/home/images/failed/")
                    print(f"Copied failed image: {image_path} to /home/birdfeeder/home/images/failed/")
            return

        print("Classification completed. Analyzing results...")
        for i in range(len(confidences)):
            if confidences[i] > maxConfidence:
                maxConfidence = confidences[i]
                maxIndex = i

        print(f"Highest confidence prediction: Class {predicted_classes[maxIndex]} with confidence {maxConfidence:.2f}")

        timeout = 0
        
        subprocess.run(["ifconfig", "wlan0", "up"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        while not pi_gpio.check_wifi_status() and timeout < 3:
            print("Waiting for WiFi connection...")
            pi_gpio.connect_wifi()
            timeout += 1

        if timeout >= 3:
            print("Failed to connect to WiFi after multiple tries. Exiting.")
            shutil.copy(image_paths[maxIndex], "/home/birdfeeder/home/images/failed/")

        else:
            print("WiFi connected. Sending results to Discord...")
            with open("/home/birdfeeder/home/credentials.txt", "r") as f:
                lines = f.readlines()
                url = lines[2].strip() if len(lines) > 2 else ""
            send_to_discord(image_paths[maxIndex], predicted_classes[maxIndex], confidences[maxIndex], url)
            
    except Exception as e:
        print("An error occurred:", e)
        for image_path in image_paths:
            if os.path.exists(image_path):
                shutil.copy(image_path, "/home/birdfeeder/home/images/failed/")
                print(f"Copied failed image: {image_path} to /home/birdfeeder/home/images/failed/")

    finally:
        for image_path in image_paths:
            if os.path.exists(image_path):
                os.remove(image_path)
                print(f"Removed image: {image_path}")
        GPIO.remove_event_detect(LIVE_PIN)
        print("Exiting photo task. All resources cleaned up.")
        
        if live_requested:
            print("Live streaming requested. Attempting to start...")
            timeout = 0
            while not pi_gpio.check_wifi_status() and timeout < 3:
                print("Waiting for WiFi connection...")
                pi_gpio.connect_wifi()
                timeout += 1

            if timeout >= 3:
                print("Failed to connect to WiFi after multiple tries. Exiting.")
            else:
                pi_stream.start_streaming(picam2, picam2.create_video_configuration(main={"size": (1280, 720), "format": "RGB888"}))
                GPIO.output(RESPONSE_PIN, GPIO.HIGH)
                time.sleep(1)
                GPIO.output(RESPONSE_PIN, GPIO.LOW)
            
        return
                
