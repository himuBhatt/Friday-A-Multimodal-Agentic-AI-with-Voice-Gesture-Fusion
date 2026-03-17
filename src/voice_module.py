import threading
import queue
import numpy as np
import pyaudio
from faster_whisper import WhisperModel
import ollama
import pyttsx3
import time
from intent_handler import IntentHandler 

class FridayVoice:
    def __init__(self):
        print("⏳ Loading STT Model (This may take a minute on first run)...")
        # 1. Initialize STT (Ears) - Tiny model is best for 8GB RAM
        self.stt_model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
        print("✅ STT Model Loaded.")
        
        # 2. Initialize TTS (Voice)
        self.engine = pyttsx3.init()
        self.engine.setProperty('rate', 180) 
        
        # 3. Initialize Intent Handler (Hands)
        self.handler = IntentHandler()
        
        # 4. Conversation Memory (The "Context Window")
        self.history = [
            {
                'role': 'system', 
                'content': (
                    'You are FRIDAY. Witty, concise, and helpful. Max 15 words. '
                    'If asked to open an app, say "Launching [App Name]" clearly.'
                )
            }
        ]
        
        self.is_running = True
        print("✅ Friday Voice Engine: Ears, Voice & Memory Initialized")

    def speak(self, text):
        """Make Friday talk."""
        print(f"Friday: {text}")
        self.engine.say(text)
        self.engine.runAndWait()

    def ask_brain(self, text):
        """Send transcription with rolling memory to Llama 3.2 1B."""
        try:
            # Add user's words to the history
            self.history.append({'role': 'user', 'content': text})

            # Memory Management: Keep only system prompt + last 4 messages.
            # This stops her from repeating her name every time.
            if len(self.history) > 6:
                self.history = [self.history[0]] + self.history[-4:]

            response = ollama.chat(model='llama3.2:1b', messages=self.history)
            friday_reply = response['message']['content']

            # Store Friday's reply so she remembers what she just said
            self.history.append({'role': 'assistant', 'content': friday_reply})
            
            return friday_reply
        except Exception as e:
            return f"Brain Error: {e}"

    def listen_and_process(self):
        """Captures audio, transcribes, and triggers brain/intents."""
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
                
                # Check if someone is actually speaking (RMS threshold)
                if np.abs(audio_data).mean() > 0.005: 
                    segments, _ = self.stt_model.transcribe(audio_data, beam_size=1)
                    for segment in segments:
                        text = segment.text.strip()
                        if len(text) > 2:
                            print(f"You: {text}")
                            
                            # Global kill-command
                            if "stop friday" in text.lower():
                                self.speak("Understood. Going offline.")
                                self.is_running = False
                                break

                            # 1. Get witty reply from Brain
                            answer = self.ask_brain(text)
                            
                            # 2. Speak the reply
                            self.speak(answer)
                            
                            # 3. Execute the Intent (Launch apps)
                            self.handler.execute(answer)
                
                time.sleep(0.01) # Save CPU cycles
        
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