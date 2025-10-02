# kukulu.py —— 只替换本文件；app.py/面板/API 不改
import requests
from bs4 import BeautifulSoup
import re
import random
from urllib.parse import quote

class Kukulu():
    def __init__(self, csrf_token=None, sessionhash=None, proxy=None):
        self.csrf_token  = csrf_token
        self.sessionhash = sessionhash
        self.proxy       = proxy
        self.session     = requests.Session()

        # 只在 m.kuku.lu 域设置关键 Cookie（创建/收件核心都发生在 m 站）
        if csrf_token:
            self.session.cookies.set("cookie_csrf_token", csrf_token, domain="m.kuku.lu", path="/")
        if sessionhash:
            shash = sessionhash.replace("%3A", ":") if "%3A" in sessionhash else sessionhash
            self.session.cookies.set("cookie_sessionhash", shash, domain="m.kuku.lu", path="/")
        self.session.cookies.set("cookie_setlang", "cn", domain="m.kuku.lu", path="/")
        self.session.cookies.set("cookie_keepalive_insert", "1", domain="m.kuku.lu", path="/")

        self.default_headers = {
            "User-Agent": self._random_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": random.choice([
                "en-US,en;q=0.5",
                "zh-CN,zh;q=0.9",
                "ja,en-US;q=0.9,en;q=0.8",
            ]),
            "Connection": "keep-alive",
        }

        # 预热（失败不抛）
        try:
            self.session.get("https://m.kuku.lu", headers=self.default_headers, timeout=10, proxies=self.proxy)
        except Exception:
            pass

    def _random_ua(self):
        return random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/114.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/113.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/117.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/110.0.0.0 Safari/537.36",
        ])

    def new_account(self):
        return {
            "csrf_token":  self.session.cookies.get("cookie_csrf_token"),
            "sessionhash": self.session.cookies.get("cookie_sessionhash"),
        }

    # ============ 创建邮箱：多路径 + 明确失败原因（打印到日志） ============
    def create_mailaddress(self):
        """
        1) 标准：addMailAddrByAuto & nopost=1 & by_system=1 & csrf_token_check
        2) 去掉 nopost
        3) 强头再试（Referer/Sec-Fetch/Upgrade）
        4) 兜底：直接从 index.php 文本里正则提邮箱
        命中任一路即返回；否则打印失败原因并返回 ""。
        """
        def _extract_email(txt: str) -> str:
            m = re.search(r"[A-Za-z0-9._%+-]{3,}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", txt)
            return m.group(0) if m else ""

        def _hit_ok(txt: str) -> str:
            if txt.startswith("OK:") and "@" in txt:
                return txt[3:].strip()
            return ""

        def _try(url, extra_headers=None, tag=""):
            hdr = dict(self.default_headers)
            if extra_headers: hdr.update(extra_headers)
            r = self.session.get(url, proxies=self.proxy, headers=hdr, timeout=15)
            txt = (r.text or "").strip()
            # 1) 正常 OK:
            mail = _hit_ok(txt)
            if mail:
                return mail
            # 2) 兜底从文本提邮箱
            mail = _extract_email(txt)
            if mail:
                return mail
            # 3) 打印失败原因（不落盘）
            reason = []
            if r.status_code != 200:
                reason.append(f"HTTP {r.status_code}")
            t_low = txt[:200].lower()
            if "just a moment" in t_low or "cloudflare" in t_low:
                reason.append("CLOUDFLARE")
            if "短縮url作成" in txt or "kuku.lu 短縮url作成" in txt:
                reason.append("HOMEPAGE")
            if not reason:
                reason.append("NO_EMAIL_IN_RESPONSE")
            print(f"[create_mailaddress][{tag}] fail: {', '.join(reason)}")
            return ""

        base = "https://m.kuku.lu/index.php?action=addMailAddrByAuto&by_system=1"
        qs1  = "&nopost=1"
        ctp  = f"&csrf_token_check={self.csrf_token}" if self.csrf_token else ""

        strong_headers = {
            "Referer": "https://m.kuku.lu/index.php",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document",
            "Upgrade-Insecure-Requests": "1",
        }

        # 顺序尝试
        for url, tag in (
            (base + qs1 + ctp, "std+nopost"),
            (base + ctp,       "std"),
            (base + qs1 + ctp, "strong+nopost"),
            (base + ctp,       "strong"),
        ):
            mail = _try(url, None if "strong" not in tag else strong_headers, tag)
            if mail:
                return mail

        # 兜底：从 index.php 把当前会话“已有地址”抠出来
        try:
            r = self.session.get("https://m.kuku.lu/index.php", headers=self.default_headers, timeout=15, proxies=self.proxy)
            mail = _extract_email(r.text or "")
            if mail:
                return mail
            print("[create_mailaddress][index] fail: NO_EMAIL_IN_INDEX")
        except Exception as e:
            print(f"[create_mailaddress][index] exception: {e}")

        return ""

    def specify_address(self, address):
        url = f"https://m.kuku.lu/index.php?action=addMailAddrByManual&by_system=1&csrf_token_check={self.csrf_token}&newdomain={address}"
        r = self.session.get(url, proxies=self.proxy, headers=self.default_headers, timeout=15)
        txt = (r.text or "").strip()
        if txt.startswith("OK:") and "@" in txt:
            return txt[3:].strip()
        m = re.search(r"[A-Za-z0-9._%+-]{3,}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", txt)
        return m.group(0) if m else ""

    # ============ 获取验证码：行为保持不变（桌面→移动回退） ============
    def check_top_mail(self, mailaddress):
        # 轻量声明当前邮箱（仅 m.kuku.lu），避免过度跨域cookie
        self.session.cookies.set("cookie_last_q", mailaddress, domain="m.kuku.lu", path="/")

        encoded   = quote(mailaddress)
        inbox_url = f"https://kuku.lu/mailbox/{encoded}"

        headers = {
            "User-Agent": self._random_ua(),
            "Referer": inbox_url,
            "Origin": "https://m.kuku.lu",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": random.choice([
                "ja,en-US;q=0.9,en;q=0.8",
                "zh-CN,zh;q=0.9,en;q=0.8",
            ])
        }

        try:
            # 桌面页
            inbox_resp = self.session.get(inbox_url, headers=headers, proxies=self.proxy, timeout=15)
            soup = BeautifulSoup(inbox_resp.text, "html.parser")

            candidates = []
            for a in soup.find_all("a", href=True):
                m = re.search(r"smphone\.app\.recv\.view\.php\?num=(\d+)&key=([A-Za-z0-9]+)", a["href"])
                if m:
                    candidates.append(m.groups())
            if not candidates:
                candidates += re.findall(r"smphone\.app\.recv\.view\.php\?num=(\d+)&key=([A-Za-z0-9]+)", inbox_resp.text)

            # 移动 AJAX 回退（需要 csrf_token）
            if not candidates and self.csrf_token:
                ajax_url = (
                    "https://m.kuku.lu/recv._ajax.php?"
                    f"q={quote(mailaddress)}&nopost=1&csrf_token_check={self.csrf_token}"
                )
                ajax_resp = self.session.get(ajax_url, headers=self.default_headers, proxies=self.proxy, timeout=15)
                candidates += re.findall(r"smphone\.app\.recv\.view\.php\?num=(\d+)&key=([A-Za-z0-9]+)", ajax_resp.text)
                candidates += re.findall(r"openMailData\('(\d+)'\s*,\s*'([0-9a-fA-F]+)'\s*,", ajax_resp.text)

            if not candidates:
                return None

            # 详情正文
            detail_url = "https://m.kuku.lu/smphone.app.recv.view.php"
            for num, key in candidates:
                resp = self.session.post(
                    detail_url,
                    data={"num": num, "key": key, "noscroll": "1"},
                    headers=headers, proxies=self.proxy, timeout=15
                )
                if resp.status_code != 200:
                    continue
                text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)
                m = re.search(r"\b\d{6}\b", text)
                if m:
                    return m.group()

        except Exception:
            pass

        return None
