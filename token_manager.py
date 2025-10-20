from kukulu import Kukulu
from collections import deque
import logging, time, random

class TokenManager:
    def __init__(self, max_tokens=5):
        self.tokens = deque(maxlen=max_tokens)
        self.token_ts = {}
        self.load_tokens()

    def load_tokens(self):
        if not self.tokens:
            self.generate_token()

    def get_token(self):
        now = time.time()
        # 移除超过 24 小时的旧 token
        for t in list(self.tokens):
            if now - self.token_ts.get(t["csrf_token"], 0) > 86400:
                logging.info(f"[TOKEN_EXPIRE] expired: {t}")
                self.tokens.remove(t)
        if not self.tokens:
            self.generate_token()
        return self.tokens[0]

    def rotate_token(self):
        if self.tokens:
            self.tokens.rotate(-1)
        else:
            self.generate_token()
        return self.tokens[0]

    def mark_bad(self, bad_token):
        """删除无效 token 并生成新 token"""
        try:
            self.tokens.remove(bad_token)
            logging.info(f"[TOKEN_REMOVED] {bad_token}")
        except ValueError:
            pass
        self.generate_token()

    def generate_token(self):
        """创建新的 kukulu token"""
        try:
            k = Kukulu()
            t = k.new_account()
            self.tokens.append(t)
            self.token_ts[t["csrf_token"]] = time.time()
            logging.info(f"[TOKEN_NEW] {t}")
            time.sleep(random.uniform(1, 2))
            return t
        except Exception as e:
            logging.error(f"[TOKEN_GEN_FAIL] {e}")
            return None
