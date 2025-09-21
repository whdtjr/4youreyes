from HardwareResourceManager import hardware_manager
from SafetyEventHandler import safety_events, threading
from Llm import Llm
from collections import deque
import time
import queue
from system import RSUtils


class Condition_check:
    """카메라 캡처 -> 이미지 분석 -> 위험 판단 -> 음성 알림 시스템"""
    
    def __init__(self, analysis_interval=20.0):
        # 컴포넌트 초기화
        self.hardware_manager = hardware_manager
        self.llm = Llm()
        self.safety_events = safety_events  # 전역 이벤트 핸들러 참조
        # 설정값 통합
        self.TARGET_WIDTH = 640
        self.JPEG_QUALITY = 82
        self.ANALYSIS_INTERVAL = analysis_interval
        self.ADAPTIVE_FACTOR = 1.2
        self.PRINT_EVERY = 1.0
        self.VOICE_COOLDOWN = 10.0
        
        # 상태 관리
        self.stop_flag = False
        self.last_voice_alert = 0
        self.analysis_history = deque(maxlen=self.llm.MAJORITY_WINDOW)
        
        print(f"안전 모니터링 시스템 초기화 완료 - 모델: {self.llm.MODEL_NAME}")
        print(f"분석 주기: {self.ANALYSIS_INTERVAL}초")

    def run(self):
        """메인 실행 함수"""
        print("=== 안전 모니터링 시스템 시작 ===")
        
        t_capture = threading.Thread(target=self.capture_loop, daemon=True)
        t_analyze = threading.Thread(target=self.analyze_loop, daemon=True)
        
        t_capture.start()
        t_analyze.start()
        
        try:
            while not self.stop_flag:
                try:
                    majority, desc, took, timestamp = self.llm.result_q.get(timeout=1.0)
                    
                    time_str = time.strftime('%H:%M:%S', time.localtime(timestamp))
                    print(f"[{time_str}] 판정: {majority} | 처리시간: {took:.2f}s")
                    
                    if majority == "위험":
                        self.safety_events.on_danger_detected(desc, timestamp)
                        self._handle_danger_alert(desc, timestamp)
                        
                except queue.Empty:
                    pass
                    
                time.sleep(0.5)
                
        except KeyboardInterrupt:
            print("\n시스템 종료 요청을 받았습니다...")
            
        finally:
            self._cleanup(t_capture, t_analyze)

    def capture_loop(self):
        """허브에서 프레임 구독 → 20초마다 최신 프레임만 큐에 투입"""
        print("RealSense Hub 구독 기반 캡처 루프 시작")

        hub = self.hardware_manager.get_camera()
        q = hub.subscribe(maxlen=1)
        try:
            last_push_t = 0.0

            while not self.stop_flag:
                if not q:
                    time.sleep(0.01)
                    continue

                try:
                    ts, color_bgr, depth_z16 = q[-1]
                except (IndexError, ValueError):
                    time.sleep(0.01)
                    continue

                now = time.monotonic()
                # 🔴 모션 기준 제거: 20초 주기로만 밀어넣기
                if now - last_push_t >= self.ANALYSIS_INTERVAL:
                    frame = color_bgr

                    # ✅ 큐에 남아있는 예전 프레임 모두 폐기(항상 최신 한 장만 유지)
                    try:
                        while True:
                            self.llm.frame_q.get_nowait()
                    except queue.Empty:
                        pass

                    try:
                        self.llm.frame_q.put_nowait(frame)
                        last_push_t = now
                        print(f"[{time.strftime('%H:%M:%S')}] 이미지 큐 푸시 (every {int(self.ANALYSIS_INTERVAL)}s)")
                    except queue.Full:
                        # maxsize=1 이지만, 혹시 모를 레이스 컨디션 대비
                        try:
                            _ = self.llm.frame_q.get_nowait()
                            self.llm.frame_q.put_nowait(frame)
                            last_push_t = now
                        except queue.Empty:
                            pass

                time.sleep(0.01)
        finally:
            hub.unsubscribe(q)

    def analyze_loop(self):
        print("이미지 분석 루프 시작")
        while not self.stop_flag:
            try:
                frame = self.llm.frame_q.get(timeout=5.0)
            except queue.Empty:
                continue

            try:
                b64_image = RSUtils.to_base64_jpeg(frame, self.TARGET_WIDTH, self.JPEG_QUALITY)

                print(f"[{time.strftime('%H:%M:%S')}] 🔍 AI 모델 분석 시작...")
                description, analysis_time = self.llm.ollama_describe(b64_image, self.llm.MODEL_NAME)

                regex_result = self.llm.classify_text_regex(description)
                nli_result = self.llm.nli_danger(description, threshold=0.6)
                individual_result = "위험" if "위험" in (regex_result, nli_result) else "안전"

                self.analysis_history.append(individual_result)
                danger_votes = sum(1 for x in self.analysis_history if x == "위험")
                majority_result = "위험" if danger_votes > len(self.analysis_history) / 2 else "안전"

                self.llm.result_q.put_nowait((majority_result, description, analysis_time, time.time()))
                print(f"📝 AI 분석 결과: {description}")
                print(f"🎯 안전 판정 - 개별: {individual_result}, 최종: {majority_result}")
                print(f"⏱️  처리 시간: {analysis_time:.2f}초")
                print("-" * 60)
            except Exception as e:
                print(f"분석 오류: {e}")
            finally:
                frame = None


    def _stabilize_camera(self, camera, frames=10):  # <- 파라미터 추가
        """카메라 안정화"""
        print("📷 카메라 안정화 중...")
        for _ in range(frames):
            try:
                camera.pipeline.wait_for_frames()  # <- 수정
            except:
                break

    def _handle_danger_alert(self, description, timestamp):
        """위험 상황 알림 처리"""
        current_time = time.time()
        
        if current_time - self.last_voice_alert < self.VOICE_COOLDOWN:
            return
        
        # 🔽 'with' 없이 직접 인스턴스 가져오기
        speaker = self.hardware_manager.get_speaker()
        try:
            danger_keywords = self._extract_danger_keywords(description)
            
            if danger_keywords:
                voice_message = f"위험이 감지되었습니다. {', '.join(danger_keywords)}가 발견되었습니다. 주의하세요."
            else:
                voice_message = "위험한 상황이 감지되었습니다. 주의하세요."
            
            print(f"🚨 위험 알림: {voice_message}")
            
            success = speaker.process(voice_message)
            
            if success:
                self.last_voice_alert = current_time
                print("🔊 음성 알림 출력 완료")
                
        except Exception as e:
            print(f"위험 알림 처리 오류: {e}")

    def _extract_danger_keywords(self, description):
        """위험 키워드 추출"""
        danger_words = []
        text_lower = description.lower()
        
        keyword_map = {
            'fire': '화재', 'flame': '화염', 'smoke': '연기',
            'weapon': '무기', 'knife': '칼', 'gun': '총',
            'explosion': '폭발', 'fall': '낙하', 'danger': '위험',
            'hazard': '위험요소', 'crash': '충돌', 'collision': '사고'
        }
        
        for eng_word, kor_word in keyword_map.items():
            if eng_word in text_lower:
                danger_words.append(kor_word)
                
        return danger_words

    def _cleanup(self, t_capture, t_analyze):
        """시스템 정리"""
        print("🔄 시스템 정리 중...")
        
        self.stop_flag = True
        self.llm.stop_flag = True
        
        if t_capture.is_alive():
            t_capture.join(timeout=3.0)
        if t_analyze.is_alive():
            t_analyze.join(timeout=3.0)
        
        # 리소스 매니저를 통한 정리는 메인에서 처리되므로 제거
        print("✅ 시스템 종료 완료")