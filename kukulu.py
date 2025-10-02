# kukulu.py —— 仅替换本文件；面板(app.py)与API逻辑不需要改动
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

        # === 把关键 Cookie 同时写入 m.kuku.lu 与 kuku.lu；修正 SHASH%3A → SHASH:
        def _set_cookie(name, value, domains=("m.kuku.lu", "kuku.lu")):
            for d in domains:
                self.session.cookies.set(name, value, domain=d, path="/")

        if csrf_token:
            _set_cookie("cookie_csrf_token", csrf_token)
        if sessionhash:
            shash = sessionhash.replace("%3A", ":") if "%3A" in sessionhash else sessionhash
            _set_cookie("cookie_sessionhash", shash)

        _set_cookie("cookie_setlang", "cn")
        _set_cookie("cookie_keepalive_insert", "1")
        _set_cookie("cookie_timezone", "Asia/Tokyo")

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
            self.session.get("https://kuku.lu",  headers=self.default_headers, timeout=10, proxies=self.proxy)
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

    # ===================== 关键修复：create_mailaddress 多路径强兜底 =====================
    def create_mailaddress(self):
        """
        顺序：
        1) 标准：addMailAddrByAuto & nopost=1 & by_system=1 & csrf_token_check
        2) 备用：去掉 nopost
        3) 强头重试：加 Referer=index.php 与 Sec-Fetch-* 系列
        4) 兜底解析：直接访问 index.php，从页面中正则提邮箱（已有/刚创建）
        任一路拿到邮箱样式即返回
        """
        def _try(url, extra_headers=None):
            hdr = dict(self.default_headers)
            if extra_headers:
                hdr.update(extra_headers)
            r = self.session.get(url, proxies=self.proxy, headers=hdr, timeout=15)
            txt = r.text.strip()
            # 第一优先：OK:xxx@yyy
            if txt.startswith("OK:") and "@" in txt:
                return txt[3:].strip()
            # 全文兜底：直接提一个邮箱样式
            m = re.search(r"[A-Za-z0-9._%+-]{3,}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", txt)
            return m.group(0) if m else ""

        # 1) 标准参数
        base = "https://m.kuku.lu/index.php?action=addMailAddrByAuto&by_system=1"
        qs1  = "&nopost=1"
        ctp  = f"&csrf_token_check={self.csrf_token}" if self.csrf_token else ""

        # 2) 强 Referer + Sec-Fetch-*（贴近浏览器）
        strong_headers = {
            "Referer": "https://m.kuku.lu/index.php",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document",
            "Upgrade-Insecure-Requests": "1",
        }

        # 依次尝试
        for url in (
            base + qs1 + ctp,
            base + ctp,
        ):
            mail = _try(url)
            if mail:
                return mail

        # 强头再试两次
        for url in (
            base + qs1 + ctp,
            base + ctp,
        ):
            mail = _try(url, strong_headers)
            if mail:
                return mail

        # 4) 兜底：直接从 index.php 页面提一个邮箱（已有/刚创建）
        try:
            r = self.session.get("https://m.kuku.lu/index.php", headers=self.default_headers, timeout=15, proxies=self.proxy)
            m = re.search(r"[A-Za-z0-9._%+-]{3,}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", r.text)
            if m:
                return m.group(0)
        except Exception:
            pass

        return ""

    def specify_address(self, address):
        url = f"https://m.kuku.lu/index.php?action=addMailAddrByManual&by_system=1&csrf_token_check={self.csrf_token}&newdomain={address}"
        r = self.session.get(url, proxies=self.proxy, headers=self.default_headers, timeout=15)
        txt = r.text.strip()
        if txt.startswith("OK:") and "@" in txt:
            return txt[3:].strip()
        m = re.search(r"[A-Za-z0-9._%+-]{3,}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", txt)
        return m.group(0) if m else ""

    # ===================== 保持原入口与行为：check_top_mail =====================
    def check_top_mail(self, mailaddress):
        """
        行为保持不变：
        - 先挂载 cookie_last_q（两域），避免 /mailbox 被主页
        - 桌面页提 num/key；若无 → 回退 m 站 AJAX（含 openMailData 解析）
        - 详情 POST smphone.app.recv.view.php，正则提 6 位验证码
        """
        self._set_current_mail_cookie(mailaddress)

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
            # 1) 桌面收件箱
            inbox_resp = self.session.get(inbox_url, headers=headers, proxies=self.proxy, timeout=15)
            soup = BeautifulSoup(inbox_resp.text, "html.parser")
            candidates = self._extract_candidates_from_desktop(inbox_resp.text, soup)

            # 2) 回退：移动 AJAX（仅当桌面抓不到候选；需要 csrf_token）
            if not candidates and self.csrf_token:
                ajax_url = (
                    "https://m.kuku.lu/recv._ajax.php?"
                    f"q={quote(mailaddress)}&nopost=1&csrf_token_check={self.csrf_token}"
                )
                ajax_resp = self.session.get(ajax_url, headers=self.default_headers, proxies=self.proxy, timeout=15)
                candidates = self._extract_candidates_from_mobile_ajax(ajax_resp.text)

            if not candidates:
                return None

            # 3) 详情正文
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

    # ====== 内部辅助 ======
    def _set_current_mail_cookie(self, mailaddress: str):
        for d in ("m.kuku.lu", "kuku.lu"):
            self.session.cookies.set("cookie_last_q", mailaddress, domain=d, path="/")
        self.session.cookies.set("cookie_last_page_recv", "0", domain="m.kuku.lu", path="/")
        self.session.cookies.set("cookie_last_page_addrlist", "0", domain="m.kuku.lu", path="/")

    def _extract_candidates_from_desktop(self, html: str, soup: BeautifulSoup):
        candidates = []
        for a in soup.find_all("a", href=True):
            m = re.search(r"smphone\.app\.recv\.view\.php\?num=(\d+)&key=([A-Za-z0-9]+)", a["href"])
            if m:
                candidates.append(m.groups())
        if not candidates:
            for m in re.findall(r"smphone\.app\.recv\.view\.php\?num=(\d+)&key=([A-Za-z0-9]+)", html):
                candidates.append(m)
        return candidates

    def _extract_candidates_from_mobile_ajax(self, html: str):
        candidates = []
        candidates += re.findall(r"smphone\.app\.recv\.view\.php\?num=(\d+)&key=([A-Za-z0-9]+)", html)
        candidates += re.findall(r"openMailData\('(\d+)'\s*,\s*'([0-9a-fA-F]+)'\s*,", html)
        return candidates
