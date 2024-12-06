import airsim
import time
import threading
import math
import os
import speech_recognition as sr
from googletrans import Translator
from transformers import pipeline
import spacy
import numpy as np
from tornado.ioloop import IOLoop
import asyncio


class Timer:
    def __init__(self):
        self.start_time = None

    def start(self):
        self.start_time = time.perf_counter()

    def end(self):
        if self.start_time is None:
            raise ValueError("Timer was not started. Call start() before end().")
        elapsed_time = time.perf_counter() - self.start_time
        self.start_time = None  # Reset timer
        return elapsed_time

timer = Timer()


# Load SpaCy model for dependency parsing and NER
nlp = spacy.load('en_core_web_sm')

# First select Language, then Begin client connection
translator = Translator()
source_language = input("Enter the language code you will speak (e.g., 'hi' for Hindi, 'es' for Spanish, 'en' for English): ").strip()

# Connect to the AirSim simulator
client = airsim.MultirotorClient()
client.confirmConnection()
client.enableApiControl(True)
client.armDisarm(True)

# Global variables
current_task_thread = None 
current_task = None
stop_event = threading.Event()
command_lock = threading.Lock()
is_executing_command = False

# Speech recognizer initialization
recognizer = sr.Recognizer()

class DroneCommandProcessor:
    def __init__(self):
        # Command structure remains the same as your original code
        self.commands = {
            'takeoff': ['take off', 'takeoff', 'launch', 'start', 'begin', 'lift'],
            'land': ['land', 'touchdown', 'come down', 'descend ground'],
            'stop': ['stop', 'halt', 'pause', 'freeze', 'stay', 'hover'],
            'up': ['up', 'higher', 'ascend', 'upward', 'upar'],
            'down': ['down', 'lower', 'descend', 'downward', 'niche'],
            'left': ['left', 'leftward', 'baye'],
            'right': ['right', 'rightward', 'daye'],
            'forward': ['forward', 'ahead', 'straight', 'front', 'age'],
            'backward': ['backward', 'back', 'reverse', 'backwards', 'piche'],
            'rotate_left': ['rotate left', 'turn left', 'spin left', 'spin counterclockwise'],
            'rotate_right': ['rotate right', 'turn right', 'spin right', 'spin clockwise']
        }

    # The process_command and _match_command methods remain the same as your original code
    def process_command(self, text):
        """Process the command text and return the corresponding action"""
        text = text.lower().strip()
        
        if any(stop_word in text for stop_word in self.commands['stop']):
            return {'action': 'stop'}

        parts = text.split()
        negation_words = ['dont', "don't", 'not']
        has_negation = any(word in parts for word in negation_words)
        
        if has_negation:
            return {'action': 'stop'}
        
        return {'action': self._match_command(text)} if self._match_command(text) else None

    def _match_command(self, text):
        """Match the input text against known commands"""
        if any(rot in text for rot in ['rotate', 'turn', 'spin']):
            if any(left in text for left in ['left', 'counterclockwise']):
                return 'rotate_left'
            elif any(right in text for right in ['right', 'clockwise']):
                return 'rotate_right'
        
        for command, variations in self.commands.items():
            if any(variation in text for variation in variations):
                if (command in ['rotate_left', 'rotate_right'] and 
                    not any(rot in text for rot in ['rotate', 'turn', 'spin'])):
                    continue
                return command
        
        return None


    
class DroneController:
    def __init__(self, client):
        self.client = client
        self.is_moving = False
        self._movement_lock = threading.Lock()

    async def takeoff(self):
        print("Taking off...")
        # Correct: No await here
        self.client.takeoffAsync().join()

    async def land(self):
        print("Landing...")
        # Correct: No await here
        self.client.landAsync().join()

    async def hover(self):
        """Make the drone hover at the current position."""
        try:
            self.client.hoverAsync().join()  # Correct: No await
        except RuntimeError as e:
            if "IOLoop is already running" not in str(e):
                raise

    async def stop(self):
        """Stop the drone and maintain its position."""
        print("Stopping and hovering...")
        with self._movement_lock:
            self.is_moving = False
        await self.hover()

    async def translate_to_position_local(self, dx, dy, dz):
        """Move the drone relative to its current position."""
        try:
            with self._movement_lock:
                if self.is_moving:
                    return
                self.is_moving = True

            current_state = self.client.getMultirotorState()
            current_position = current_state.kinematics_estimated.position
            yaw = self.get_yaw()

            dx_world = dx * math.cos(yaw) - dy * math.sin(yaw)
            dy_world = dx * math.sin(yaw) + dy * math.cos(yaw)

            target_position = airsim.Vector3r(
                current_position.x_val + dx_world,
                current_position.y_val + dy_world,
                current_position.z_val + dz
            )

            # Correct: No await
            self.client.moveToPositionAsync(
                target_position.x_val,
                target_position.y_val,
                target_position.z_val,
                velocity=2
            ).join()
        except Exception as e:
            print(f"Error in movement: {str(e)}")
        finally:
            with self._movement_lock:
                self.is_moving = False
            

    async def rotate(self, direction):
        """Rotate the drone in the specified direction."""
        try:
            with self._movement_lock:
                if self.is_moving:
                    return
                self.is_moving = True

            rate = 10 if direction == 'right' else -10
            # Correct: No await
            self.client.rotateByYawRateAsync(rate, duration=3).join()
        except Exception as e:
            print(f"Error in rotation: {str(e)}")
        finally:
            with self._movement_lock:
                self.is_moving = False
            

    def get_yaw(self):
        """Get the drone's current yaw angle."""
        orientation = self.client.getMultirotorState().kinematics_estimated.orientation
        _, _, yaw = airsim.to_eularian_angles(orientation)
        return yaw
    
