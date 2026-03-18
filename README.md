🤖 FRIDAY: Multimodal Agentic AI Interface

A Next-Generation HCI System with Holographic HUD, Gesture Tracking, and Voice Fusion.

FRIDAY (Functional Responsive Intelligent Digital Assistant System) is an autonomous AI agent designed to eliminate physical peripherals. It fuses Computer Vision (Hand Landmarks) and Natural Language Processing (Speech Intent) to provide a seamless, contactless workstation experience.

🚀 Key Features:

👁️ Precision Vision System
> Holographic HUD: A transparent Tkinter-based overlay providing a virtual QWERTY interface directly on your desktop.
> Hybrid Tracking: * Command Mode: Uses V-Gesture for standard mouse navigation and clicking.
> Typing Mode: Uses the Index Finger as a high-precision stylus with a Minor-Hand Palm safety lock.
> System Gestures: Integrated Pinch-to-Zoom logic for Volume, Brightness, and Vertical/Horizontal scrolling.

🎙️ Voice & Brain Integration
> Multimodal Fusion: Simultaneous processing of hand coordinates and voice commands using Python threading.
> Intent Parsing: A rule-based brain handler (ready for LLM integration) that maps natural language to system-level execution.
> Speech Synthesis: Real-time feedback using gTTS with support for English and Hindi commands.


🛠️ Tech Stack
Core: Python 3.8+
Vision: OpenCV, MediaPipe (21-point Landmark Tracking)
Automation: PyAutoGUI (System API Hooks)
NLP: SpeechRecognition (Google Web API), gTTS
Interface: Tkinter (Transparent Canvas API)
Audio: Pygame Mixer


📦 Setup & Installation:
> Clone the Repository:
Bash:
git clone https://github.com/himubhatt/Friday-Omni-Bot.git
cd Friday-Omni-Bot

> Initialize Environment:
Bash:
python -m venv venv
.\venv\Scripts\activate

> Install Dependencies:
Bash
pip install -r requirements.txt

Note: If PyAudio fails on Windows, use pip install pipwin && pipwin install pyaudio.

> Run the Interface:
Bash:
python src/main_bot.py


🖖 Gesture Guide
Gesture                                  Action
Double Palm (2s)              Toggle Holographic HUD (Keyboard)
V-Gesture                     Standard Mouse Navigation
Middle Finger Up              Left Click
Index Finger Up               Right Click
Pinch (Major Hand)            Volume (Vertical) / Brightness (Horizontal)
Pinch (Minor Hand)            Scroll (Vertical/Horizontal)
Minor Palm + Major Index      Precision Typing Mode


📂 Project Structure
> src/main_bot.py: The Central Orchestrator (Threading logic).
> src/vision_module.py: Mediapipe tracking and HUD rendering.
> src/voice_module.py: Voice I/O and speech synthesis.
> src/brain_handler.py: Intent mapping and system execution logic.

🔮 Future Roadmap:
[ ] Edge LLM: Integrate Gemma-2b for offline, local intelligence.
[ ] Hardware: Link to myCobot 280 Pi for physical task execution.
[ ] Biometrics: Add Face-ID login to the main boot sequence.



Developed by Himanshu Bhatt & Gaurav Prasad Raturi,  Diploma Computer Science Engineering Students