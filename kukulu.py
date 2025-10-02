import requests
from bs4 import BeautifulSoup
import re
import random
from urllib.parse import quote

class Kukulu:
    def __init__(self, proxy=None):
        self.session = requests.Session()
        self.proxy = proxy

        self.csrf_token = None
        self.sessionhash = None

        # 初始化：先访问主页设置 Cookie
        self._initialize_cookies()

    def _random_user_agent(self):
        ua_list = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/114.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/113.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/117.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/110.0.0.0 Safari/537.36",
        ]
        return random.choice(ua_list)

    def _initialize_cookies(self):
        headers = {
            "User-Agent": self._random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        self.session.get("https://m.kuku.lu", headers=headers, proxies=self.proxy)

    def create_mailaddress(self):
        url = "https://m.kuku.lu/index.php?action=addMailAddrByAuto&nopost=1&by_system=1"
        headers = {
            "User-Agent": self._random_user_agent(),
            "Accept": "*/*",
            "Referer": "https://m.kuku.lu/",
        }
        response = self.session.get(url, headers=headers, proxies=self.proxy)

        self.csrf_token = self.session.cookies.get("cookie_csrf_token")
        self.sessionhash = self.session.cookies.get("cookie_sessionhash")

        return response.text[3:]  # 去掉开头的 "OK:"

    def check_top_mail(self, mailaddress):
        encoded = quote(mailaddress)
        inbox_url = f"https://kuku.lu/mailbox/{encoded}"

        headers = {
            "User-Agent": self._random_user_agent(),
            "Referer": inbox_url,
            "Origin": "https://m.kuku.lu",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        try:
            # Step 1: 加载收件箱页面
            resp = self.session.get(inbox_url, headers=headers, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")

            # Step 2: 抓邮件链接
            a_tags = soup.find_all("a", href=re.compile(r"smphone\\.app\\.recv\\.view\\.php\\?num=\\d+&key=\\w+"))
            for a in a_tags:
                href = a.get("href")
                match = re.search(r"num=(\\d+)&key=([a-zA-Z0-9]+)", href)
                if not match:
                    continue
                num, key = match.groups()

                # Step 3: 请求邮件内容（POST）
                post_resp = self.session.post(
                    "https://m.kuku.lu/smphone.app.recv.view.php",
                    data={"num": num, "key": key, "noscroll": "1"},
                    headers=headers,
                    timeout=10
                )

                # Step 4: 提取验证码
                soup_detail = BeautifulSoup(post_resp.text, "html.parser")
                text = soup_detail.get_text()
                code_match = re.search(r"\\b\\d{6}\\b", text)
                if code_match:
                    return code_match.group()

        except Exception as e:
            print(f"[ERROR] check_top_mail() 失败: {e}")

        return None

if __name__ == "__main__":
    kukulu = Kukulu()
    mail = kukulu.create_mailaddress()
    print(f"✅ 创建邮箱: {mail}")

    print("⏳ 等待接收验证码中...")
    import time
    for i in range(30):
        code = kukulu.check_top_mail(mail)
        if code:
            print(f"🎉 收到验证码: {code}")
            break
        else:
            print(f"[尝试 {i+1}/30] 暂无新邮件，等待 3 秒...")
            time.sleep(3)
    else:
        print("❌ 未收到验证码")
