# kukulu.py
import requests
from bs4 import BeautifulSoup
import re
import random
from urllib.parse import quote

class Kukulu():
    def __init__(self, csrf_token=None, sessionhash=None, proxy=None):
        self.csrf_token = csrf_token
        self.sessionhash = sessionhash
        self.proxy = proxy
        self.session = requests.Session()

        # === 关键：把会话 Cookie 同时写入 m.kuku.lu 与 kuku.lu 两个域，并修正 SHASH%3A → SHASH:
        def _set_cookie(name, value, domains=("m.kuku.lu", "kuku.lu")):
            for d in domains:
                # Requests 的 CookieJar 支持 domain/path 参数
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
            "User-Agent": self._random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": random.choice([
                "en-US,en;q=0.5",
                "zh-CN,zh;q=0.9",
                "ja,en-US;q=0.9,en;q=0.8",
            ]),
            "Connection": "keep-alive",
        }

        # 预热两个域（失败也不抛）
        try:
            self.session.get("https://m.kuku.lu", headers=self.default_headers, timeout=10, proxies=self.proxy)
            self.session.get("https://kuku.lu",  headers=self.default_headers, timeout=10, proxies=self.proxy)
        except Exception:
            pass

    def _random_user_agent(self):
        ua_list = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/114.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/113.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/117.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/110.0.0.0 Safari/537.36",
        ]
        return random.choice(ua_list)

    def new_account(self):
        return {
            "csrf_token": self.session.cookies.get("cookie_csrf_token"),
            "sessionhash": self.session.cookies.get("cookie_sessionhash"),
        }

    def create_mailaddress(self):
        url = "https://m.kuku.lu/index.php?action=addMailAddrByAuto&nopost=1&by_system=1"
        resp = self.session.get(url, proxies=self.proxy, headers=self.default_headers, timeout=15)
        return resp.text[3:]  # 去掉 "OK:"

    def specify_address(self, address):
        url = f"https://m.kuku.lu/index.php?action=addMailAddrByManual&nopost=1&by_system=1&csrf_token_check={self.csrf_token}&newdomain={address}"
        resp = self.session.get(url, proxies=self.proxy, headers=self.default_headers, timeout=15)
        return resp.text[3:]

    # ====== 内部辅助 ======
    def _set_current_mail_cookie(self, mailaddress: str):
        # 声明当前邮箱（两个域都写），贴近浏览器行为，避免 /mailbox 被踢回主页
        for d in ("m.kuku.lu", "kuku.lu"):
            self.session.cookies.set("cookie_last_q", mailaddress, domain=d, path="/")
        # 这两个指示位在实际浏览器中常见，保持一致更稳
        self.session.cookies.set("cookie_last_page_recv", "0", domain="m.kuku.lu", path="/")
        self.session.cookies.set("cookie_last_page_addrlist", "0", domain="m.kuku.lu", path="/")

    def _extract_candidates_from_desktop(self, html: str, soup: BeautifulSoup):
        """桌面页候选提取：a[href] 优先 + 全文正则兜底"""
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
        """
        移动 AJAX 候选提取：
        1) 明文 URL: smphone.app.recv.view.php?num=...&key=...
        2) JS: openMailData('num','key',...) —— 常见于 m 站回包
        """
        candidates = []
        candidates += re.findall(r"smphone\.app\.recv\.view\.php\?num=(\d+)&key=([A-Za-z0-9]+)", html)
        candidates += re.findall(r"openMailData\('(\d+)'\s*,\s*'([0-9a-fA-F]+)'\s*,", html)
        return candidates

    # ====== 外部调用的主函数（保持签名不变）======
    def check_top_mail(self, mailaddress):
        """
        行为保持不变：
        - 先挂载 cookie_last_q
        - 桌面页提取 num/key；若无 → 回退 m 站 AJAX（含 openMailData 解析）
        - 详情页 POST smphone.app.recv.view.php，正则提取 6 位验证码
        """
        self._set_current_mail_cookie(mailaddress)

        encoded = quote(mailaddress)
        inbox_url = f"https://kuku.lu/mailbox/{encoded}"

        headers = {
            "User-Agent": self._random_user_agent(),
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
            # 1) 桌面收件箱（kuku.lu）
            inbox_resp = self.session.get(inbox_url, headers=headers, proxies=self.proxy, timeout=15)
            soup = BeautifulSoup(inbox_resp.text, "html.parser")
            candidates = self._extract_candidates_from_desktop(inbox_resp.text, soup)

            # 2) 回退：移动 AJAX（m.kuku.lu）—— 仅当桌面抓不到候选时
            if not candidates and self.csrf_token:
                ajax_url = (
                    "https://m.kuku.lu/recv._ajax.php?"
                    f"q={quote(mailaddress)}&nopost=1&csrf_token_check={self.csrf_token}"
                )
                ajax_resp = self.session.get(ajax_url, headers=self.default_headers, proxies=self.proxy, timeout=15)
                candidates = self._extract_candidates_from_mobile_ajax(ajax_resp.text)

            if not candidates:
                return None

            # 3) 详情正文（POST）
            detail_url = "https://m.kuku.lu/smphone.app.recv.view.php"
            for num, key in candidates:
                post_data = {"num": num, "key": key, "noscroll": "1"}
                detail_resp = self.session.post(
                    detail_url, data=post_data, headers=headers,
                    proxies=self.proxy, timeout=15
                )
                if detail_resp.status_code != 200:
                    continue

                text = BeautifulSoup(detail_resp.text, "html.parser").get_text(" ", strip=True)
                m = re.search(r"\b\d{6}\b", text)
                if m:
                    return m.group()

        except Exception:
            # 保持静默失败（你的 API 逻辑会轮转 token 或返回 None/404）
            pass

        return None
