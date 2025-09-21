from system.SafetyEventHandler import threading
from Realsense import RealSenseHub
from Tts import TextToSpeechApp
from Stt import SpeechRecognitionApp, sr
import queue

class HardwareResourceManager:
    """하드웨어 리소스를 중앙에서 관리하는 싱글톤 클래스"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, 'initialized'):
            return
        
        self.camera_lock = threading.Lock()
        self.speaker_lock = threading.Lock()
        self.mic_lock = threading.Lock()
        
        # 하드웨어 인스턴스들 (지연 초기화)
        self._camera_instance = None
        self._speaker_instance = None
        self._mic_instance = None
        
        self.initialized = True
    
    # 🔽 @contextmanager 제거 및 로직 변경
    def get_camera(self):
        # 카메라 허브는 시작 시 한 번만 초기화되므로 복잡한 락킹 불필요
        if self._camera_instance is None:
            with self.camera_lock:
                if self._camera_instance is None:
                    self._camera_instance = RealSenseHub(width=640, height=480, fps=30)
                    self._camera_instance.start()
        return self._camera_instance
    
    # 🔽 @contextmanager 제거 및 로직 변경
    def get_speaker(self):
        """스피커 리소스를 안전하게 얻기 (인스턴스 반환)"""
        if self._speaker_instance is None:
            with self.speaker_lock:
                if self._speaker_instance is None:
                    print("🔊 스피커 리소스 초기화...")
                    self._speaker_instance = TextToSpeechApp()
                    self._speaker_instance.initialize()
        return self._speaker_instance
    
    # 🔽 @contextmanager 제거 및 로직 변경
    def get_microphone(self):
        """마이크 리소스를 안전하게 얻기 (인스턴스 반환)"""
        if self._mic_instance is None:
            with self.mic_lock:
                if self._mic_instance is None:
                    print("🎤 마이크 리소스 초기화...")
                    self._mic_instance = SpeechRecognitionApp()
                    self._mic_instance.initialize()
        return self._mic_instance
    
    def cleanup_all(self):
        """모든 리소스 정리"""
        with self.camera_lock:
            if self._camera_instance:
                self._camera_instance._cleanup()
        
        with self.speaker_lock:
            if self._speaker_instance:
                self._speaker_instance.cleanup()
        
        with self.mic_lock:
            if self._mic_instance:
                self._mic_instance.cleanup()
                
class VoiceCommandHandler:
    """
    마이크 녹음을 제어하고 음성을 텍스트로 변환하는 작업을 처리하는 클래스.
    (AttributeError를 수정한 버전)
    """
    def __init__(self):
        self.stt_app = SpeechRecognitionApp()
        self.is_recording = False
        self.stop_event = threading.Event()
        self.recording_thread = None
        self.text_queue = queue.Queue()

    def _record_and_transcribe_loop(self):
        """[백그라운드 스레드] 마이크 입력을 지속적으로 듣고 텍스트로 변환합니다."""
        mic = sr.Microphone()
        with mic as source:
            # --- 수정된 부분 1 ---
            # self.stt_app.recognizer 객체의 메서드를 호출해야 합니다.
            self.stt_app.recognizer.adjust_for_ambient_noise(source)
            # --------------------
            print("🎤 (백그라운드) 음성 녹음 스레드 시작. 입력을 기다립니다...")

            while not self.stop_event.is_set():
                try:
                    # --- 수정된 부분 2 ---
                    audio = self.stt_app.recognizer.listen(source, timeout=1.0, phrase_time_limit=5)
                    text = self.stt_app.recognizer.recognize_google(audio, language=self.stt_app.language)
                    # --------------------
                    if text:
                        print(f"🔊 (백그라운드) 음성 인식 성공: {text}")
                        self.text_queue.put(text)
                except sr.WaitTimeoutError:
                    continue
                except Exception as e:
                    print(f"🔥 녹음/인식 중 오류: {e}")
        
        print("🛑 (백그라운드) 음성 녹음 스레드 종료.")
        self.is_recording = False

    # (start_recording, stop_recording, get_transcribed_text 메서드는 변경 없음)
    def start_recording(self):
        if self.is_recording:
            print("⚠️ 이미 녹음이 진행 중입니다.")
            return
        self.is_recording = True
        self.stop_event.clear()
        self.recording_thread = threading.Thread(target=self._record_and_transcribe_loop)
        self.recording_thread.start()
        print("▶️ 음성 녹음을 시작합니다.")

    def stop_recording(self):
        if not self.is_recording:
            print("⚠️ 녹음 중이 아닙니다.")
            return
        self.stop_event.set()
        if self.recording_thread:
            self.recording_thread.join(timeout=2.0)
        self.is_recording = False
        print("⏹️ 음성 녹음을 중지합니다.")

    def get_transcribed_text(self):
        try:
            return self.text_queue.get_nowait()
        except queue.Empty:
            return None
        
hardware_manager = HardwareResourceManager()