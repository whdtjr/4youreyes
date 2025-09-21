import speech_recognition as sr
import tempfile
from gtts import gTTS
import os
from BaseApp import time, BaseApp

# ===== Speech Recognition App =====
class SpeechRecognitionApp(BaseApp):
    """음성을 텍스트로 변환하는 앱"""

    def __init__(self, language='ko-KR', tts_language='ko', adjustment_duration=1):
        super().__init__(language=language)
        self.tts_language = tts_language
        self.adjustment_duration = adjustment_duration
        self.recognizer = sr.Recognizer()
        self.temp_files = []

    def initialize(self):
        self.initialized = True

    def _create_temp_file(self, suffix=".mp3"):
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp_file.close()
        self.temp_files.append(temp_file.name)
        return temp_file.name

    def speak_message(self, message, slow=False):
        try:
            tts = gTTS(text=message, lang=self.tts_language, slow=slow)
            temp_file = self._create_temp_file(".mp3")
            tts.save(temp_file)
            os.system(f'start "" "{temp_file}"' if os.name == 'nt' else f'mpg123 "{temp_file}" > /dev/null 2>&1')
            time.sleep(2)
            return True
        except Exception as e:
            print(f"TTS 오류: {e}")
            return False

    def validate_input(self, welcome_message="3초 뒤에 말을 해주세요"):
        if welcome_message:
            self.speak_message(welcome_message)
        with sr.Microphone() as source:
            print("배경 소음을 조정하는 중...")
            self.recognizer.adjust_for_ambient_noise(source, duration=self.adjustment_duration)
            print("음성 입력을 기다리는 중...")
            try:
                audio = self.recognizer.listen(source)
                return audio
            except Exception as e:
                print(f"음성 입력 오류: {e}")
                return None

    def process(self, audio):
        try:
            text = self.recognizer.recognize_google(audio, language=self.language)
            print(f"인식된 텍스트: {text}")
            return True
        except Exception as e:
            print(f"음성 인식 오류: {e}")
            return False

    def cleanup(self):
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as e:
                print(f"임시 파일 삭제 오류: {e}")
        self.temp_files.clear()
        
