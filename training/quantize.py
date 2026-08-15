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

model_path = r"C:\Users\mlgsa\Documents\Visual Studio Code\birds\models\bird_recognition_model.h5"
output_path = r"C:\Users\mlgsa\Documents\Visual Studio Code\birds\models\model_int8_full_quant.tflite"

model = tf.keras.models.load_model(model_path)

def representative_dataset_generator():
    num_calibration_steps = 100 
    for _ in range(num_calibration_steps):
        data = np.random.rand(1, 224, 224, 3).astype(np.float32)
        yield [data]

converter = tf.lite.TFLiteConverter.from_keras_model(model)
converter.optimizations = [tf.lite.Optimize.DEFAULT]

converter.representative_dataset = representative_dataset_generator
converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
converter.inference_input_type = tf.int8 
converter.inference_output_type = tf.int8 

try:
    tflite_quant_model = converter.convert()

    with open(output_path, "wb") as f:
        f.write(tflite_quant_model)

    print("Full integer quantized model saved to:", output_path)
except Exception as e:
    print(f"Error during full integer quantization: {e}")
    print("Consider checking your representative_dataset_generator and model input shape/type.")
