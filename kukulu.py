import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import quote
import random
import logging

log = logging.getLogger("kukulu")

class Kukulu():
    def __init__(self, csrf_token=None, sessionhash=None, proxy=None):
        """
        保持你最初的轻量初始化，不引入跨域/大改：
        - 只在 m.kuku.lu 域写 cookie（创建/收件核心都在 m 站）
        - SHASH%3A → SHASH:（常见坑）
        """
        self.csrf_token  = csrf_token
        self.sessionhash = sessionhash
        self.proxy       = proxy
        self.session     = requests.Session()

        if csrf_token:
            self.session.cookies.set("cookie_csrf_token", csrf_token, domain="m.kuku.lu", path="/")
        if sessionhash:
            shash = sessionhash.replace("%3A", ":") if "%3A" in sessionhash else sessionhash
            self.session.cookies.set("cookie_sessionhash", shash, domain="m.kuku.lu", path="/")

        # 语言/保活（与浏览器行为一致）
        self.session.cookies.set("cookie_setlang", "cn", domain="m.kuku.lu", path="/")
        self.session.cookies.set("cookie_keepalive_insert", "1", domain="m.kuku.lu", path="/")

        self.default_headers = {
            "User-Agent": self._random_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": random.choice([
                "zh-CN,zh;q=0.9,en;q=0.8",
                "ja,en-US;q=0.9,en;q=0.8",
            ]),
            "Connection": "keep-alive",
        }

        # 预热（失败不抛异常）
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

    # -------------------- 创建邮箱：优先 POST + 子 token，自适应兜底 --------------------
    def _fetch_subtoken(self) -> str:
        """
        到 index.php 抓子 token（页面内常见：csrf_subtoken_check=32位hex）
        """
        try:
            r = self.session.get("https://m.kuku.lu/index.php",
                                 headers=self.default_headers, timeout=10, proxies=self.proxy)
            m = re.search(r"csrf_subtoken_check=([0-9a-fA-F]{32})", r.text or "")
            return m.group(1) if m else ""
        except Exception:
            return ""

    def _extract_any_email(self, text: str) -> str:
        m = re.search(r"[A-Za-z0-9._%+-]{3,}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")
        return m.group(0) if m else ""

    def _log_create_fail(self, tag: str, status_code: int, text: str):
        reasons = []
        if status_code and status_code != 200:
            reasons.append(f"HTTP {status_code}")
        low = (text or "")[:200].lower()
        if "just a moment" in low or "cloudflare" in low:
            reasons.append("CLOUDFLARE")
        if "短縮url作成" in (text or "") or "kuku.lu 短縮url作成" in (text or ""):
            reasons.append("HOMEPAGE")
        if not reasons:
            reasons.append("NO_EMAIL_IN_RESPONSE")
        log.warning(f"CREATE FAIL [{tag}] {', '.join(reasons)}")

    def create_mailaddress(self):
        """
        现在 kukulu 大概率要求带 csrf_subtoken 的 **POST** 才返回 OK:xxx@xx。
        顺序：
          1) POST: action=addMailAddrByAuto & nopost=1 & by_system=1 & csrf_token_check & csrf_subtoken_check
          2) GET:  旧路径（nopost=1）
          3) GET:  旧路径（去掉 nopost）
          4) 兜底：index.php 页面直接提邮箱文本
        任一路拿到邮箱即返回；只写一行失败原因到日志，不写文件。
        """
        # 1) POST 带子 token
        sub = self._fetch_subtoken()
        post_headers = {
            **self.default_headers,
            "Referer": "https://m.kuku.lu/index.php",
            "Origin":  "https://m.kuku.lu",
            "Content-Type": "application/x-www-form-urlencoded",
            # 轻微拟人（可选）
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document",
            "Upgrade-Insecure-Requests": "1",
        }
        try:
            data = {
                "action": "addMailAddrByAuto",
                "nopost": "1",
                "by_system": "1",
            }
            if self.csrf_token:
                data["csrf_token_check"] = self.csrf_token
            if sub:
                data["csrf_subtoken_check"] = sub

            r = self.session.post("https://m.kuku.lu/index.php",
                                  data=data, headers=post_headers, timeout=12, proxies=self.proxy)
            txt = (r.text or "").strip()
            if txt.startswith("OK:") and "@" in txt:
                return txt[3:].strip()
            mail = self._extract_any_email(txt)
            if mail:
                return mail
            self._log_create_fail("POST+subtoken", r.status_code, txt)
        except Exception as e:
            log.warning(f"CREATE FAIL [POST+subtoken] exception: {e}")

        # 2) GET 旧路径（nopost=1）
        try:
            url = "https://m.kuku.lu/index.php?action=addMailAddrByAuto&nopost=1&by_system=1"
            if self.csrf_token:
                url += f"&csrf_token_check={self.csrf_token}"
            r = self.session.get(url, headers=self.default_headers, timeout=12, proxies=self.proxy)
            txt = (r.text or "").strip()
            if txt.startswith("OK:") and "@" in txt:
                return txt[3:].strip()
            mail = self._extract_any_email(txt)
            if mail:
                return mail
            self._log_create_fail("GET+nopost", r.status_code, txt)
        except Exception as e:
            log.warning(f"CREATE FAIL [GET+nopost] exception: {e}")

        # 3) GET 旧路径（去掉 nopost）
        try:
            url = "https://m.kuku.lu/index.php?action=addMailAddrByAuto&by_system=1"
            if self.csrf_token:
                url += f"&csrf_token_check={self.csrf_token}"
            r = self.session.get(url, headers=self.default_headers, timeout=12, proxies=self.proxy)
            txt = (r.text or "").strip()
            if txt.startswith("OK:") and "@" in txt:
                return txt[3:].strip()
            mail = self._extract_any_email(txt)
            if mail:
                return mail
            self._log_create_fail("GET", r.status_code, txt)
        except Exception as e:
            log.warning(f"CREATE FAIL [GET] exception: {e}")

        # 4) 兜底：直接看 index.php 文本里是否渲染了邮箱
        try:
            r = self.session.get("https://m.kuku.lu/index.php",
                                 headers=self.default_headers, timeout=10, proxies=self.proxy)
            mail = self._extract_any_email(r.text or "")
            if mail:
                return mail
            self._log_create_fail("INDEX", r.status_code, r.text or "")
        except Exception as e:
            log.warning(f"CREATE FAIL [INDEX] exception: {e}")

        return ""

    # ---------------- 保留你原来的 specify_address ----------------
    def specify_address(self, address):
        url = (
            "https://m.kuku.lu/index.php?action=addMailAddrByManual"
            "&nopost=1&by_system=1"
            f"&csrf_token_check={self.csrf_token}"
            f"&newdomain={address}"
        )
        resp = self.session.get(url, proxies=self.proxy)
        return resp.text[3:]

    # ---------------- 验证码解析：桌面优先，移动 AJAX 兜底 ----------------
    def check_top_mail(self, mailaddress):
        """
        行为保持不变：
        - 桌面页 a[href] + 全文正则提 num/key
        - 桌面抓不到 → 移动 AJAX（兼容 openMailData('num','key',...)）
        - POST smphone.app.recv.view.php 拉正文；正则提 6 位验证码
        """
        encoded_mail = quote(mailaddress)

        # A) 桌面页
        candidates = []
        try:
            inbox_url = f"https://kuku.lu/mailbox/{encoded_mail}"
            inbox_resp = self.session.get(inbox_url, proxies=self.proxy, timeout=10)
            soup = BeautifulSoup(inbox_resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                m = re.search(r"smphone\.app\.recv\.view\.php\?num=(\d+)&key=([A-Za-z0-9]+)", a["href"])
                if m:
                    candidates.append(m.groups())
            if not candidates:
                candidates += re.findall(
                    r"smphone\.app\.recv\.view\.php\?num=(\d+)&key=([A-Za-z0-9]+)", inbox_resp.text
                )
        except Exception:
            pass

        # B) 移动 AJAX
        if not candidates and self.csrf_token:
            try:
                ajax_url = (
                    "https://m.kuku.lu/recv._ajax.php?"
                    f"q={encoded_mail}&nopost=1&csrf_token_check={self.csrf_token}"
                )
                ajax_resp = self.session.get(ajax_url, proxies=self.proxy, timeout=10)
                candidates += re.findall(
                    r"smphone\.app\.recv\.view\.php\?num=(\d+)&key=([A-Za-z0-9]+)", ajax_resp.text
                )
                candidates += re.findall(
                    r"openMailData\('(\d+)'\s*,\s*'([0-9a-fA-F]+)'\s*,", ajax_resp.text
                )
            except Exception:
                pass

        if not candidates:
            return None

        # C) 拉正文
        for num, key in candidates:
            try:
                detail = self.session.post(
                    "https://m.kuku.lu/smphone.app.recv.view.php",
                    data={"num": num, "key": key, "noscroll": "1"},
                    proxies=self.proxy, timeout=10
                )
                text = BeautifulSoup(detail.text, "html.parser").get_text(" ", strip=True)
                m = re.search(r"\b\d{6}\b", text)
                if m:
                    return m.group()
            except Exception:
                continue

        return None
