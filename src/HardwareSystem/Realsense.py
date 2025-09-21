import cv2
import pyrealsense2 as rs
from system.SafetyEventHandler import threading
from collections import deque
import numpy as np
from BaseApp import time



# === Hub: RealSense를 1번만 열어 모두에게 배포 ===
class RealSenseHub:
    def __init__(self, width=640, height=480, fps=30):
        self.width, self.height, self.fps = width, height, fps
        self.pipeline = rs.pipeline()
        self.config = rs.config()
        self.config.enable_stream(rs.stream.depth, width, height, rs.format.z16, fps)
        self.config.enable_stream(rs.stream.color, width, height, rs.format.bgr8, fps)
        self._align = rs.align(rs.stream.color)

        self._lock = threading.Lock()
        self._subs = []              # each: deque(maxlen=1)
        self._running = False
        self._thread = None

        self.depth_scale = None
        self.depth_intrin = None

    def start(self):
        with self._lock:
            if self._running:
                return
            profile = self.pipeline.start(self.config)

            # 센서 정보 (스케일/내부파라미터 캐시)
            dev = profile.get_device()
            depth_sensor = dev.first_depth_sensor()
            self.depth_scale = float(depth_sensor.get_depth_scale())
            self.depth_intrin = (profile.get_stream(rs.stream.depth)
                                         .as_video_stream_profile().get_intrinsics())
            # 안정화 약간
            for _ in range(8):
                try: self.pipeline.wait_for_frames()
                except: break

            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def subscribe(self, maxlen=1) -> deque:
        q = deque(maxlen=maxlen)
        with self._lock:
            self._subs.append(q)
            if not self._running:
                self.start()
        return q

    def unsubscribe(self, q: deque):
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def get_info(self):
        """소비자들이 3D 변환 등에 쓰는 메타."""
        return {
            "width": self.width, "height": self.height, "fps": self.fps,
            "depth_scale": self.depth_scale, "depth_intrinsics": self.depth_intrin
        }

    def _loop(self):
        while self._running:
            try:
                frames = self.pipeline.wait_for_frames()
                frames = self._align.process(frames)
                df = frames.get_depth_frame()
                cf = frames.get_color_frame()
                if not df or not cf:
                    continue

                # 💡 RealSense frame은 다음 루프에서 메모리 해제되므로 안전하게 copy
                color_bgr = np.asanyarray(cf.get_data()).copy()
                depth_z16 = np.asanyarray(df.get_data()).copy()
                ts = time.time()

                with self._lock:
                    for q in self._subs:
                        q.append((ts, color_bgr, depth_z16))
            except Exception as e:
                print(f"[Hub] capture error:", e)
                time.sleep(0.01)

    def stop(self):
        with self._lock:
            self._running = False
        try:
            self.pipeline.stop()
        except:
            pass

    def _cleanup(self):
        self.stop()