import tensorflow as tf

model_path = r"C:\Users\mlgsa\Documents\Visual Studio Code\birds\models\bird_recognition_model.h5"
output_path = r"C:\Users\mlgsa\Documents\Visual Studio Code\birds\models\model_dynamic_range.tflite"

model = tf.keras.models.load_model(model_path)

converter = tf.lite.TFLiteConverter.from_keras_model(model)
converter.optimizations = [tf.lite.Optimize.DEFAULT] 

try:
    tflite_model = converter.convert()

    with open(output_path, "wb") as f:
        f.write(tflite_model)

    print("Dynamic range quantized model (float32 I/O) saved to:", output_path)
except Exception as e:
    print(f"Error during dynamic range quantization: {e}")
