import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import quote

class Kukulu():
    def __init__(self, csrf_token=None, sessionhash=None, proxy=None):
        self.csrf_token = csrf_token
        self.sessionhash = sessionhash
        self.proxy = proxy
        self.session = requests.Session()
        if csrf_token and sessionhash:
            self.session.cookies.set("cookie_csrf_token", csrf_token)
            self.session.cookies.set("cookie_sessionhash", sessionhash)
            self.session.post("https://m.kuku.lu", proxies=proxy)
        else:
            self.session.post("https://m.kuku.lu", proxies=proxy)

    def new_account(self):
        return {
            "csrf_token": self.session.cookies["cookie_csrf_token"],
            "sessionhash": self.session.cookies["cookie_sessionhash"]
        }

    def create_mailaddress(self):
        return self.session.get(
            "https://m.kuku.lu/index.php?action=addMailAddrByAuto&nopost=1&by_system=1",
            proxies=self.proxy
        ).text[3:]

    def specify_address(self, address):
        return self.session.get(
            f"https://m.kuku.lu/index.php?action=addMailAddrByManual&nopost=1&by_system=1&t=1716696234&csrf_token_check={self.csrf_token}&newdomain={address}",
            proxies=self.proxy
        ).text[3:]

    def check_top_mail(self, mailaddress):
        encoded = quote(mailaddress)
        inbox_url = f"https://kuku.lu/mailbox/{encoded}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        }

        try:
            # Step 1: 获取收件箱页面
            inbox_resp = self.session.get(inbox_url, headers=headers, timeout=10)
            soup = BeautifulSoup(inbox_resp.text, "html.parser")

            # Step 2: 提取邮件链接（POST 参数）
            view_links = soup.select("a[href*='smphone.app.recv.view.php']")
            if not view_links:
                return None

            for link in view_links:
                href = link.get("href")
                match = re.search(r"num=(\d+)&key=([a-zA-Z0-9]+)", href)
                if not match:
                    continue
                num, key = match.groups()

                # Step 3: 访问邮件详情内容（POST）
                detail_url = "https://kuku.lu/smphone.app.recv.view.php"
                detail_resp = self.session.post(detail_url, data={
                    "num": num,
                    "key": key,
                    "noscroll": "1"
                }, headers=headers, timeout=10)

                # Step 4: 提取正文中的验证码
                mail_soup = BeautifulSoup(detail_resp.text, "html.parser")
                text = mail_soup.get_text()
                code = re.search(r"\b\d{6}\b", text)
                if code:
                    return code.group()

        except Exception as e:
            print(f"[ERROR] check_top_mail failed: {e}")

        return None
