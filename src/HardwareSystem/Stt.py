import speech_recognition as sr
from BaseApp import BaseApp

# ===== Speech Recognition App =====
class SpeechRecognitionApp(BaseApp):
    """음성을 텍스트로 변환하는 앱"""

    def __init__(self, language='ko-KR', adjustment_duration=1):
        super().__init__(language=language)
        self.adjustment_duration = adjustment_duration
        self.recognizer = sr.Recognizer()

    def initialize(self):
        self.initialized = True

    def validate_input(self):
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
            return text  # ← True 대신 실제 텍스트를 반환하는 게 상위 사용처에 편함
        except Exception as e:
            print(f"음성 인식 오류: {e}")
            return None

    def cleanup(self):
        """STT는 파일 리소스가 없으므로 현재는 비워둠."""
        pass
