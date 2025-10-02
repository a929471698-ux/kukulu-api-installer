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

        # 设置 cookie 模拟登录
        if csrf_token and sessionhash:
            self.session.cookies.set("cookie_csrf_token", csrf_token)
            self.session.cookies.set("cookie_sessionhash", sessionhash)

        # 设置随机默认 headers（浏览器伪装）
        self.default_headers = {
            "User-Agent": self._random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": random.choice([
                "en-US,en;q=0.5",
                "ja,en-US;q=0.9,en;q=0.8",
                "zh-CN,zh;q=0.9,en;q=0.8",
            ]),
            "Connection": "keep-alive",
        }

        # 初始化 session（请求主页模拟一次访问）
        self.session.post("https://m.kuku.lu", proxies=self.proxy, headers=self.default_headers)

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
        resp = self.session.get(url, proxies=self.proxy, headers=self.default_headers)
        return resp.text[3:]  # 去掉前缀 "OK:"

    def specify_address(self, address):
        url = f"https://m.kuku.lu/index.php?action=addMailAddrByManual&nopost=1&by_system=1&t=1716696234&csrf_token_check={self.csrf_token}&newdomain={address}"
        resp = self.session.get(url, proxies=self.proxy, headers=self.default_headers)
        return resp.text[3:]

    def check_top_mail(self, mailaddress):
        encoded = quote(mailaddress)
        inbox_url = f"https://kuku.lu/mailbox/{encoded}"

        inbox_headers = dict(self.default_headers)
        inbox_headers["Referer"] = inbox_url

        try:
            # Step 1: 收件箱页面
            resp = self.session.get(inbox_url, headers=inbox_headers, timeout=10, proxies=self.proxy)
            soup = BeautifulSoup(resp.text, "html.parser")

            # Step 2: 找邮件链接中的 num 和 key
            links = soup.select("a[href*='smphone.app.recv.view.php']")
            if not links:
                return None

            for link in links:
                href = link.get("href")
                match = re.search(r"num=(\d+)&key=([a-zA-Z0-9]+)", href)
                if not match:
                    continue
                num, key = match.groups()

                # Step 3: 构造 POST 请求获取邮件内容
                post_url = "https://kuku.lu/smphone.app.recv.view.php"
                post_data = {
                    "num": num,
                    "key": key,
                    "noscroll": "1",
                }
                detail_headers = dict(inbox_headers)
                detail_headers["Origin"] = "https://kuku.lu"
                detail_headers["Content-Type"] = "application/x-www-form-urlencoded"

                resp = self.session.post(post_url, data=post_data, headers=detail_headers, timeout=10, proxies=self.proxy)
                soup_detail = BeautifulSoup(resp.text, "html.parser")
                text = soup_detail.get_text()
                code = re.search(r"\b\d{6}\b", text)
                if code:
                    return code.group()

        except Exception as e:
            print(f"[ERROR] check_top_mail failed: {e}")

        return None
