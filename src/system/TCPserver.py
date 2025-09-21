from HardwareSystem.HardwareResourceManager import HardwareResourceManager, VoiceCommandHandler
from HardwareSystem.BaseApp import time
from SafetyEventHandler import safety_events
from HardwareSystem.HardwareResourceManager import hardware_manager
import socket
import re
import os
from SafetyEventHandler import threading
from HardwareSystem.HardwareResourceManager import cv2

class PersistentTCPServer:
    """
    제어 클라이언트의 명령을 받아, C서버로 이미지 캡처 및 전송까지 모두 처리하는 통합 서버
    """
    def __init__(self, host='0.0.0.0', port=5002):
        self.host = host
        self.port = port
        self.server_socket = None
        self.safety_events = safety_events
        # 제어 클라이언트용 인증 정보
        self.control_client_credentials = { 
            '8': 'passwd' 
        }
        self.voice_handler = VoiceCommandHandler()
        # C언어 서버 접속용 정보
        self.C_SERVER_CONFIG = {
            'HOST': '192.168.0.168',      # C 서버 IP
            'PORT': 5000,             # C 서버 포트
            'AUTH_STRING': '[8:passwd]' # C 서버 로그인 인증 문자열
        }
        
        self.hardware_manager = hardware_manager
        self.image_filename = "captured_rgb.jpg"
        print("✅ 올인원(All-in-one) 서버 객체가 생성되었습니다.")

    def _capture_and_send_to_c_server(self, filename="realsense.jpg"): # filename은 C서버에 전달할 이름
        """[최적화] 캡처 후 메모리에서 바로 제3서버로 전송"""
        print("\n--- 캡처 및 전송 작업 시작 (메모리 최적화) ---")
        
        image_bytes = None
        hub = self.hardware_manager.get_camera()
        q = hub.subscribe(maxlen=1)
        try:
            t0 = time.time()
            frame = None
            while time.time() - t0 < 2.0:
                if q:
                    _, color_bgr, _ = q[-1]
                    frame = color_bgr
                    break
                time.sleep(0.01)

            if frame is None:
                print("❌ 작업 실패: 프레임을 받지 못했습니다.")
                return False

            # 🔽 1. 디스크에 저장하는 대신 메모리에서 바로 JPEG로 인코딩
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            if not ok:
                print("🔥 [오류] JPEG 인코딩 실패")
                return False
            image_bytes = buf.tobytes()

        finally:
            hub.unsubscribe(q)

        # 제3서버에 인증 및 이미지 전송
        # 2. 제3서버에 인증 및 이미지 전송 (파일 읽기 과정이 사라짐)
        print(f"📡 제3서버({self.C_SERVER_CONFIG['HOST']}:{self.C_SERVER_CONFIG['PORT']})에 연결을 시도합니다.")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as c_socket:
                c_socket.settimeout(30.0) # 1. 타임아웃을 30초로 늘려 AI 분석 시간을 충분히 확보
                c_socket.connect((self.C_SERVER_CONFIG['HOST'], self.C_SERVER_CONFIG['PORT']))

                # C서버 인증
                auth_string = self.C_SERVER_CONFIG['AUTH_STRING']
                c_socket.sendall(auth_string.encode('utf-8'))
                auth_response = c_socket.recv(1024).decode('utf-8')
                if "Connected!" not in auth_response:
                    print(f"🚫 C서버 로그인 실패: {auth_response.strip()}")
                    return False
                print(f"✅ C서버 로그인 성공: {auth_response.strip()}")

                # 🔽 3. 메모리에 있는 image_bytes를 바로 전송
                header = f"IMAGE:{filename}:{len(image_bytes)}\n"
                c_socket.sendall(header.encode('utf-8'))
                c_socket.sendall(image_bytes)
                print("📦 C서버로 이미지 전송 완료.")

                # 2. C서버의 AI 분석 결과 수신 (강건한 수신 로직으로 변경)
                print("⏳ C서버의 AI 분석 결과 수신 대기...")
                
                response_parts = []
                while True:
                    try:
                        part = c_socket.recv(1024)
                        if not part: # 서버가 연결을 닫으면 recv는 빈 바이트를 반환
                            break
                        response_parts.append(part)
                    except socket.timeout: # 더 이상 데이터가 오지 않으면 타임아웃 발생
                        break
                ai_response = b''.join(response_parts).decode('utf-8')
                ai_response_text = ai_response.strip()
                if ai_response_text.startswith("[AI_Inference]:"):
                    ai_response_text = ai_response_text.split(":", 1)[1].strip()
                    ai_response_text = re.sub(r'\s*IMAGE:[^\s:]+:\d+\s*', ' ', ai_response_text, flags=re.IGNORECASE)
                print(f"🤖 C서버 AI 결과: {ai_response_text}")

                # 요청 3: 받은 텍스트를 스피커로 출력
                if ai_response_text:
                    try:
                        self.hardware_manager.get_speaker().process(ai_response_text)
                    except Exception as e:
                        print(f"🔥 캡처 결과 음성 출력 중 오류: {e}")
                return True

        except Exception as e:
            print(f"🔥 [오류] C서버와 통신 중 오류 발생: {e}")
            return False
        finally:
            # 4. 작업 완료 후 임시 파일 삭제
            if os.path.exists(self.image_filename):
                os.remove(self.image_filename)
                print(f"🗑️ 임시 파일 '{self.image_filename}'이 삭제되었습니다.")

    def _send_text_to_c_server(self, text: str) -> str | None:
        """음성 인식 텍스트를 C 서버로 전송하고 응답을 받습니다."""
        print(f"📡 C 서버({self.C_SERVER_CONFIG['HOST']}:{self.C_SERVER_CONFIG['PORT']})로 텍스트 '{text}' 전송 시도...")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as c_socket:
                c_socket.settimeout(10.0) # 10초 타임아웃
                c_socket.connect((self.C_SERVER_CONFIG['HOST'], self.C_SERVER_CONFIG['PORT']))

                # 1. C 서버 인증
                auth_string = self.C_SERVER_CONFIG['AUTH_STRING']
                c_socket.sendall(auth_string.encode('utf-8'))
                auth_response = c_socket.recv(1024).decode('utf-8')
                if "Connected!" not in auth_response:
                    print(f"🚫 C 서버 로그인 실패: {auth_response.strip()}")
                    return None
                print(f"✅ C 서버 로그인 성공: {auth_response.strip()}")

                # 2. 텍스트 데이터 전송 (프로토콜: "TEXT:내용")

                payload = f"TEXT:{text}\n"
                c_socket.sendall(payload.encode('utf-8'))
                print(f"📦 C 서버로 텍스트 전송 완료: {payload}")

                # 3. C 서버의 응답 수신
                print("⏳ C 서버의 응답 수신 대기...")
                response_text = c_socket.recv(1024).decode('utf-8').strip()
                if response_text:
                    if response_text.startswith("[AI_Inference]:"):
                        response_text = response_text.split(":", 1)[1].strip()
                        response_text = re.sub(r'\s*IMAGE:[^\s:]+:\d+\s*', ' ', response_text, flags=re.IGNORECASE)
                    print(f"🤖 C 서버 응답 수신: '{response_text}'")
                    return response_text
                else:
                    print("⚠️ C 서버로부터 빈 응답을 받았습니다.")
                    return None

        except socket.timeout:
            print("🔥 [오류] C 서버 응답 시간 초과.")
            return None
        except Exception as e:
            print(f"🔥 [오류] C 서버와 텍스트 통신 중 오류 발생: {e}")
            return None

    def _handle_client(self, client_socket, addr):
        """[서버 역할] 제어 클라이언트의 연결 및 명령을 처리하는 메서드"""
        print(f"✅ [제어 클라이언트 연결] {addr[0]}:{addr[1]}")
        
        try:
            # 제어 클라이언트 인증
            auth_data = client_socket.recv(1024)
            if not auth_data: return
            
            auth_string = auth_data.decode('utf-8').strip()
            if ':' not in auth_string:
                client_socket.sendall(b"AUTH_FAILURE: Invalid format")
                return
            user_id, password = auth_string.split(':', 1)
            
            if self.control_client_credentials.get(user_id) == password:
                client_socket.sendall(b"AUTH_SUCCESS")
            else:
                client_socket.sendall(b"AUTH_FAILURE")
                return

            # 명령 처리 루프
            while True:
                command_data = client_socket.recv(1024)
                if not command_data: break
                command = command_data.decode('utf-8').strip().lower()
                print(f"💬 [명령 수신] {addr}: {command}")

                if command == 'capture on':
                    # 중복 제거 - 하나의 메서드만 사용
                    success = self._capture_and_send_to_c_server("realsense.jpg")
                    if success:
                        client_socket.sendall(b"SUCCESS: All tasks completed.")
                    else:
                        client_socket.sendall(b"FAILURE: Task failed.")                     # --- 추가된 부분: 녹음 명령 처리 ---
                elif command == 'recording on':
                    self.voice_handler.start_recording()
                    client_socket.sendall(b"ACK: Recording started.")
                
                elif command == 'recording off':
                    self.voice_handler.stop_recording()
                    client_socket.sendall(b"ACK: Recording stopped.")
                
                elif command == 'quit':
                    client_socket.sendall(b"GOODBYE")
                    break
                else:
                    client_socket.sendall(b"Unknown command.")

        except Exception as e:
            print(f"🔥 [오류] 제어 클라이언트 처리 중 오류: {e}")
        finally:
            client_socket.close()
            print(f"🔌 [연결 종료] {addr} 클라이언트와의 연결을 종료합니다.")
            
    def start(self):
        """서버를 시작하고 클라이언트의 연결을 기다립니다."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        print(f"🚀 서버가 {self.host}:{self.port}에서 제어 클라이언트의 연결을 기다립니다...")
        try:
            while True:
                client_socket, addr = self.server_socket.accept()
                client_thread = threading.Thread(target=self._handle_client, args=(client_socket, addr))
                client_thread.start()
        except KeyboardInterrupt:
            print("\n🛑 서버를 종료합니다.")
        finally:
            self.stop()
            
    def stop(self):
        """서버 소켓을 안전하게 닫습니다."""
        if self.server_socket: 
            self.server_socket.close()
            print("서버 소켓이 닫혔습니다.")

def check_voice_commands(server_instance, hw_manager):
    """
    서버의 VoiceCommandHandler가 변환한 텍스트를 주기적으로 확인하여 출력하는 함수
    음성 인식 텍스트를 C 서버로 보내고, 응답을 스피커로 출력하는 함수.
    """
    while True:
        # 서버 객체를 통해 voice_handler의 큐에 접근
        transcribed_text = server_instance.voice_handler.get_transcribed_text()
        if transcribed_text:
            print(f"\n--- 🗣️ 음성 명령 확인: '{transcribed_text}' ---")
            # 여기서 변환된 텍스트로 다른 작업을 수행할 수 있습니다.
            
            # 1. 인식된 텍스트를 C 서버로 전송
            response_from_c = server_instance._send_text_to_c_server(transcribed_text)
            
            # 2. C 서버로부터 응답이 있으면 스피커로 출력
            if response_from_c:
                print(f"🔊 C 서버 응답을 스피커로 출력합니다: '{response_from_c}'")
                try:
                    speaker = hw_manager.get_speaker()
                    speaker.process(response_from_c)
                except Exception as e:
                    print(f"🔥 스피커 출력 중 오류 발생: {e}")

        time.sleep(0.5) # 0.5초마다 한 번씩 확인