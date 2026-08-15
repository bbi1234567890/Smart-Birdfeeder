import tensorflow as tf
from tensorflow.keras.applications import MobileNetV2 
from tensorflow.keras.layers import GlobalAveragePooling2D, Dense
from tensorflow.keras.models import Model
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint
import os
import matplotlib.pyplot as plt
import numpy as np

IMG_HEIGHT, IMG_WIDTH = 224, 224
BATCH_SIZE = 32

EPOCHS_PHASE1 = 10
EPOCHS_PHASE2 = 5

LEARNING_RATE_PHASE1 = 0.001
LEARNING_RATE_PHASE2 = 0.0001

DATA_DIR = 'data'
TRAIN_DIR = os.path.join(DATA_DIR, 'train')
VALIDATION_DIR = os.path.join(DATA_DIR, 'validation')
TEST_DIR = os.path.join(DATA_DIR, 'test')

MODEL_SAVE_PATH = 'models/bird_recognition_model.h5'
LABELS_FILE_PATH = 'labels.txt'

os.makedirs(os.path.dirname(MODEL_SAVE_PATH), exist_ok=True)
os.makedirs(TRAIN_DIR, exist_ok=True)
os.makedirs(VALIDATION_DIR, exist_ok=True)
os.makedirs(TEST_DIR, exist_ok=True)


print(f"TensorFlow Version: {tf.__version__}")
if tf.config.list_physical_devices('GPU'):
    print("GPU is available and will be used for training.")
else:
    print("No GPU detected. Training will run on CPU (this might be slower).")

print(f"Image Dimensions: {IMG_HEIGHT}x{IMG_WIDTH}")
print(f"Batch Size: {BATCH_SIZE}")
print(f"Data Directories: Train={TRAIN_DIR}, Validation={VALIDATION_DIR}, Test={TEST_DIR}")
print(f"Model will be saved to: {MODEL_SAVE_PATH}")


print("\n--- Setting up Data Generators ---")

train_datagen = ImageDataGenerator(
    rescale=1./255,          
    rotation_range=20,       
    width_shift_range=0.2,   
    height_shift_range=0.2,  
    shear_range=0.2,         
    zoom_range=0.2,          
    horizontal_flip=True,    
    fill_mode='nearest'      
)

val_test_datagen = ImageDataGenerator(rescale=1./255)

try:
    train_generator = train_datagen.flow_from_directory(
        TRAIN_DIR,
        target_size=(IMG_HEIGHT, IMG_WIDTH),
        batch_size=BATCH_SIZE,
        class_mode='categorical', 
        shuffle=True
    )

    validation_generator = val_test_datagen.flow_from_directory(
        VALIDATION_DIR,
        target_size=(IMG_HEIGHT, IMG_WIDTH),
        batch_size=BATCH_SIZE,
        class_mode='categorical',
        shuffle=False 
    )

    test_generator = val_test_datagen.flow_from_directory(
        TEST_DIR,
        target_size=(IMG_HEIGHT, IMG_WIDTH),
        batch_size=BATCH_SIZE,
        class_mode='categorical',
        shuffle=False 
    )

    NUM_CLASSES = train_generator.num_classes
    if NUM_CLASSES == 0:
        raise ValueError("No classes found. Ensure your data directories are correctly structured.")

    print(f"Found {NUM_CLASSES} classes in training data.")

    class_names = sorted(train_generator.class_indices.keys())
    with open(LABELS_FILE_PATH, 'w') as f:
        for class_name in class_names:
            f.write(f"{class_name}\n")
    print(f"Class labels saved to {LABELS_FILE_PATH}")

except Exception as e:
    print(f"Error loading data: {e}")
    print("Please ensure your 'data' directory is structured as follows:")
    print("data/")
    print("├── train/")
    print("│   ├── species_A/")
    print("│   ├── species_B/")
    print("│   └── ...")
    print("├── validation/")
    print("│   ├── species_A/")
    print("│   ├── species_B/")
    print("│   └── ...")
    print("└── test/")
    print("    ├── species_A/")
    print("    ├── species_B/")
    print("    └── ...")
    exit() 


print("\n--- Building Model Architecture (Transfer Learning) ---")

base_model = MobileNetV2(
    input_shape=(IMG_HEIGHT, IMG_WIDTH, 3), 
    include_top=False,                      
    weights='imagenet'                      
)

base_model.trainable = False

x = base_model.output
x = GlobalAveragePooling2D()(x) 
x = Dense(128, activation='relu')(x) 
predictions = Dense(NUM_CLASSES, activation='softmax')(x) 

model = Model(inputs=base_model.input, outputs=predictions)

print(f"\n--- Compiling Model for Phase 1 (Training New Layers) ---")
print(f"Learning Rate: {LEARNING_RATE_PHASE1}")

model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=LEARNING_RATE_PHASE1),
              loss='categorical_crossentropy', 
              metrics=['accuracy'])

early_stopping = EarlyStopping(monitor='val_loss', patience=3, restore_best_weights=True)
model_checkpoint_phase1 = ModelCheckpoint(
    MODEL_SAVE_PATH,
    monitor='val_accuracy',
    save_best_only=True,
    mode='max',
    verbose=1
)

print(f"\n--- Training Phase 1 for {EPOCHS_PHASE1} epochs ---")
history_phase1 = model.fit(
    train_generator,
    epochs=EPOCHS_PHASE1,
    validation_data=validation_generator,
    callbacks=[early_stopping, model_checkpoint_phase1], 
    verbose=1
)


print("\n--- Starting Fine-tuning Phase ---")
print("Unfreezing some base model layers for further training.")
print(f"Learning Rate: {LEARNING_RATE_PHASE2}")

base_model.trainable = True

fine_tune_at = len(base_model.layers) - 30 

for layer in base_model.layers[:fine_tune_at]:
    layer.trainable = False

print(f"Freezing layers before index {fine_tune_at}. Unfreezing layers from index {fine_tune_at} onwards.")

model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=LEARNING_RATE_PHASE2),
              loss='categorical_crossentropy',
              metrics=['accuracy'])

model_checkpoint_phase2 = ModelCheckpoint(
    MODEL_SAVE_PATH,
    monitor='val_accuracy',
    save_best_only=True,
    mode='max',
    verbose=1
)

print(f"\n--- Training Phase 2 for {EPOCHS_PHASE2} epochs (fine-tuning) ---")
history_phase2 = model.fit(
    train_generator,
    epochs=EPOCHS_PHASE1 + EPOCHS_PHASE2, 
    initial_epoch=history_phase1.epoch[-1] + 1,
    validation_data=validation_generator,
    callbacks=[early_stopping, model_checkpoint_phase2],
    verbose=1
)

model = tf.keras.models.load_model(MODEL_SAVE_PATH)
print(f"\nLoaded the best model from {MODEL_SAVE_PATH} for final evaluation.")

print("\n--- Evaluating Model on the Test Set ---")
if test_generator.samples == 0:
    print("No test samples found. Skipping final evaluation on test set.")
else:
    test_loss, test_accuracy = model.evaluate(test_generator, verbose=1)
    print(f"Test Loss: {test_loss:.4f}")
    print(f"Test Accuracy: {test_accuracy:.4f}")

print("\n--- Training Complete ---")
