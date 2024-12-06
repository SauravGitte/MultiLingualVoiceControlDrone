import airsim
import time
import threading
import math
import os
import speech_recognition as sr
import re
from googletrans import Translator
import spacy
from spacy.lang.en import English

nlp = spacy.load('en_core_web_md')

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

# Measure execution time of the function

#Multi-threading and Rule based NLP

#First select Language , then Begin client connection : 
translator = Translator()
source_language = input("Enter the language code you will speak (e.g., 'hi' for Hindi, 'es' for Spanish, 'en' for English): ").strip()


# Connect to the AirSim simulator
client = airsim.MultirotorClient()
client.confirmConnection()
client.enableApiControl(True)
client.armDisarm(True)

# Global variables
current_task = None
stop_event = threading.Event()
negate_next = False 

# Speech recognizer initialization
recognizer = sr.Recognizer()

# Command mappings with synonyms

# command_mappings = {
#     "takeoff": ["take off", "launch", "ascend", "rise", "start", "flying", "lift off", "elevate", "take flight"],
#     "land": ["land", "settle", "touch down", "descend", "land down", "arrive", "come down", "alight"],
#     "up": ["up", "ascend", "rise", "upside", "elevate", "lift", "go up", "climb", "raise", "upward", "elevate higher", "go upwards"],
#     "down": ["down", "descend", "lower", "below", "downside", "sink", "drop", "go down", "fall", "decline", "move downward"],
#     "forward": ["forward", "move forward", "advance", "front", "go ahead", "proceed", "move on", "go forth", "push forward", "head forward"],
#     "backward": ["backward", "reverse", "move back", "back", "go back", "retreat", "move behind", "fall back", "move rearward", "go in reverse"],
#     "left": ["left", "move left", "leftside", "go left", "turn left", "leftward"],
#     "right": ["right", "move right", "rightside", "go right", "turn right", "rightward"],
#     "rotate left": ["rotate left", "spin left", "spin counterclockwise", "turn counterclockwise", "rotate counterclockwise", "swerve left", "spin in left direction"],
#     "rotate right": ["rotate right", "spin right", "turn right", "spin clockwise", "turn clockwise", "rotate clockwise", "swerve right", "spin in right direction"],
#     "stop": ["stop", "halt", "pause", "cease", "hold", "freeze", "standby", "break", "terminate", "end", "cut", "stand still"],
#     "dont": ["don't", "do not", "not", "never", "don't do", "no", "avoid", "stop doing"],
#     "scan": ["scan", "look around", "sweep", "survey", "inspect"],
#     "analyse": ["record", "start recording", "begin recording", "analyse"]
# }

# Command mappings with synonyms
command_mappings = {
    "takeoff": ["take off", "launch", "ascend","rise","start", "fly", "flying"],
    "land": ["land", "touchdown"],
    "up": ["up", "ascend", "rise","upside", "upward"],
    "down": ["down", "descend", "lower","below","downside", "downward"],
    "forward": ["forward", "move forward", "advance","front", "go"],
    "backward": ["backward", "reverse","back"],
    "left": ["left","leftside", "leftward"],
    "right": ["right","rightside", "rightward"],
    "rotate left": ["rotate left", "spin left", "counterclockwise"],
    "rotate right": ["rotate right", "spin right", "clockwise"],
    "stop": ["stop", "halt", "pause", "freeze"],
    "scan": ["scan", "survey", "inspect", "check", "search"],
    "analyse": ["record", "start recording", "begin recording", "analyse"],
    "dont": ["don't", "do not", "not"]
}

def get_voice_command():
    """Function to capture voice input and transcribe it."""
    with sr.Microphone() as source:
        print("Listening for command...")
        audio = recognizer.listen(source)
    try:
        # Transcribe speech to text
        command_text = recognizer.recognize_google(audio, language=source_language)
        print(f"Transcribed command: {command_text}")
        return command_text.lower()
    except sr.UnknownValueError:
        print("Could not understand the audio.")
        return None
    except sr.RequestError:
        print("Could not request results from speech recognition service.")
        return None

#English Translation Text : 
def translate_to_english(text):
    """Translate the recognized text to English using Google Translate."""
    try:
        translated = translator.translate(text, src=source_language, dest='en')
        print(f"Translated to English: {translated.text}")
        return translated.text.lower()
    except Exception as e:
        print(f"Translation error: {e}")
        return None

def map_to_drone_command(command_text):
    """Maps recognized command text to a drone-specific command using spaCy."""
    global negate_next
    negate_next = False  # Reset negation for every command
    
    # Preprocess command_text with spaCy
    command_doc = nlp(command_text)
    mapped_command = None
    max_similarity = 0.0

    # Iterate through command mappings to find the best match
    for command, keywords in command_mappings.items():
        for keyword in keywords:
            keyword_doc = nlp(keyword)
            similarity = command_doc.similarity(keyword_doc)  # Calculate similarity
            if similarity > max_similarity and similarity > 0.7:  # Set a similarity threshold
                max_similarity = similarity
                mapped_command = command

            # Handle negation explicitly
            if 'dont' in command_text or 'do not' in command_text:
                print(f"Negation detected. Skipping command: {command}")
                negate_next = True
                return None

    if mapped_command:
        print(f"Mapped '{command_text}' to command '{mapped_command}' with similarity {max_similarity:.2f}")
        return [mapped_command]
    else:
        print(f"Could not map command: '{command_text}'. No suitable match found.")
        return []


