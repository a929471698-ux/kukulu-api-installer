import requests
from bs4 import BeautifulSoup
import re
import random
from urllib.parse import quote, unquote
import os
from datetime import datetime

class Kukulu():
    def __init__(self, csrf_token=None, sessionhash=None, proxy=None):
        self.csrf_token = csrf_token
        self.sessionhash = sessionhash
        self.proxy = proxy
        self.session = requests.Session()

        # --- 关键：标准化并设置 cookie（含 domain/path）
        if csrf_token:
            self.session.cookies.set(
                "cookie_csrf_token",
                csrf_token,
                domain="m.kuku.lu",
                path="/"
            )
        if sessionhash:
            # 许多场景下缓存的是 URL 编码的 SHASH 值（SHASH%3Axxxx）
            shash = sessionhash
            if "%3A" in shash:
                shash = shash.replace("%3A", ":")
            self.session.cookies.set(
                "cookie_sessionhash",
                shash,
                domain="m.kuku.lu",
                path="/"
            )
        # 语言/保活同样在 m.kuku.lu 域设置，确保服务端识别
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

        # 走一遍 m.kuku.lu 初始化（贴近浏览器行为）
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

    def check_top_mail(self, mailaddress):
        """
        适配新版 kukulu：
        - 修正 cookie_sessionhash（SHASH: 而非 SHASH%3A）
        - /mailbox/ 页面可能含多层结构，使用 a+regex 双通道提取 num/key
        - 详情用 POST smphone.app.recv.view.php 获取正文
        - 调试文件落地到 debug_html/
        """
        # mailbox URL（保持你原来的入口不变）
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

            # Step 1: 打开收件箱
            inbox_resp = self.session.get(inbox_url, headers=headers, proxies=self.proxy, timeout=15)

            # 保存收件箱 HTML 便于你排查（你说必须完整输出/便于调试）
            self._save_html_debug(inbox_resp.text, tag=f"inbox_{self._safe_name(mailaddress)}")

            soup = BeautifulSoup(inbox_resp.text, "html.parser")

            # Step 2a: 先尝试 a 标签提取（新版常见）
            a_tags = soup.find_all("a", href=re.compile(r"smphone\.app\.recv\.view\.php\?num=\d+&key=[A-Za-z0-9]+"))
            candidates = []
            for a in a_tags:
                href = a.get("href") or ""
                m = re.search(r"num=(\d+)&key=([A-Za-z0-9]+)", href)
                if m:
                    candidates.append(m.groups())

            # Step 2b: 再用正则在整页兜底（应对深层嵌套/JS 注入）
            if not candidates:
                for m in re.findall(r"smphone\.app\.recv\.view\.php\?num=(\d+)&key=([A-Za-z0-9]+)", inbox_resp.text):
                    candidates.append(m)

            if not candidates:
                # 依然找不到，很可能还在首页/未挂载/cookie 不生效（你之前的 debug 就是首页）:contentReference[oaicite:3]{index=3}
                return None

            # Step 3: 逐个尝试抓详情正文
            detail_url = "https://m.kuku.lu/smphone.app.recv.view.php"
            for num, key in candidates:
                post_data = {"num": num, "key": key, "noscroll": "1"}
                detail_resp = self.session.post(
                    detail_url, data=post_data, headers=headers,
                    proxies=self.proxy, timeout=15
                )

                # 保存详情页 HTML
                self._save_html_debug(detail_resp.text, tag=f"detail_{num}")

                if detail_resp.status_code != 200:
                    continue

                # 提取六位验证码
                soup_detail = BeautifulSoup(detail_resp.text, "html.parser")
                text = soup_detail.get_text(" ", strip=True)
                code = re.search(r"\b\d{6}\b", text)
                if code:
                    return code.group()

        except Exception as e:
            print(f"[ERROR] check_top_mail failed: {e}")

        return None

    # === 工具方法 ===
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
