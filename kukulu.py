# kukulu.py —— 直接整文件替换

import html
import json
import os
import re
from typing import Dict, Optional, Tuple, List

import requests

from token_manager import TokenManager, _new_session

BASE_URL = os.getenv("KUKULU_BASE_URL", "https://m.kuku.lu").rstrip("/")

# 常见字段正则
MAIL_ADDR_RE = re.compile(r"mailto:([A-Za-z0-9_.+\-]+@[A-Za-z0-9_.\-]+\.[A-Za-z]{2,})")
CODE_RE = re.compile(r"(?<!\d)(\d{4,8})(?!\d)")
# 邮箱页面里常见 “收件箱顶部第一封邮件” 的容错锚点
TOP_MAIL_BLOCK_RE = re.compile(r"(受信|受信箱|受信フォルダ|Inbox|最新|新着)[\s\S]{0,500}?(?:\r?\n|\<)", re.IGNORECASE)

DEFAULT_HEADERS_EXTRA = {
    "Origin": "https://m.kuku.lu",
    "Referer": "https://m.kuku.lu/index.php",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
}

def _session_with_token(tm: TokenManager):
    rec, subtoken = tm.get_valid()
    s = _new_session(rec.ua)
    s.cookies.update(rec.to_cookie_jar())
    return s, rec, subtoken

def _req(s: requests.Session, method: str, url: str, **kw) -> requests.Response:
    # 统一加头（不覆盖用户传入）
    headers = kw.pop("headers", {})
    for k, v in DEFAULT_HEADERS_EXTRA.items():
        headers.setdefault(k, v)
    return s.request(method, url, headers=headers, timeout=kw.pop("timeout", 10), **kw)

def _extract_first_mail_address(html_text: str) -> Optional[str]:
    # DOM 渲染前后兼容：先 unescape，再两轮匹配
    txt = html.unescape(html_text or "")
    m = MAIL_ADDR_RE.search(txt)
    if m:
        return m.group(1)
    # 兜底：明文邮箱
    m2 = re.search(r"([A-Za-z0-9_.+\-]+@[A-Za-z0-9_.\-]+\.[A-Za-z]{2,})", txt)
    return m2.group(1) if m2 else None

def _extract_latest_code(html_text: str) -> Optional[str]:
    # 从“最新/新着”附近 500 字窗口抽验证码
    txt = html.unescape(html_text or "")
    window = txt
    anchor = TOP_MAIL_BLOCK_RE.search(txt)
    if anchor:
        start = max(anchor.start() - 300, 0)
        end = min(anchor.end() + 800, len(txt))
        window = txt[start:end]
    m = CODE_RE.search(window)
    return m.group(1) if m else None

# =============== 对外 API ===============

def create_random(tm: TokenManager) -> Dict:
    """新建一个随机邮箱地址；返回 {ok, reason, data:{email}}"""
    s, rec, subtoken = _session_with_token(tm)
    url = f"{BASE_URL}/mailbox/?csrf_subtoken_check={subtoken}&type=random"
    try:
        r = _req(s, "GET", url)
    except requests.RequestException as e:
        tm.report_bad(rec, "network", None)
        return {"ok": False, "reason": f"network:{e}"}

    if r.status_code in (403, 429):
        tm.report_bad(rec, "blocked", r.status_code)
        return {"ok": False, "reason": f"http-{r.status_code}"}

    if r.status_code != 200:
        return {"ok": False, "reason": f"http-{r.status_code}"}

    email = _extract_first_mail_address(r.text)
    if not email:
        # 可能是子令牌过期/UA 不一致导致页面被重定向空白
        tm.report_bad(rec, "parse-email-empty", None)
        return {"ok": False, "reason": "parse-email-empty"}

    return {"ok": True, "data": {"email": email}}

def check_top_mail(tm: TokenManager, email_addr: str) -> Dict:
    """读取该邮箱收件箱顶部邮件，并尽可能抽取验证码"""
    s, rec, subtoken = _session_with_token(tm)
    # 有些版本需要显式传邮箱，否则按 Cookie/session 定位最近邮箱
    mailbox_url = f"{BASE_URL}/mailbox/?csrf_subtoken_check={subtoken}&mail={email_addr}"
    try:
        r = _req(s, "GET", mailbox_url)
    except requests.RequestException as e:
        tm.report_bad(rec, "network", None)
        return {"ok": False, "reason": f"network:{e}"}

    if r.status_code in (403, 429):
        tm.report_bad(rec, "blocked", r.status_code)
        return {"ok": False, "reason": f"http-{r.status_code}"}

    if r.status_code != 200 or not r.text:
        return {"ok": False, "reason": f"http-{r.status_code}"}

    code = _extract_latest_code(r.text)
    return {"ok": True, "data": {"code": code, "raw_len": len(r.text)}}

def get_code_from_latest_email(tm: TokenManager, email_addr: str) -> Dict:
    """封装一层：先打开收件箱再抽验证码"""
    res = check_top_mail(tm, email_addr)
    if not res.get("ok"):
        return res
    code = res["data"].get("code")
    if not code:
        return {"ok": False, "reason": "code-not-found"}
    return {"ok": True, "data": {"code": code}}
