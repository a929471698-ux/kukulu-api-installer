import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import quote

class Kukulu():
    def __init__(self, csrf_token=None, sessionhash=None, proxy=None):
        """
        回滚到你旧的最简初始化逻辑：
        - 不做跨域/强头乱写
        - 仅按你原先写法把 token 写到 session（不带 domain），
          然后 POST 一次 m.kuku.lu 建立会话。
        """
        self.csrf_token  = csrf_token
        self.sessionhash = sessionhash
        self.proxy       = proxy
        self.session     = requests.Session()

        if csrf_token and sessionhash:
            self.session.cookies.set("cookie_csrf_token", csrf_token)
            # 兼容可能传入的 URL 编码值
            shash = sessionhash.replace("%3A", ":") if "%3A" in sessionhash else sessionhash
            self.session.cookies.set("cookie_sessionhash", shash)
            self.session.post("https://m.kuku.lu", proxies=proxy)
        else:
            self.session.post("https://m.kuku.lu", proxies=proxy)

    def new_account(self):
        return {
            "csrf_token": self.session.cookies.get("cookie_csrf_token"),
            "sessionhash": self.session.cookies.get("cookie_sessionhash"),
        }

    def create_mailaddress(self):
        """
        回滚到你旧的“能创建”的写法：只调一次 addMailAddrByAuto&nopost=1&by_system=1
        然后把响应从第4个字符开始返回（去掉 'OK:'）。
        —— 这是你“当时能创建”的关键路径，不再做任何花活。
        """
        url = "https://m.kuku.lu/index.php?action=addMailAddrByAuto&nopost=1&by_system=1"
        resp = self.session.get(url, proxies=self.proxy)
        # 旧逻辑：直接截掉 'OK:' 前缀
        return resp.text[3:]

    def specify_address(self, address):
        """
        保留你原先的地址指定写法（当时能用的版本）
        """
        url = (
            "https://m.kuku.lu/index.php?action=addMailAddrByManual"
            "&nopost=1&by_system=1"
            f"&csrf_token_check={self.csrf_token}"
            f"&newdomain={address}"
        )
        resp = self.session.get(url, proxies=self.proxy)
        return resp.text[3:]

    def check_top_mail(self, mailaddress):
        """
        只修复“验证码解析”这一块，不影响创建：
        - 先看桌面页（kuku.lu/mailbox/xx）：抓 <a href="smphone.app.recv.view.php?...">
        - 如果桌面页抓不到 → 回退移动 AJAX（m.kuku.lu/recv._ajax.php）
          * 兼容 openMailData('num','key',...) 与明文 URL 两种形态
        - 拿到 num/key 后 POST smphone.app.recv.view.php ，再从正文里提取 6 位验证码
        """
        encoded_mail = quote(mailaddress)

        # Step A: 桌面页（kuku.lu/mailbox/...）
        try:
            inbox_url = f"https://kuku.lu/mailbox/{encoded_mail}"
            inbox_resp = self.session.get(inbox_url, proxies=self.proxy, timeout=10)
            soup = BeautifulSoup(inbox_resp.text, "html.parser")

            # 先从 a[href] 提 num/key
            candidates = []
            for a in soup.find_all("a", href=True):
                m = re.search(r"smphone\.app\.recv\.view\.php\?num=(\d+)&key=([A-Za-z0-9]+)", a["href"])
                if m:
                    candidates.append(m.groups())

            # 全文兜底一次（有些链接不是 a 标签挂载）
            if not candidates:
                for m in re.findall(
                    r"smphone\.app\.recv\.view\.php\?num=(\d+)&key=([A-Za-z0-9]+)", inbox_resp.text
                ):
                    candidates.append(m)
        except Exception:
            candidates = []

        # Step B: 移动 AJAX 回退（只有在桌面抓不到时才去）
        if not candidates and self.csrf_token:
            try:
                ajax_url = (
                    "https://m.kuku.lu/recv._ajax.php?"
                    f"q={encoded_mail}&nopost=1&csrf_token_check={self.csrf_token}"
                )
                ajax_resp = self.session.get(ajax_url, proxies=self.proxy, timeout=10)
                # 形态 1：明文 URL
                for m in re.findall(
                    r"smphone\.app\.recv\.view\.php\?num=(\d+)&key=([A-Za-z0-9]+)", ajax_resp.text
                ):
                    candidates.append(m)
                # 形态 2：openMailData('num','key',...)
                for m in re.findall(r"openMailData\('(\d+)'\s*,\s*'([0-9a-fA-F]+)'\s*,", ajax_resp.text):
                    candidates.append(m)
            except Exception:
                pass

        if not candidates:
            return None

        # Step C: 拿 num/key 拉正文
        for num, key in candidates:
            try:
                detail = self.session.post(
                    "https://m.kuku.lu/smphone.app.recv.view.php",
                    data={"num": num, "key": key, "noscroll": "1"},
                    proxies=self.proxy, timeout=10
                )
                text = BeautifulSoup(detail.text, "html.parser").get_text(" ", strip=True)
                m = re.search(r"\b\d{6}\b", text)
                if m:
                    return m.group()
            except Exception:
                continue

        return None