def execute_command(command):
    global negate_next

    if command == 'dont':
        print("Negation command detected.")
        negate_next = True  # Enable negation for the next command
        return

    # Skip command execution if negation flag is set
    if negate_next:
        print(f"Negation active, skipping '{command}' command.")
        negate_next = False  # Reset negation after skipping
        return
    """Executes the drone command based on mapped text."""
    if command == 'takeoff':
        execute_command_in_thread(takeoff)
    elif command == 'land':
        execute_command_in_thread(land)
    elif command == 'up':
        execute_command_in_thread(translate_to_position_local, 0, 0, -100)
    elif command == 'down':
        execute_command_in_thread(translate_to_position_local, 0, 0, 100)
    elif command == 'forward':
        execute_command_in_thread(translate_to_position_local, 100, 0, 0)
    elif command == 'backward':
        execute_command_in_thread(translate_to_position_local, -100, 0, 0)
    elif command == 'left':
        execute_command_in_thread(translate_to_position_local, 0, -100, 0)
    elif command == 'right':
        execute_command_in_thread(translate_to_position_local, 0, 100, 0)
    elif command == 'rotate left':
        execute_command_in_thread(a)
    elif command == 'rotate right':
        execute_command_in_thread(d)
    elif command == 'scan':
        execute_command_in_thread(scan)
    elif command == 'analyse':
        execute_command_in_thread(analyse)
    elif command == 'stop':
        execute_command_in_thread(stop)
    # elif command == 'shutdown':
    #         execute_command_in_thread(shutdown)
    # elif command == 'on':
    #         execute_command_in_thread(on)
    else:
        print("Command not recognized.")

def control_drone():
    """Main loop for controlling the drone with voice commands."""
    print("Voice-Controlled Drone is Ready.")
    
    while True:
        command_text = get_voice_command()
        #Timer started after listening the command
        start_time=timer.start()
        if command_text:
            # Translate to English if needed
            translated_text = translate_to_english(command_text)
            if translated_text:
                print(f"Translated Command: {translated_text}")
                drone_commands = map_to_drone_command(translated_text)
                if drone_commands:
                    print("Mapped Command: ", drone_commands)
                    execute_command(drone_commands[0])
                else:
                    print("Command not recognized.")
                end_time=timer.end()
                print("Time: ", (end_time))
                #Timer stopped after command mapped
        time.sleep(0.1)  # Short delay for the next command input

# Drone control functions (unchanged)
def on():
    print("Turning On...")
    client = airsim.MultirotorClient()
    client.confirmConnection()
    client.enableApiControl(True)
    client.armDisarm(True)

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

def shutdown():
    print("Shutting Down...")
    client.enableApiControl(False)
    client.armDisarm(False)

def stop():
    print("Stopping the drone...")
    # Stop all movement and rotations
    client.moveByVelocityAsync(0, 0, 0, 1).join()  # Stop translation
    client.rotateByYawRateAsync(0, 0).join()  # Stop rotation
    time.sleep(1)  # Short delay for stability
    try:
        task.cancel()  # Cancel any ongoing task
    except Exception as e:
        pass  # Suppress any exception during task cancellation

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

# Function to handle translation to a new position in the drone's local (FPV) coordinates
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

def scan(save_path=r"F:\mini_project_files\collected_photos/scan_image.png"):
    print("Scanning the area...")
    responses = client.simGetImages([airsim.ImageRequest("0", airsim.ImageType.Scene)])  # Scene = RGB image
    if responses:
        response = responses[0]
        # Save the image to the specified path
        with open(save_path, "wb") as f:
            f.write(response.image_data_uint8)
        print(f"Image saved at {save_path}")
    else:
        print("Failed to capture image.")

# Function to analyse (click a picture and perform analysis)
def analyse(save_path=r"F:\mini_project_files\collected_photos/scan_image.png"):
    print("Capturing image for analysis...")
    responses = client.simGetImages([airsim.ImageRequest("0", airsim.ImageType.Segmentation)])  # Segmentation type
    if responses:
        response = responses[0]
        # Save the image
        with open(save_path, "wb") as f:
            f.write(response.image_data_uint8)
        print(f"Segmentation image saved at {save_path}")
    else:
        print("Failed to capture segmentation image.")

# Function to handle commands in separate threads
def execute_command_in_thread(function, *args):
    global current_task
    stop_event.set()
    if current_task:
        current_task.join()
    stop_event.clear()
    current_task = threading.Thread(target=function, args=args)
    current_task.start()



# Start the voice control loop
control_drone()
