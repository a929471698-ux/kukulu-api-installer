# token_manager.py  —— 直接整文件替换

import json
import os
import re
import threading
import time
from typing import Dict, Optional, Tuple, List

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SUBTOKEN_RE = re.compile(r"csrf_subtoken_check=([0-9a-fA-F]{32})")

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

BASE_URL = os.getenv("KUKULU_BASE_URL", "https://m.kuku.lu")
INDEX_PATH = "/index.php"

def _new_session(ua: str) -> requests.Session:
    s = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.headers.update({
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8,zh-CN;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "keep-alive",
    })
    return s

class TokenRecord:
    def __init__(self, csrf_token: str, sessionhash: str, ua: str, note: str = ""):
        self.csrf_token = csrf_token
        self.sessionhash = sessionhash
        self.ua = ua or DEFAULT_UA
        self.note = note
        self.last_ok_ts = 0.0
        self.bad_count = 0

    def to_cookie_jar(self) -> Dict[str, str]:
        return {
            "cookie_csrf_token": self.csrf_token,
            "cookie_sessionhash": self.sessionhash,
            # 语言可固定 cn/ja，不影响 subtoken 产生，但便于页面解析
            "cookie_setlang": "cn",
        }

class TokenManager:
    """
    - 支持最多5个记录
    - get_valid()：返回“已验证可用”的 TokenRecord + 当前 subtoken
    - report_bad()：根据错误码/症状扣分，必要时剔除
    """
    def __init__(self, max_size: int = 5, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/")
        self._lock = threading.Lock()
        self._items: List[TokenRecord] = []

        self._load_from_env_or_file()

    # ------- 外部接口 -------

    def get_valid(self) -> Tuple[TokenRecord, str]:
        with self._lock:
            # 简单 LRU：按 last_ok_ts 排序，优先用最近成功的
            self._items.sort(key=lambda x: x.last_ok_ts, reverse=True)
            items = list(self._items)

        last_err = None
        for rec in items:
            ok, subtoken = self._validate_and_fetch_subtoken(rec)
            if ok and subtoken:
                with self._lock:
                    rec.last_ok_ts = time.time()
                    rec.bad_count = 0
                return rec, subtoken
            else:
                last_err = "subtoken-missing"

        raise RuntimeError(f"No valid kukulu tokens (last_error={last_err})")

    def report_bad(self, rec: TokenRecord, reason: str, http_status: Optional[int] = None) -> None:
        with self._lock:
            rec.bad_count += 1
            # 403 / 429 / 连续三次失败：剔除
            if http_status in (403, 429) or rec.bad_count >= 3:
                if rec in self._items:
                    self._items.remove(rec)

    # ------- 内部实现 -------

    def _validate_and_fetch_subtoken(self, rec: TokenRecord) -> Tuple[bool, Optional[str]]:
        s = _new_session(rec.ua)
        s.cookies.update(rec.to_cookie_jar())
        url = f"{self.base_url}{INDEX_PATH}"
        try:
            r = s.get(url, timeout=10)
        except requests.RequestException:
            return False, None

        if r.status_code != 200:
            return False, None

        m = SUBTOKEN_RE.search(r.text or "")
        if not m:
            return False, None

        return True, m.group(1)

    def _load_from_env_or_file(self) -> None:
        # 1) 从环境变量载入（支持多组）
        env_pairs = []
        for k, v in os.environ.items():
            if k.startswith("KUKULU_TOKEN_") and "|" in v:
                env_pairs.append(v)

        # 2) 从 tokens.json 载入（可选）
        path = os.getenv("KUKULU_TOKENS_FILE", "tokens.json")
        if os.path.isfile(path):
            try:
                data = json.load(open(path, "r", encoding="utf-8"))
                for item in data:
                    env_pairs.append(f"{item['csrf_token']}|{item['sessionhash']}|{item.get('ua','')}")
            except Exception:
                pass

        # 3) 兼容你 shell 导出的两段变量
        cs = os.getenv("CSRF")
        sh = os.getenv("SHASH")
        if cs and sh:
            env_pairs.append(f"{cs}|{sh}|")

        # 去重并裁剪
        uniq = []
        for row in env_pairs:
            parts = row.strip().split("|")
            if len(parts) >= 2:
                csrf, shash = parts[0].strip(), parts[1].strip()
                ua = parts[2].strip() if len(parts) >= 3 else DEFAULT_UA
                if csrf and shash:
                    uniq.append((csrf, shash, ua))

        for csrf, shash, ua in uniq[:5]:
            self._items.append(TokenRecord(csrf, shash, ua))

        if not self._items:
            # 允许空启动，但 get_valid 会抛错
            pass
