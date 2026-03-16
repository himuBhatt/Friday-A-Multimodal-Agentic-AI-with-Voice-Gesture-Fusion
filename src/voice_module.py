import threading
import queue
import numpy as np
import pyaudio
from faster_whisper import WhisperModel
import ollama
import pyttsx3
import time
# --- NEW IMPORT ---
# Remove 'from src.intent_handler'
from intent_handler import IntentHandler 

class FridayVoice:
    def __init__(self):
        # 1. Initialize STT (Ears)
        self.stt_model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
        
        # 2. Initialize TTS (Voice)
        self.engine = pyttsx3.init()
        self.engine.setProperty('rate', 180) 
        
        # 3. Initialize Intent Handler (Hands)
        self.handler = IntentHandler()
        
        self.is_running = True
        print("✅ Friday Voice Engine: Ears, Voice & Intents Initialized")

    def speak(self, text):
        print(f"Friday: {text}")
        self.engine.say(text)
        self.engine.runAndWait()

    def ask_brain(self, text):
        try:
            response = ollama.chat(model='llama3.2:1b', messages=[
                {
                    'role': 'system', 
                    'content': 'You are FRIDAY. Witty, concise, and helpful. Max 15 words. If asked to open an app, use the app name clearly in your reply.'
                },
                {'role': 'user', 'content': text}
            ])
            return response['message']['content']
        except Exception as e:
            return f"Brain Error: {e}"

    def listen_and_process(self):
        chunk = 1024
        sample_format = pyaudio.paInt16
        channels = 1
        fs = 16000 
        
        p = pyaudio.PyAudio()
        stream = p.open(format=sample_format, channels=channels, rate=fs,
                        frames_per_buffer=chunk, input=True)

        print("🎙️ Friday is listening (Speak now)...")

        try:
            while self.is_running:
                data = stream.read(chunk, exception_on_overflow=False)
                audio_data = np.frombuffer(data, np.int16).flatten().astype(np.float32) / 32768.0
                
                if np.abs(audio_data).mean() > 0.005: 
                    segments, _ = self.stt_model.transcribe(audio_data, beam_size=1)
                    for segment in segments:
                        text = segment.text.strip()
                        if len(text) > 2:
                            print(f"You: {text}")
                            
                            if "stop friday" in text.lower():
                                self.speak("Understood. Going offline.")
                                self.is_running = False
                                break

                            # 1. Get reply from Brain
                            answer = self.ask_brain(text)
                            
                            # 2. Speak the reply
                            self.speak(answer)
                            
                            # 3. Execute the Intent (Launch app if mentioned)
                            self.handler.execute(answer)
                
                time.sleep(0.01) 
        
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

if __name__ == "__main__":
    friday = FridayVoice()
    try:
        friday.listen_and_process()
    except KeyboardInterrupt:
        print("\n🛑 Friday is going to sleep. Goodbye!")