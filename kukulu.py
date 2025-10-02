import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, quote
import random
import logging

log = logging.getLogger("kukulu")

class Kukulu():
    def __init__(self, csrf_token=None, sessionhash=None, proxy=None):
        """
        轻量初始化，只在 m.kuku.lu 域写 cookie（创建/收件核心都在 m 站）。
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

        # 预热（失败不抛）
        try:
            self.session.get("https://m.kuku.lu/index.php", headers=self.default_headers, timeout=10, proxies=self.proxy)
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

    # -------------------- 创建邮箱：表单驱动（从 index.php 抓表单再提交） --------------------
    def create_mailaddress(self):
        """
        步骤：
        1) GET https://m.kuku.lu/index.php
        2) 找到 <form> 里 action=addMailAddrByAuto 的那个表单
        3) 采集该表单中所有 <input name=... value=...>，若缺失则补 nopost=1、by_system=1
        4) 按表单 method/action 提交（一般是 POST index.php）
        5) 响应优先匹配 'OK:xxx@yyy'，否则在文本中兜底提邮箱样式；仍无则返回 ""
        """
        try:
            # Step 1: 打开 index.php
            r = self.session.get("https://m.kuku.lu/index.php", headers=self.default_headers, timeout=12, proxies=self.proxy)
            soup = BeautifulSoup(r.text, "html.parser")

            # Step 2: 找到 action=addMailAddrByAuto 的 form
            target_form = None
            for form in soup.find_all("form"):
                # 收集这个 form 的所有 inputs 看看有没有 action=addMailAddrByAuto
                inputs = form.find_all("input")
                for inp in inputs:
                    if inp.get("name") == "action" and (inp.get("value") or "").strip() == "addMailAddrByAuto":
                        target_form = form
                        break
                if target_form:
                    break

            # 如果没找到表单，试旧接口快速兜底一把（尽量不报错）
            if target_form is None:
                url = "https://m.kuku.lu/index.php?action=addMailAddrByAuto&nopost=1&by_system=1"
                if self.csrf_token:
                    url += f"&csrf_token_check={self.csrf_token}"
                r2 = self.session.get(url, headers=self.default_headers, timeout=10, proxies=self.proxy)
                txt = (r2.text or "").strip()
                if txt.startswith("OK:") and "@" in txt:
                    return txt[3:].strip()
                m = re.search(r"[A-Za-z0-9._%+-]{3,}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", txt)
                if m:
                    return m.group(0)
                log.warning("CREATE FAIL [no_form] NO_EMAIL_IN_RESPONSE")
                return ""

            # Step 3: 采集 inputs，补齐必要字段
            data = {}
            for inp in target_form.find_all("input"):
                name  = inp.get("name")
                if not name:
                    continue
                value = inp.get("value") or ""
                data[name] = value

            # 补齐/覆盖必要字段
            data.setdefault("action", "addMailAddrByAuto")
            data.setdefault("by_system", "1")
            data.setdefault("nopost", "1")
            if self.csrf_token:
                data["csrf_token_check"] = self.csrf_token
            # 表单里若有 csrf_subtoken_check 会被上面的采集拿到；没有也没关系

            # Step 4: 解析 form method 与 action
            method = (target_form.get("method") or "post").lower()
            action = target_form.get("action") or "/index.php"
            action_url = urljoin("https://m.kuku.lu/index.php", action)

            # 提交表单
            if method == "post":
                resp = self.session.post(
                    action_url, data=data, headers={
                        **self.default_headers,
                        "Referer": "https://m.kuku.lu/index.php",
                        "Origin":  "https://m.kuku.lu",
                        "Content-Type": "application/x-www-form-urlencoded",
                    }, timeout=12, proxies=self.proxy
                )
            else:
                # 极少数会是 GET，但也做一下兼容
                resp = self.session.get(
                    action_url, params=data, headers=self.default_headers,
                    timeout=12, proxies=self.proxy
                )

            txt = (resp.text or "").strip()
            if txt.startswith("OK:") and "@" in txt:
                return txt[3:].strip()
            m = re.search(r"[A-Za-z0-9._%+-]{3,}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", txt)
            if m:
                return m.group(0)

            # 到这说明依旧没拿到邮箱
            rs = []
            if resp.status_code != 200: rs.append(f"HTTP {resp.status_code}")
            low = txt[:200].lower()
            if "just a moment" in low or "cloudflare" in low: rs.append("CLOUDFLARE")
            if not rs: rs.append("NO_EMAIL_IN_RESPONSE")
            log.warning(f"CREATE FAIL [form_submit] {', '.join(rs)}")
            return ""

        except Exception as e:
            log.warning(f"CREATE FAIL [exception] {e}")
            return ""

    # 保留：你的旧方式
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
