import airsim
import time
import threading
import math
import os
import speech_recognition as sr
import re
from transformers import pipeline
from googletrans import Translator

class Timer:
    def __init__(self):
        self.start_time = None

    def start(self):
        self.start_time = time.perf_counter()

    def end(self):
        if self.start_time is None:
            raise ValueError("Timer was not started. Call `start()` before `end()`.")
        elapsed_time = time.perf_counter() - self.start_time
        self.start_time = None  # Reset timer
        return elapsed_time

timer = Timer()

# Initialize the classifier and translator
classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")
labels = [
    "take off", "land", "up", "down", "forward", "backward",
    "left", "right", "rotate left", "rotate right", "stop"
]

translator = Translator()
source_language = input("Enter language code (e.g., 'hi' for Hindi): ").strip()

# Connect to AirSim
client = airsim.MultirotorClient()
client.confirmConnection()
client.enableApiControl(True)
client.armDisarm(True)

# Speech recognition setup
recognizer = sr.Recognizer()

# Global variables
current_task = None
stop_event = threading.Event()


def classify_command(command_text):
    """Classifies the given text into predefined drone commands."""
    result = classifier(command_text, labels, multi_label=False)
    command = result["labels"][0]
    confidence = result["scores"][0]
    print(f"Command classified: {command}")
    print(f"Confidence: {confidence:.2f}")
    return command if confidence > 0.2 else None


def get_voice_command():
    """Capture voice input and transcribe it."""
    with sr.Microphone() as source:
        print("Listening for command...")
        audio = recognizer.listen(source)
    try:
        command_text = recognizer.recognize_google(audio, language=source_language)
        print(f"Transcribed command: {command_text}")
        return command_text.lower()
    except sr.UnknownValueError:
        print("Could not understand the audio.")
        return None
    except sr.RequestError:
        print("Speech recognition service unavailable.")
        return None

# Command mappings with synonyms
# command_mappings = {
#     "takeoff": ["take off", "launch", "ascend","rise","start fly"],
#     "land": ["land", "touchdown"],
#     "up": ["up", "ascend", "rise","upside"],
#     "down": ["down", "descend", "lower","below","downside"],
#     "forward": ["forward", "move forward", "advance","front"],
#     "backward": ["backward", "reverse", "move back","back"],
#     "left": ["left", "move left","leftside"],
#     "right": ["right", "move right","rightside"],
#     "rotate left": ["rotate left", "spin left"],
#     "rotate right": ["rotate right", "spin right"],
#     "stop": ["stop", "halt", "pause"],
#     "dont": ["don't", "do not", "not"]
# }

# def map_to_drone_command(command_text):
#     """Maps recognized command text to a drone-specific command with negation handling."""
#     mapped_commands = []
#     for command, keywords in command_mappings.items():
#         for keyword in keywords:
#             if re.search(r'\b' + re.escape(keyword) + r'\b', command_text):
#                 mapped_commands.append(command)
#                 break  # Move to the next command after a match is found

#     return mapped_commands

def translate_to_english(text):
    """Translate recognized text to English."""
    try:
        translated = translator.translate(text, src=source_language, dest='en')
        print(f"Translated to English: {translated.text}")
        return translated.text.lower()
    except Exception as e:
        print(f"Translation error: {e}")
        return None


def execute_command(command):
    """Executes drone commands."""
    try:
        if command == 'take off':
            execute_command_in_thread(takeoff)
        elif command == 'land':
            execute_command_in_thread(land)
        elif command == 'up':
            execute_command_in_thread(translate_to_position_local, 0, 0, -10)
        elif command == 'down':
            execute_command_in_thread(translate_to_position_local, 0, 0, 10)
        elif command == 'forward':
            execute_command_in_thread(translate_to_position_local, 10, 0, 0)
        elif command == 'backward':
            execute_command_in_thread(translate_to_position_local, -10, 0, 0)
        elif command == 'left':
            execute_command_in_thread(translate_to_position_local, 0, -10, 0)
        elif command == 'right':
            execute_command_in_thread(translate_to_position_local, 0, 10, 0)
        elif command == 'rotate left':
            execute_command_in_thread(a)
        elif command == 'rotate right':
            execute_command_in_thread(d)
        elif command == 'stop':
            stop()
        else:
            print("Unrecognized or unsupported command.")
    except Exception as e:
        print(f"Error executing command: {e}")

