import sys
import io
import queue
import threading
import time
import pygame
from gtts import gTTS  # ← 수정: Stt가 아니라 gtts 모듈에서 import
from BaseApp import BaseApp

class TextToSpeechApp(BaseApp):
    """
    안전한 TTS: 인스턴스 1 + 워커 스레드 1 + 큐
    - process(text): 비블로킹, 텍스트를 큐에 넣기만 함.
    - 내부 워커가 gTTS 합성(mp3) → pygame.mixer 재생을 순차 처리.
    - pygame 전역 리소스는 1회 초기화/정리.
    """
    def __init__(self, language='ko', frequency=22050, size=-16, channels=2, buffer=512, queue_size=64):
        super().__init__(language=language)
        self.frequency = frequency
        self.size = size
        self.channels = channels
        self.buffer = buffer

        self._q = queue.Queue(maxsize=queue_size)
        self._stop = threading.Event()
        self._worker = None
        self._lock = threading.Lock()
        self._pygame_ok = False
        self._slow = False  # gTTS 속도 옵션

    def initialize(self):
        with self._lock:
            if self.initialized:
                return
            try:
                # 가능하면 메인 스레드에서 호출 권장(일부 OS/SDL 제약)
                pygame.mixer.pre_init(
                    frequency=self.frequency,
                    size=self.size,
                    channels=self.channels,
                    buffer=self.buffer
                )
                pygame.mixer.init()
                self._pygame_ok = True
            except Exception as e:
                print(f"[TTS] pygame 초기화 오류: {e}")
                self._pygame_ok = False
                # pygame이 실패해도 워커는 띄우지 않음
                return

            # 워커 시작
            self._worker = threading.Thread(target=self._loop, name="TTSWorker", daemon=True)
            self._worker.start()

            self.initialized = True
            print("[TTS] 초기화 완료, 워커 스레드 시작.")

    def set_slow(self, slow: bool):
        """gTTS 합성 속도 설정 (True: 느리게)"""
        self._slow = bool(slow)

    def process(self, text: str, slow: bool | None = None) -> bool:
        if not text or not text.strip():
            return False
        if not self.initialized:
            # 사용자가 initialize 안 불렀다면 안전하게 내부에서 한번 시도
            self.initialize()
            if not self.initialized:
                return False

        payload = (text.strip(), self._slow if slow is None else bool(slow))
        try:
            self._q.put_nowait(payload)
            return True
        except queue.Full:
            # 백프레셔 정책: 가장 오래된 것 drop 후 push
            try:
                _ = self._q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._q.put_nowait(payload)
                return True
            except queue.Full:
                return False

    def flush(self):
        """대기열 비우기(재생 중인 항목은 건드리지 않음)"""
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass

    def stop(self):
        """현재 재생 중지(대기열은 유지)"""
        if self._pygame_ok:
            try:
                if pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop()
            except Exception as e:
                print(f"[TTS] stop 오류: {e}")
    
    def _loop(self):
        """워커: 큐에서 꺼내 순차 합성/재생"""
        while not self._stop.is_set():
            try:
                text, slow = self._q.get(timeout=0.5)
            except queue.Empty:
                continue

            # 1) gTTS 합성(mp3 메모리)
            mp3_fp = io.BytesIO()
            try:
                t0 = time.time()
                tts = gTTS(text=text, lang=self.language, slow=slow)
                tts.write_to_fp(mp3_fp)
                mp3_fp.seek(0)
                synth_dur = time.time() - t0
            except Exception as e:
                print(f"[TTS] 합성 오류: {e} (텍스트: {text[:40]!r}...)")
                continue

            # 2) pygame 재생(단일 워커이므로 자연스럽게 직렬화)
            if not self._pygame_ok:
                print("[TTS] pygame 사용 불가 상태. 합성 결과는 재생하지 않습니다.")
                continue

            try:
                pygame.mixer.music.load(mp3_fp, "mp3")
                pygame.mixer.music.play()
                # 바쁘게 도는 루프 대신 짧게 sleep
                while pygame.mixer.music.get_busy() and not self._stop.is_set():
                    time.sleep(0.05)
            except Exception as e:
                print(f"[TTS] 재생 오류: {e}")

    def cleanup(self):
        """워커 종료 및 pygame 정리"""
        with self._lock:
            self._stop.set()
            if self._worker:
                self._worker.join(timeout=2.0)
                self._worker = None
            if self._pygame_ok:
                try:
                    if pygame.mixer.music.get_busy():
                        pygame.mixer.music.stop()
                    pygame.mixer.quit()
                except Exception as e:
                    print(f"[TTS] 정리 오류: {e}")
                self._pygame_ok = False
            self.initialized = False
            print("[TTS] 정리 완료.")
