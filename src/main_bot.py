import threading
from vision_module import GestureController
from voice_module import FridayVoice
from intent_handler import IntentHandler
def start_friday():
    # 1. Initialize Friday's Ears, Brain, and Hands
    voice = FridayVoice()
    handler = IntentHandler()
    
    # 2. Run Vision in a background thread
    # This keeps the mouse moving while Friday listens
    vision = GestureController()
    vision_thread = threading.Thread(target=vision.start, daemon=True)
    vision_thread.start()

    print("🚀 Friday is fully synchronized. Eyes, Ears, and Brain online.")

    try:
        while True:
            # 3. Listen for commands
            # This is the loop we tested in your voice_module
            voice.listen_and_process()
            
    except KeyboardInterrupt:
        print("\n🛑 Shutting down Friday. Systems offline.")

if __name__ == "__main__":
    start_friday()