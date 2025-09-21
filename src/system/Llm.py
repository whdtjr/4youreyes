import queue
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import re
import time
import ollama
class Llm:
    def __init__(self):
        # 설정값
        self.MODEL_NAME = "moondream:latest"   # llava 계열로 바꿔도 동일하게 동작
        self.ADAPTIVE_FACTOR = 1.2             # 인퍼런스 시간 기반 적응 계수
        self.MAJORITY_WINDOW = 5               # 최근 N회 결과 다수결
        self.OLLAMA_TIMEOUT = 25.0             # 초            
        
        self.HAZARD_PATTERNS = [
            # 영어
            r"\b(flame|blaze|fire|smoke|burn(ing)?\s*object|ignition)\b",
            r"\b(gun|knife|weapon|explosion|threat)\b",
            r"\b(fall(ing)?|ladder|no\s*harness|no\s*safety\s*line|at\s*height|construction|danger|hazard)\b",
            r"\b(crash|collision|overturn|rollover|airbag|wreckage|damaged\s*vehicle)\b",
        ]
        
        self.NLI_MODEL_NAME = "MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli"
        
        # NLI 모델 로드
        self.tokenizer, self.nli_model, self.device, self.ENTAIL_IDX, self.CONTRA_IDX, self.NEUTRAL_IDX = self._load_nli()
        
        # 큐 및 스레드 관련
        self.frame_q = queue.Queue(maxsize=1)
        self.result_q = queue.Queue(maxsize=10)
        self.stop_flag = False
        
    def _load_nli(self):
        """NLI 모델을 로드하고 초기화합니다."""
        tokenizer = AutoTokenizer.from_pretrained(self.NLI_MODEL_NAME)
        model = AutoModelForSequenceClassification.from_pretrained(self.NLI_MODEL_NAME)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda":
            model = model.half().to(device)
        id2label = model.config.id2label
        label_map_upper = {i: lbl.upper() for i, lbl in id2label.items()}
        entail_idx = [i for i, lbl in label_map_upper.items() if "ENTAIL" in lbl][0]
        contra_idx  = [i for i, lbl in label_map_upper.items() if "CONTRADICT" in lbl][0]
        neutral_idx = [i for i, lbl in label_map_upper.items() if "NEUTRAL" in lbl][0]
        return tokenizer, model, device, entail_idx, contra_idx, neutral_idx
        
    def classify_text_regex(self, text: str) -> str:
        """정규표현식을 사용하여 텍스트를 위험/안전으로 분류합니다."""
        t = text.lower()
        for p in self.HAZARD_PATTERNS:
            if re.search(p, t):
                return "위험"
        return "안전"
        
    def nli_danger(self, text: str, threshold: float = 0.6) -> str:
        """NLI 모델을 사용하여 텍스트가 위험한지 판단합니다."""
        premise = text
        hypothesis = "it is dangerous."
        inputs = self.tokenizer(premise, hypothesis, return_tensors="pt", truncation=True)
        if self.device == "cuda":
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with torch.no_grad():
            logits = self.nli_model(**inputs).logits.squeeze(0)
            probs = torch.softmax(logits, dim=-1).float().cpu().numpy().tolist()
        return "위험" if probs[self.ENTAIL_IDX] >= threshold else "안전"


    def ollama_describe(self, b64jpg: str, model: str, timeout: float = None) -> tuple[str, float]:
        if timeout is None:
            timeout = self.OLLAMA_TIMEOUT
        start = time.time()
        try:
            resp = ollama.chat(
                model=model,
                messages=[{
                    "role": "user", 
                    "content": "Describe this image briefly and factually.",
                    "images": [b64jpg]
                }],
                options={"timeout": timeout}
            )
            took = time.time() - start
            return resp["message"]["content"], took
        except Exception as e:
            took = time.time() - start
            print(f"Ollama 분석 오류: {e}")
            return f"이미지 분석 실패: {str(e)}", took