def thread_wrapper(coro, *args):
    """
    Wrapper function to execute asyncio coroutines in threads.
    """
    asyncio.run(coro(*args))

    
def execute_command_in_thread(function, coro, *args):
    """
    Execute a command in a separate thread while allowing cancellation of
    the currently running task.
    """
    global current_task_thread
    stop_event.set()  # Signal the stop event to interrupt ongoing tasks
    if current_task_thread:
        current_task_thread.join()  # Wait for the previous thread to finish

    stop_event.clear()  # Clear the stop event for the new task
    current_task_thread = threading.Thread(target=function, args=(coro, *args))
    current_task_thread.start()


def execute_command(controller, command_info):
    """
    Dispatch drone commands to separate threads for execution.
    """
    if not command_info:
        return

    action = command_info.get('action')
    print(f"Executing action: {action}")

    movement_distance = 4

    # Map actions to functions and their arguments
    actions_map = {
        'stop': (controller.stop, ),
        'takeoff': (controller.takeoff, ),
        'land': (controller.land, ),
        'up': (controller.translate_to_position_local, 0, 0, -movement_distance),
        'down': (controller.translate_to_position_local, 0, 0, movement_distance),
        'forward': (controller.translate_to_position_local, movement_distance, 0, 0),
        'backward': (controller.translate_to_position_local, -movement_distance, 0, 0),
        'left': (controller.translate_to_position_local, 0, -movement_distance, 0),
        'right': (controller.translate_to_position_local, 0, movement_distance, 0),
        'rotate_left': (controller.rotate, 'left'),
        'rotate_right': (controller.rotate, 'right')
    }

    if action in actions_map:
        coro = actions_map[action][0]  # Extract coroutine function
        args = actions_map[action][1:]  # Extract arguments (if any)
        execute_command_in_thread(thread_wrapper, coro, *args)
    else:
        print("Command not recognized.")



async def process_voice_commands():
    """Process voice commands asynchronously"""
    command_processor = DroneCommandProcessor()
    controller = DroneController(client)
    
    while True:
        try:
            command_text = get_voice_command()
            timer.start()
            if command_text:
                translated_text = translate_to_english(command_text)
                if translated_text:
                    print(f"Processing command: {translated_text}")

                    command_info = command_processor.process_command(translated_text)
                    if command_info:
                        execute_command(controller, command_info)
                        #await execute_command(controller, command_info)
                    else:
                        print("Command not recognized.")
            print("Time taken: ", timer.end())
            await asyncio.sleep(0.1)
        except KeyboardInterrupt:
            print("\nShutting down...")
            execute_command(controller, {'action': 'stop'})
            #await controller.stop()
            client.armDisarm(False)
            client.enableApiControl(False)
            break
        except Exception as e:
            print(f"Error in command processing: {str(e)}")
            continue

def get_voice_command():
    """Function to capture voice input and transcribe it."""
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
        print("Could not request results from speech recognition service.")
        return None

def translate_to_english(text):
    """Translate the recognized text to English using Google Translate."""
    try:
        translated = translator.translate(text, src=source_language, dest='en')
        print(f"Translated to English: {translated.text}")
        return translated.text.lower()
    except Exception as e:
        print(f"Translation error: {e}")
        return None

if __name__ == "__main__":
    try:
        asyncio.run(process_voice_commands())
    except KeyboardInterrupt:
        print("\nProgram terminated by user")
    finally:
        client.armDisarm(False)
        client.enableApiControl(False)