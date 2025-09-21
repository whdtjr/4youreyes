import BaseApp
import pygame
import sys
from Stt import gTTS
import io

# ===== Text-to-Speech App =====
class TextToSpeechApp(BaseApp):
    """텍스트를 음성으로 변환하는 앱"""

    def __init__(self, language='ko', frequency=22050, size=-16, channels=2, buffer=512):
        super().__init__(language=language)
        self.frequency = frequency
        self.size = size
        self.channels = channels
        self.buffer = buffer
        self.pygame_initialized = False

    def initialize(self):
        try:
            pygame.mixer.pre_init(
                frequency=self.frequency,
                size=self.size,
                channels=self.channels,
                buffer=self.buffer
            )
            pygame.mixer.init()
            self.pygame_initialized = True
            self.initialized = True
        except Exception as e:
            print(f"pygame 초기화 오류: {e}")
            self.pygame_initialized = False

    def validate_input(self, args=None):
        if args is None:
            args = sys.argv
        if len(args) < 2:
            return None
        text = " ".join(args[1:]).strip()
        return text if len(text) > 1 else None

    def process(self, text, slow=False):
        try:
            tts = gTTS(text=text, lang=self.language, slow=slow)
            fp = io.BytesIO()
            tts.write_to_fp(fp)
            fp.seek(0)
            pygame.mixer.music.load(fp, "mp3")
            pygame.mixer.music.play()
            clock = pygame.time.Clock()
            while pygame.mixer.music.get_busy():
                clock.tick(10)
            return True
        except Exception as e:
            print(f"TTS 처리 오류: {e}")
            return False

    def cleanup(self):
        try:
            if self.pygame_initialized:
                if pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop()
                pygame.mixer.quit()
                self.pygame_initialized = False
        except Exception as e:
            print(f"리소스 정리 오류: {e}")