import time
from HardwareResourceManager import hardware_manager
from TCPserver import socket
from Realsense import cv2
import os

class ClothCaptureClient: # <-- 이름 변경됨
    """
    저장된 이미지 파일을 "IMAGE:바이너리:크기" 포맷으로 전송하는 클라이언트
    """
    def __init__(self, third_party_host, third_party_port, auth_string):
        self.hardware_manager = hardware_manager
        self.forward_host = third_party_host
        self.forward_port = third_party_port
        self.auth_string = auth_string
        self.image_filename = "captured_rgb.jpg"

    def _forward_image_mixed_protocol(self, filepath):
        """디스크의 이미지 파일을 지정된 혼합 프로토콜로 전송합니다."""
        print(f"📡 제3서버({self.forward_host}:{self.forward_port})로 '{filepath}' 파일 전송을 시작합니다.")
        
        try:
            with open(filepath, 'rb') as f:
                image_bytes = f.read()
            
            image_size = len(image_bytes)
            payload = b"IMAGE:" + image_bytes + b":" + str(image_size).encode('utf-8')
            
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
                client_socket.connect((self.forward_host, self.forward_port))
                client_socket.sendall(payload)
                
                response = client_socket.recv(1024).decode('utf-8')
                print(f"📨 제3서버 응답: {response}")
                return "SUCCESS" in response.upper()

        except FileNotFoundError:
            print(f"🔥 [오류] 전송할 파일을 찾을 수 없습니다: {filepath}")
            return False
        except Exception as e:
            print(f"🔥 [오류] 제3서버 전송 중 오류 발생: {e}")
            return False

    def run(self):
        """캡처, 파일 읽기, 전송의 전체 과정을 실행합니다."""
        print("\n--- 캡처 및 전송 작업 시작 ---")
        
        hub = self.hardware_manager.get_camera()   # RealSenseHub
        q = hub.subscribe(maxlen=1)
        try:
            # 최신 프레임 도착 대기 (최대 2초)
            t0 = time.time()
            frame = None
            while time.time() - t0 < 2.0:
                if q:
                    _, frame, depth = q[-1]
                    break
                time.sleep(0.01)
            if frame is None:
                print("❌ 작업 실패: 프레임을 받지 못했습니다.")
                return False

            # 파일로 저장 후 전송
            cv2.imwrite(self.image_filename, frame)
            forward_success = self._forward_image_mixed_protocol(self.image_filename)
            try:
                if os.path.exists(self.image_filename):
                    os.remove(self.image_filename)
                    print(f"🗑️ 임시 파일 '{self.image_filename}'이 삭제되었습니다.")
            except Exception as e:
                print(f"임시 파일 삭제 오류: {e}")

            if forward_success:
                print("✅ 작업 성공: 이미지 캡처 및 전송이 완료되었습니다.")
                return True
            else:
                print("❌ 작업 실패: 이미지 전송에 실패했습니다.")
                return False
        finally:
            hub.unsubscribe(q)