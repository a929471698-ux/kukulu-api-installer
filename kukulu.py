# kukulu.py  —— 只替换本文件；app.py 和面板逻辑一律不改
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

        # 仅在 m.kuku.lu 域设置关键 Cookie（创建/收件核心都发生在 m 站）
        if csrf_token:
            self.session.cookies.set("cookie_csrf_token", csrf_token, domain="m.kuku.lu", path="/")
        if sessionhash:
            shash = sessionhash.replace("%3A", ":") if "%3A" in sessionhash else sessionhash
            self.session.cookies.set("cookie_sessionhash", shash, domain="m.kuku.lu", path="/")

        # 常见偏好
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

        # 预热 m.kuku.lu（失败不抛）
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

    # === 稳定：创建邮箱 — 三步短路 ===
    def create_mailaddress(self):
        """
        顺序：
        1) 标准：addMailAddrByAuto & nopost=1 & by_system=1 & csrf_token_check
        2) 备用：去掉 nopost（有时被拦）
        3) 兜底：返回体中直接正则提邮箱（不少响应会把地址渲染到文中）
        命中任一路线即返回，不再做多域 cookie 操作，避免状态干扰。
        """
        def _try(url, extra_headers=None):
            hdr = dict(self.default_headers)
            if extra_headers:
                hdr.update(extra_headers)
            r = self.session.get(url, proxies=self.proxy, headers=hdr, timeout=15)
            txt = r.text.strip()
            if txt.startswith("OK:") and "@" in txt:      # 正常返回
                return txt[3:].strip()
            m = re.search(r"[A-Za-z0-9._%+-]{3,}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", txt)
            return m.group(0) if m else ""

        base = "https://m.kuku.lu/index.php?action=addMailAddrByAuto&by_system=1"
        qs1  = "&nopost=1"
        ctp  = f"&csrf_token_check={self.csrf_token}" if self.csrf_token else ""

        # 标准
        mail = _try(base + qs1 + ctp)
        if mail: return mail
        # 去 nopost
        mail = _try(base + ctp)
        if mail: return mail
        # 强 Referer 头再试（常见 Cloudflare/Sec-Fetch 轻拦截）
        strong_headers = {
            "Referer": "https://m.kuku.lu/index.php",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document",
            "Upgrade-Insecure-Requests": "1",
        }
        mail = _try(base + qs1 + ctp, strong_headers)
        if mail: return mail
        mail = _try(base + ctp, strong_headers)
        if mail: return mail

        # 兜底：直接请求 index.php，从页面文本里找邮箱
        try:
            r = self.session.get("https://m.kuku.lu/index.php", headers=self.default_headers, timeout=15, proxies=self.proxy)
            m = re.search(r"[A-Za-z0-9._%+-]{3,}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", r.text)
            if m:
                return m.group(0)
        except Exception:
            pass

        return ""  # 最终失败

    def specify_address(self, address):
        url = f"https://m.kuku.lu/index.php?action=addMailAddrByManual&by_system=1&csrf_token_check={self.csrf_token}&newdomain={address}"
        r = self.session.get(url, proxies=self.proxy, headers=self.default_headers, timeout=15)
        txt = r.text.strip()
        if txt.startswith("OK:") and "@" in txt:
            return txt[3:].strip()
        m = re.search(r"[A-Za-z0-9._%+-]{3,}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", txt)
        return m.group(0) if m else ""

    # === 保持原行为：获取验证码 ===
    def check_top_mail(self, mailaddress):
        """
        行为保持不变：
        - 桌面页提取 num/key（a[href] + 全文正则）
        - 失败 → 回退移动 AJAX（含 openMailData('num','key',...) 解析）
        - 详情页 POST smphone.app.recv.view.php，正则提 6 位验证码
        """
        # 轻量声明当前邮箱（仅 m.kuku.lu）；避免过度写跨域状态引发风控
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
            # 1) 桌面页
            inbox_resp = self.session.get(inbox_url, headers=headers, proxies=self.proxy, timeout=15)
            soup = BeautifulSoup(inbox_resp.text, "html.parser")

            candidates = []
            # a[href] 优先
            for a in soup.find_all("a", href=True):
                m = re.search(r"smphone\.app\.recv\.view\.php\?num=(\d+)&key=([A-Za-z0-9]+)", a["href"])
                if m:
                    candidates.append(m.groups())
            # 全文兜底
            if not candidates:
                candidates += re.findall(r"smphone\.app\.recv\.view\.php\?num=(\d+)&key=([A-Za-z0-9]+)", inbox_resp.text)

            # 2) 移动 AJAX 回退（需要 csrf_token）
            if not candidates and self.csrf_token:
                ajax_url = (
                    "https://m.kuku.lu/recv._ajax.php?"
                    f"q={quote(mailaddress)}&nopost=1&csrf_token_check={self.csrf_token}"
                )
                ajax_resp = self.session.get(ajax_url, headers=self.default_headers, proxies=self.proxy, timeout=15)
                # URL 形态
                candidates += re.findall(r"smphone\.app\.recv\.view\.php\?num=(\d+)&key=([A-Za-z0-9]+)", ajax_resp.text)
                # openMailData 形态
                candidates += re.findall(r"openMailData\('(\d+)'\s*,\s*'([0-9a-fA-F]+)'\s*,", ajax_resp.text)

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
