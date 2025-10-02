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
        encoded_mail = quote(mailaddress)
        url = f"https://kuku.lu/mailbox/{encoded_mail}"
        resp = self.session.get(url, proxies=self.proxy, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        # 新版 kukulu 页面适配（多个 class，向后兼容）
        mail_divs = soup.select("div.mail_item, div.mail_body, div.mailcontent")
        if not mail_divs:
            return None

        for div in mail_divs:
            text = div.get_text()
            code = re.search(r"\b\d{6}\b", text)
            if code:
                return code.group()

        return None
