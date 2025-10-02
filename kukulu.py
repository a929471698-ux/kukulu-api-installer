# kukulu.py  —— 仅替换本文件；面板(app.py等)一律不改
import requests
from bs4 import BeautifulSoup
import re
import random
from urllib.parse import quote
import os
from datetime import datetime

class Kukulu():
    def __init__(self, csrf_token=None, sessionhash=None, proxy=None):
        self.csrf_token = csrf_token
        self.sessionhash = sessionhash
        self.proxy = proxy
        self.session = requests.Session()

        # --- 关键：在 m.kuku.lu 域设置必要 cookie（并修正 SHASH）
        if csrf_token:
            self.session.cookies.set(
                "cookie_csrf_token", csrf_token,
                domain="m.kuku.lu", path="/"
            )
        if sessionhash:
            shash = sessionhash.replace("%3A", ":") if "%3A" in sessionhash else sessionhash
            self.session.cookies.set(
                "cookie_sessionhash", shash,
                domain="m.kuku.lu", path="/"
            )
        # 语言/保活
        self.session.cookies.set("cookie_setlang", "cn", domain="m.kuku.lu", path="/")
        self.session.cookies.set("cookie_keepalive_insert", "1", domain="m.kuku.lu", path="/")

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

        # 模拟浏览器先触发一次
        try:
            self.session.post("https://m.kuku.lu", proxies=self.proxy, headers=self.default_headers, timeout=10)
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
        return resp.text[3:]

    def specify_address(self, address):
        url = f"https://m.kuku.lu/index.php?action=addMailAddrByManual&nopost=1&by_system=1&csrf_token_check={self.csrf_token}&newdomain={address}"
        resp = self.session.get(url, proxies=self.proxy, headers=self.default_headers, timeout=15)
        return resp.text[3:]

    def _set_current_mail_cookie(self, mailaddress: str):
        """
        让服务器“知道”你要看的邮箱是谁：
        - cookie_last_q = 当前邮箱（URL 编码由服务器处理，这里直接放原文也能被接受）
        - 两个域都写：m.kuku.lu + kuku.lu
        """
        try:
            self.session.cookies.set("cookie_last_q", mailaddress, domain="m.kuku.lu", path="/")
            self.session.cookies.set("cookie_last_q", mailaddress, domain="kuku.lu",   path="/")
            # 与 UI 行为一致，补充这两个“最近页面指示”也有助于稳定
            self.session.cookies.set("cookie_last_page_recv", "0", domain="m.kuku.lu", path="/")
            self.session.cookies.set("cookie_last_page_addrlist", "0", domain="m.kuku.lu", path="/")
        except Exception:
            pass

    def check_top_mail(self, mailaddress):
        """
        修复点：
        - 先把当前邮箱写入 cookie_last_q（两个域都写），避免 /mailbox 被踢回首页
        - 纠正 SHASH%3A → SHASH:
        - a选择器 + 全文正则 两套提取 num/key，避免嵌套丢失
        - 详情页 POST 拉取正文；保存 debug_html 便于复核
        """
        self._set_current_mail_cookie(mailaddress)

        encoded = quote(mailaddress)
        inbox_url = f"https://kuku.lu/mailbox/{encoded}"

        try:
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

            # Step 1: 打开收件箱（若没挂载/没cookie_last_q，常被重定向到首页）
            inbox_resp = self.session.get(inbox_url, headers=headers, proxies=self.proxy, timeout=15)

            # 落地调试
            self._save_html_debug(inbox_resp.text, tag=f"inbox_{self._safe_name(mailaddress)}")

            soup = BeautifulSoup(inbox_resp.text, "html.parser")

            # Step 2a: a标签提取
            candidates = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                m = re.search(r"smphone\.app\.recv\.view\.php\?num=(\d+)&key=([A-Za-z0-9]+)", href)
                if m:
                    candidates.append(m.groups())

            # Step 2b: 全文正则兜底
            if not candidates:
                for m in re.findall(r"smphone\.app\.recv\.view\.php\?num=(\d+)&key=([A-Za-z0-9]+)", inbox_resp.text):
                    candidates.append(m)

            if not candidates:
                return None

            # Step 3: 拉正文
            detail_url = "https://m.kuku.lu/smphone.app.recv.view.php"
            for num, key in candidates:
                post_data = {"num": num, "key": key, "noscroll": "1"}
                detail_resp = self.session.post(
                    detail_url, data=post_data, headers=headers,
                    proxies=self.proxy, timeout=15
                )
                self._save_html_debug(detail_resp.text, tag=f"detail_{num}")

                if detail_resp.status_code != 200:
                    continue

                text = BeautifulSoup(detail_resp.text, "html.parser").get_text(" ", strip=True)
                code = re.search(r"\b\d{6}\b", text)
                if code:
                    return code.group()

        except Exception as e:
            print(f"[ERROR] check_top_mail failed: {e}")

        return None

    # === 工具 ===
    def _safe_name(self, s: str) -> str:
        return s.replace("@", "_").replace("/", "_").replace("\\", "_")

    def _save_html_debug(self, html_text: str, tag: str):
        try:
            os.makedirs("debug_html", exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fp = os.path.join("debug_html", f"{tag}_{ts}.html")
            with open(fp, "w", encoding="utf-8") as f:
                f.write(html_text)
            print(f"[DEBUG] HTML saved → {fp}")
        except Exception:
            pass
