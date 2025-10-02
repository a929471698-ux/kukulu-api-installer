# token_manager.py
# 需求实现：
# - 启动时/运行中发现“跨天”→ 删除旧 tokens，自动生成 5 个新 tokens 并持久化
# - get_token() / rotate_token() 与现有 app.py 完全兼容
# - 自动修正 sessionhash 为 "SHASH:xxxx"（避免 SHASH%3A 编码坑）

import os
import json
import random
import time
import requests
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# ========= 可调参数 =========
TARGET_TOKEN_COUNT = 5            # 每天生成的 token 数量
REQUEST_TIMEOUT    = 12           # 单次请求超时
PARALLEL_WORKERS   = 5            # 并发生成线程
PROXY              = None         # 如需代理：{"http": "...", "https": "..."}；否则 None
TZ_OFFSET_MINUTES  = 540            # 本地时区偏移（需要按特定时区轮换可改，比如日本 +540）

# ========= 路径 =========
APP_DIR   = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(APP_DIR, "data")
TOKENS_DB = os.path.join(DATA_DIR, "mail_tokens.json")
os.makedirs(DATA_DIR, exist_ok=True)

# ========= 工具 =========
def _now_tz():
    tz = timezone(timedelta(minutes=TZ_OFFSET_MINUTES))
    return datetime.now(tz)

def _today_key():
    return _now_tz().strftime("%Y-%m-%d")

def _random_user_agent():
    return random.choice([
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/114.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/113.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/117.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/110.0.0.0 Safari/537.36",
    ])

def _normalize_shash(shash: str) -> str:
    """修正 SHASH%3Axxxx → SHASH:xxxx"""
    if shash and "%3A" in shash:
        return shash.replace("%3A", ":")
    return shash

def _is_valid_token(t: dict) -> bool:
    return bool(
        t and t.get("csrf_token") and t.get("sessionhash") and
        str(t["sessionhash"]).startswith("SHASH:")
    )

def _load_tokens():
    if not os.path.exists(TOKENS_DB):
        return {"day": None, "tokens": []}
    try:
        with open(TOKENS_DB, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"day": None, "tokens": []}
            # 兼容老格式（纯 list）
            if "tokens" not in data and isinstance(data, list):
                return {"day": None, "tokens": data}
            return data
    except Exception:
        return {"day": None, "tokens": []}

def _save_tokens(day_key: str, tokens: list):
    tmp = TOKENS_DB + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"day": day_key, "tokens": tokens}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, TOKENS_DB)

# ========= 生成 =========
def _gen_one_token(proxy=None) -> dict:
    """
    访问 https://m.kuku.lu 获取 cookie_csrf_token / cookie_sessionhash
    返回 {"csrf_token": "...", "sessionhash": "SHASH:..."}
    """
    sess = requests.Session()
    headers = {
        "User-Agent": _random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }
    # 预热主页
    sess.get("https://m.kuku.lu", headers=headers, timeout=REQUEST_TIMEOUT, proxies=proxy)
    csrf  = sess.cookies.get("cookie_csrf_token")
    shash = sess.cookies.get("cookie_sessionhash")
    # 备份尝试
    if not csrf or not shash:
        sess.get("https://m.kuku.lu/index.php", headers=headers, timeout=REQUEST_TIMEOUT, proxies=proxy)
        csrf  = sess.cookies.get("cookie_csrf_token")
        shash = sess.cookies.get("cookie_sessionhash")

    if not csrf or not shash:
        raise RuntimeError("无法生成 kukulu token：未拿到 cookie_csrf_token / cookie_sessionhash")

    shash = _normalize_shash(shash)
    return {"csrf_token": csrf, "sessionhash": shash}

def _gen_many_tokens(n, proxy=None) -> list:
    """并发生成 n 个 token；单个失败不影响其它。"""
    out = []
    with ThreadPoolExecutor(max_workers=min(PARALLEL_WORKERS, max(1, n))) as ex:
        futs = [ex.submit(_gen_one_token, proxy=proxy) for _ in range(n)]
        for fut in as_completed(futs):
            try:
                t = fut.result()
                if _is_valid_token(t):
                    out.append(t)
                time.sleep(0.1)  # 微小抖动
            except Exception:
                pass
    return out

def _dedup(tokens: list) -> list:
    """按 (csrf, sessionhash) 去重"""
    seen = set()
    out = []
    for t in tokens:
        key = (t.get("csrf_token"), t.get("sessionhash"))
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out

# ========= 管理类（与 app.py 完全兼容）=========
class TokenManager:
    def __init__(self, proxy=None):
        self.proxy = proxy if proxy is not None else PROXY
        data = _load_tokens()
        self.day = data.get("day")  # 上次写入的“日”标记（YYYY-MM-DD）
        tokens = data.get("tokens") or []

        # 清洗/修正
        clean = []
        for t in tokens:
            if not t: 
                continue
            if t.get("sessionhash"):
                t["sessionhash"] = _normalize_shash(t["sessionhash"])
            if _is_valid_token(t):
                clean.append(t)
        clean = _dedup(clean)

        # 若是“跨天”或数量不足 → 直接重建今日 token
        today = _today_key()
        if (self.day != today) or (len(clean) < TARGET_TOKEN_COUNT):
            clean = self._rebuild_today_tokens(today)
        self.tokens = clean
        self.index = 0
        self.day = today
        _save_tokens(self.day, self.tokens)

    def _rebuild_today_tokens(self, today_key: str) -> list:
        new_tokens = _gen_many_tokens(TARGET_TOKEN_COUNT, proxy=self.proxy)
        new_tokens = _dedup([t for t in new_tokens if _is_valid_token(t)])
        # 如果并发生成不足，补齐到目标数量
        if len(new_tokens) < TARGET_TOKEN_COUNT:
            need = TARGET_TOKEN_COUNT - len(new_tokens)
            new_tokens += _gen_many_tokens(need, proxy=self.proxy)
            new_tokens = _dedup([t for t in new_tokens if _is_valid_token(t)])
        _save_tokens(today_key, new_tokens)
        return new_tokens

    def _ensure_today(self):
        """每次对外取 token 时检查是否跨天，跨天则重建 5 个并覆盖。"""
        today = _today_key()
        if today != self.day or len(self.tokens) < TARGET_TOKEN_COUNT:
            self.tokens = self._rebuild_today_tokens(today)
            self.day = today
            self.index = 0

    def get_token(self) -> dict:
        self._ensure_today()
        if not self.tokens:
            # 兜底：再尝试生成 1 个
            try:
                t = _gen_one_token(proxy=self.proxy)
                self.tokens = [t]
                _save_tokens(self.day or _today_key(), self.tokens)
            except Exception:
                return {"csrf_token": None, "sessionhash": None}
        t = self.tokens[self.index % len(self.tokens)]
        self.index = (self.index + 1) % max(1, len(self.tokens))
        return t

    def rotate_token(self) -> dict:
        """与 app.py 的 fallback 兼容：轮换 + 跨天检测"""
        return self.get_token()
