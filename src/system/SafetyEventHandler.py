import threading

class SafetyEventHandler:
    def __init__(self):
        self.danger_event = threading.Event()
        self.safe_event = threading.Event()
        self.latest_info = {}
        self._lock = threading.Lock()
    
    def on_danger_detected(self, description, timestamp):
        with self._lock:
            self.latest_info = {
                'type': 'danger',
                'description': description,
                'timestamp': timestamp
            }
            self.danger_event.set()
            self.safe_event.clear()
    
    def on_safe_detected(self):
        with self._lock:
            self.latest_info = {'type': 'safe'}
            self.safe_event.set()
            self.danger_event.clear()
        
    def wait_for_danger(self, timeout=None):
        """위험 상태까지 대기"""
        return self.danger_event.wait(timeout)
    
    def get_latest_info(self):
        with self._lock:
            return self.latest_info.copy()
        
safety_events = SafetyEventHandler()