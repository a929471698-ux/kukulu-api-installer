from flask import Flask, request, jsonify, render_template
from kukulu import Kukulu
from token_manager import TokenManager
import logging, os, random, time

APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(APP_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(LOGS_DIR, "kukulu_api.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config['JSON_AS_ASCII'] = False
manager = TokenManager()

# 缓存最近一次查询结果 {mail: {"code":..., "body":..., "time":...}}
cache = {}
MIN_INTERVAL = 5   # 最小查询间隔秒，避免过于频繁打 Kukulu

CUSTOM_DOMAINS_FILE = os.path.join(APP_DIR, "custom_domains.txt")

@app.route("/api/create_random", methods=["GET"])
def api_create_random():
    token = manager.get_token()
    k = Kukulu(token['csrf_token'], token['sessionhash'])
    mail = k.create_mailaddress()
    return jsonify({
        "mailaddress": mail,
        "csrf_token": token['csrf_token'],
        "sessionhash": token['sessionhash']
    })

@app.route("/api/create_custom", methods=["GET"])
def api_create_custom():
    domains = []
    try:
        with open(CUSTOM_DOMAINS_FILE, "r", encoding="utf-8") as f:
            domains = [line.strip() for line in f if line.strip()]
    except:
        pass

    if not domains:
        return jsonify({"error": "no custom domains"}), 400

    domain = random.choice(domains)
    token = manager.get_token()
    k = Kukulu(token['csrf_token'], token['sessionhash'])
    mail = k.specify_address(domain)
    return jsonify({
        "mailaddress": mail,
        "csrf_token": token['csrf_token'],
        "sessionhash": token['sessionhash']
    })

@app.route("/api/check_captcha/<path:mailaddr>", methods=["GET"])
def api_check_captcha(mailaddr):
    now = time.time()
    # 限频：同一邮箱短时间重复请求 → 返回缓存
    if mailaddr in cache and now - cache[mailaddr]["time"] < MIN_INTERVAL:
        result = cache[mailaddr]
        return jsonify({
            "mailaddress": mailaddr,
            "code": result["code"],
            "body": result["body"],
            "cached": True
        })

    token = manager.get_token()
    k = Kukulu(token['csrf_token'], token['sessionhash'], mailaddr)
    result = k.check_top_mail(mailaddr)

    cache[mailaddr] = {
        "code": result.get("code"),
        "body": result.get("body"),
        "time": now
    }

    return jsonify({
        "mailaddress": mailaddr,
        "code": result.get("code"),
        "body": result.get("body"),
        "cached": False
    })

@app.route("/api/domains", methods=["GET", "POST"])
def api_domains():
    if request.method == "GET":
        if not os.path.exists(CUSTOM_DOMAINS_FILE):
            return jsonify({"domains": []})
        with open(CUSTOM_DOMAINS_FILE, "r", encoding="utf-8") as f:
            domains = [line.strip() for line in f if line.strip()]
        return jsonify({"domains": domains})

    if request.method == "POST":
        data = request.get_json(force=True, silent=True)
        if not isinstance(data, list):
            return jsonify({"error": "必须是字符串数组"}), 400
        with open(CUSTOM_DOMAINS_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(data) + "\n")
        return jsonify({"ok": True, "domains": data})

@app.route("/ui")
def ui_page():
    return render_template("index.html")

@app.route("/api/health")
def api_health():
    return {"ok": True}, 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
