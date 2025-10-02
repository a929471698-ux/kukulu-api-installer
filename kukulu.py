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

        if csrf_token and sessionhash:
            self.session.cookies.set("cookie_csrf_token", csrf_token)
            self.session.cookies.set("cookie_sessionhash", sessionhash)
            self.session.cookies.set("cookie_setlang", "cn")
            self.session.cookies.set("cookie_keepalive_insert", "1")

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
        return resp.text[3:]

    def specify_address(self, address):
        url = f"https://m.kuku.lu/index.php?action=addMailAddrByManual&nopost=1&by_system=1&csrf_token_check={self.csrf_token}&newdomain={address}"
        resp = self.session.get(url, proxies=self.proxy, headers=self.default_headers)
        return resp.text[3:]

    def check_top_mail(self, mailaddress):
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

            inbox_resp = self.session.get(inbox_url, headers=headers, timeout=10)
            soup = BeautifulSoup(inbox_resp.text, "html.parser")

            a_tags = soup.find_all("a", href=re.compile(r"smphone\\.app\\.recv\\.view\\.php\\?num=\\d+&key=[a-zA-Z0-9]+"))
            if not a_tags:
                return None

            for a in a_tags:
                href = a["href"]
                match = re.search(r"num=(\\d+)&key=([a-zA-Z0-9]+)", href)
                if not match:
                    continue
                num, key = match.groups()

                detail_url = "https://m.kuku.lu/smphone.app.recv.view.php"
                detail_resp = self.session.post(
                    detail_url,
                    data={"num": num, "key": key, "noscroll": "1"},
                    headers=headers,
                    timeout=10
                )

                if detail_resp.status_code != 200:
                    continue

                soup_detail = BeautifulSoup(detail_resp.text, "html.parser")
                text = soup_detail.get_text()
                code = re.search(r"\\b\\d{6}\\b", text)
                if code:
                    return code.group()

        except Exception as e:
            print(f"[ERROR] check_top_mail failed: {e}")

        return None
