from kukulu import Kukulu
from collections import deque

class TokenManager:
    def __init__(self, max_tokens=5):
        self.tokens = deque(maxlen=max_tokens)

    def get_token(self):
        if not self.tokens:
            return self.generate_token()
        return self.tokens[0]

    def rotate_token(self):
        if self.tokens:
            self.tokens.rotate(-1)
        return self.tokens[0] if self.tokens else self.generate_token()

    def generate_token(self):
        k = Kukulu()
        t = k.new_account()
        self.tokens.append(t)
        return t
