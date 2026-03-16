# Omni-Bot Dependency Fix Plan

## Steps to Complete:

- [x] Step 1: Create Python virtual environment (`python -m venv venv`) - DONE
- [ ] Step 2: Activate virtual environment (`venv\\Scripts\\activate`)
- [x] Step 3: Edit requirements.txt to use compatible versions (updated with protobuf)
- [ ] Step 4: Upgrade pip (`pip install --upgrade pip`)
- [ ] Step 5: Install dependencies (`pip install -r requirements.txt`)
- [ ] Step 6: Test imports (`python -c "import cv2, mediapipe, speech_recognition, pyttsx3, pyaudio, google.protobuf; print('All deps OK')"` )
- [ ] Step 7: Test run bot (`python src/main_bot.py`)

**Fixed:** Added `protobuf>=5.28.0` (required by mediapipe for google.protobuf).

**Install now:**
```
venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

Test imports, then run bot. No more ModuleNotFoundError.
