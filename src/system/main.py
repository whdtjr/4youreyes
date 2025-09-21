import time
import base64
import threading
import cv2
import numpy as np
from contextlib import contextmanager
from TCPserver import PersistentTCPServer, check_voice_commands
from ConditionCheck import Condition_check
from HardwareSystem.HardwareResourceManager import hardware_manager
  
class RSUtils:


    @staticmethod
    def to_base64_jpeg(img_bgr: np.ndarray, width: int, quality: int) -> str:
        h, w = img_bgr.shape[:2]
        if w != width:
            scale = width / w
            img_bgr = cv2.resize(img_bgr, (width, int(h*scale)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", img_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if not ok:
            raise RuntimeError("JPEG 인코딩 실패")
        return base64.b64encode(buf).decode("ascii")

    @staticmethod
    def depth_to_xyz(x, y, depth_z16: np.ndarray, intrin, depth_scale: float):
        """픽셀(x,y)에서 3D 좌표(m) 계산 (z16*scale 사용). z가 0이면 NaN."""
        z = float(depth_z16[y, x]) * depth_scale
        if z <= 0: return (np.nan, np.nan, 0.0)
        fx, fy, ppx, ppy = intrin.fx, intrin.fy, intrin.ppx, intrin.ppy
        X = (x - ppx) * z / fx
        Y = (y - ppy) * z / fy
        return (X, Y, z)

    @staticmethod
    def overlay_distances(image_bgr, triplet_xyz, color=(0,255,0)):
        (cx,cy,cz), (lx,ly,lz), (rx,ry,rz) = triplet_xyz
        pairs = [(f"Center: {cz:.2f} m", (10, 30)),
                 (f"Left:   {lz:.2f} m", (10, 60)),
                 (f"Right:  {rz:.2f} m", (10, 90))]
        for text, pos in pairs:
            cv2.putText(image_bgr, text, pos, cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)





        
if __name__ == '__main__':
    try:
        server = PersistentTCPServer(host='0.0.0.0', port=5002)
        condition = Condition_check()

        # 모든 주요 기능을 별도의 데몬 스레드로 실행
        server_thread = threading.Thread(target=server.start, daemon=True)
        condition_thread = threading.Thread(target=condition.run, daemon=True)
        text_checker_thread = threading.Thread(target=check_voice_commands, args=(server, hardware_manager), daemon=True)
        
        server_thread.start()
        condition_thread.start()
        text_checker_thread.start()

        print("✅ 모든 스레드가 시작되었습니다. Ctrl+C로 종료하세요.")
        # 메인 스레드는 데몬 스레드들이 실행되는 동안 대기
        while True:
            time.sleep(1)
        
    except KeyboardInterrupt:
        print("\n🛑 시스템 종료 요청을 받았습니다...")
        # 스레드 종료 신호 먼저 보내기
        condition.stop_flag = True
        condition.llm.stop_flag = True
        
    finally:
        print("🧹 하드웨어 리소스 정리 중...")
        hardware_manager.cleanup_all()
        print("✅ 시스템 종료 완료")
    


