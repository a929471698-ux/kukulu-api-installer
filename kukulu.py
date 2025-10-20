import requests
from bs4 import BeautifulSoup
import re

class Kukulu:
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
        """创建新账号并返回 token"""
        return {
            "csrf_token": self.session.cookies["cookie_csrf_token"],
            "sessionhash": self.session.cookies["cookie_sessionhash"],
        }

    def create_mailaddress(self):
        """自动创建邮箱（含上限检测）"""
        resp = self.session.get(
            "https://m.kuku.lu/index.php?action=addMailAddrByAuto&nopost=1&by_system=1",
            proxies=self.proxy,
        )
        text = resp.text.strip()
        if "メールアドレスの最大数を超過しました" in text:
            raise RuntimeError("MAX_ADDRESS_REACHED")
        return text[3:]

    def specify_address(self, address):
        """指定域名创建邮箱"""
        resp = self.session.get(
            f"https://m.kuku.lu/index.php?action=addMailAddrByManual&nopost=1&by_system=1"
            f"&csrf_token_check={self.csrf_token}&newdomain={address}",
            proxies=self.proxy,
        )
        text = resp.text.strip()
        if "メールアドレスの最大数を超過しました" in text:
            raise RuntimeError("MAX_ADDRESS_REACHED")
        return text[3:]

    def check_top_mail(self, mailaddress):
        """检查邮箱验证码"""
        mailaddress = mailaddress.replace("@", "%40")
        mails = self.session.get(
            f"https://m.kuku.lu/recv._ajax.php?q={mailaddress}&nopost=1&csrf_token_check={self.csrf_token}",
            proxies=self.proxy,
        )
        soup = BeautifulSoup(mails.text, "html.parser")
        script = soup.find_all("script")
        match = re.search("(openMailData[^ ]+)", str(script))
        if not match:
            return None
        openMailData = match.group().replace("openMailData(", "")
        maildata = re.findall(f"{openMailData} [^ ]+", str(script))[1].split("'")
        mail = self.session.post(
            "https://m.kuku.lu/smphone.app.recv.view.php",
            data={"num": maildata[1], "key": maildata[3], "noscroll": "1"},
            proxies=self.proxy,
        )
        soup = BeautifulSoup(mail.text, "html.parser")
        node = soup.find(dir="ltr")
        if not node:
            return None
        text = node.text
        code = re.search(r"\b\d{6}\b", text)
        return code.group() if code else None
