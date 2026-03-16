# Omni-Bot

An all-in-one AI bot with vision, voice recognition, speech synthesis, and a central brain handler.

## Features
- **Vision**: Camera feed and basic object detection using OpenCV.
- **Voice**: Speech-to-text (Google) and text-to-speech.
- **Brain**: Rule-based processing (extendable to LLM).

## Setup
1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
   Note: PyAudio may require additional setup on Windows (use `pip install pipwin && pipwin install pyaudio`).

2. Run the bot:
   ```
   cd Omni-Bot
   python src/main_bot.py
   ```

## Modules
- `src/vision_module.py`: Computer vision tasks.
- `src/voice_module.py`: Voice I/O.
- `src/brain_handler.py`: Decision making.
- `src/main_bot.py`: Orchestrates everything.

## Usage
- Speak commands like "hello", "vision", or "exit".
- Grant microphone/camera permissions.

## Extend
- Integrate LLM (e.g., OpenAI) in `brain_handler.py`.
- Advanced vision with YOLO/TensorFlow.
- Custom wake words.

Built with Python 3.8+.