# Function to take off
def takeoff():
    print("Taking off...")
    client.takeoffAsync().join()
    time.sleep(1)  # Adding a delay after takeoff for stability

# Function to land
def land():
    print("Landing...")
    client.landAsync().join()
    time.sleep(1)  # Delay before disarming

def translate_to_position_local(dx, dy, dz):
    current_position = client.getMultirotorState().kinematics_estimated.position
    yaw = get_yaw()  # Get the drone's current yaw angle

    # Convert local dx, dy to global coordinates based on yaw
    dx_world = dx * math.cos(yaw) - dy * math.sin(yaw)  # Forward/backward
    dy_world = dx * math.sin(yaw) + dy * math.cos(yaw)  # Left/right

    target_position = airsim.Vector3r(current_position.x_val + 5*dx_world, 
                                      current_position.y_val + 5*dy_world, 
                                      current_position.z_val + dz)

    # Move to the new position with the specified velocity and handle interruption
    task = client.moveToPositionAsync(target_position.x_val, target_position.y_val, target_position.z_val, velocity=1)
    while not stop_event.is_set():
        time.sleep(0.1)  # Check for stop_event periodically
    try:
        task.cancel()  # Cancel the current task if a new command is issued
    except Exception as e:
        pass  # Suppress any exception that occurs during task cancellation

def d():
    print("Rotating clockwise...")
    # Rotate clockwise indefinitely at a slow rate (e.g., 10 degrees per second)
    client.rotateByYawRateAsync(10, duration=9999)  # Rotate indefinitely

def a():
    print("Rotating counterclockwise...")
    # Rotate counterclockwise indefinitely at a slow rate (e.g., -10 degrees per second)
    client.rotateByYawRateAsync(-10, duration=9999)  # Rotate indefinitely

# Function to convert quaternion to yaw (drone's orientation)
def get_yaw():
    orientation = client.getMultirotorState().kinematics_estimated.orientation
    _, _, yaw = airsim.to_eularian_angles(orientation)  # Get yaw (rotation around the z-axis)
    return yaw

# Function to handle rotation
def rotate(dyaw):
    current_orientation = client.getMultirotorState().kinematics_estimated.orientation
    current_yaw = airsim.to_eularian_angles(current_orientation)[2]  # Get the yaw angle in degrees
    target_yaw = current_yaw + dyaw
    task = client.rotateToYawAsync(target_yaw)
    while not stop_event.is_set():
        time.sleep(0.1)
    try:
        task.cancel()  # Cancel rotation if interrupted
    except Exception as e:
        pass  # Suppress any exception that occurs during task cancellation


def stop():
    """Stop all drone motion."""
    print("Stopping drone...")
    client.moveByVelocityAsync(0, 0, 0, duration=1).join()


def control_drone():
    """Main control loop for voice-controlled drone."""
    print("Voice-controlled drone ready.")

    while True:
        command_text = get_voice_command()
        start_time=timer.start()
        if command_text:
            translated_text = translate_to_english(command_text)

            if translated_text:
                command = classify_command(translated_text)
                #command = map_to_drone_command(translated_text)
                if command:
                    print(f"Command: {command}")
                    execute_command(command)
                else:
                    print("Command not recognized.")
                end_time=timer.end()
                print("Time: ", (end_time))
        time.sleep(0.1)

# Function to handle commands in separate threads
def execute_command_in_thread(function, *args):
    global current_task
    stop_event.set()
    if current_task:
        current_task.join()
    stop_event.clear()
    current_task = threading.Thread(target=function, args=args)
    current_task.start()


if __name__ == "__main__":
    control_drone()
