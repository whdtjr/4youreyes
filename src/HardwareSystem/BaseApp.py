# ===== Base Class =====
class BaseApp:
    """공통 기능을 제공하는 베이스 클래스"""

    def __init__(self, language='ko'):
        self.language = language
        self.initialized = False

    def initialize(self):
        """필요한 리소스 초기화 (서브클래스에서 구현)"""
        raise NotImplementedError

    def cleanup(self):
        """리소스 정리 (서브클래스에서 확장 가능)"""
        pass

    def validate_input(self, data):
        """입력 데이터 검증 (서브클래스에서 구현)"""
        pass

    def process(self, data):
        """주요 로직 실행 (서브클래스에서 구현)"""
        raise NotImplementedError

    def run(self, *args, **kwargs):
        """전체 실행 흐름 관리"""
        try:
            self.initialize()
            input_data = self.validate_input(*args, **kwargs)
            if not input_data:
                return 1
            success = self.process(input_data)
            return 0 if success else 1
        except Exception as e:
            print(f"실행 중 오류: {e}")
            return 1
        finally:
            self.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()