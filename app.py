from flask import Flask, request, jsonify, render_template
from kukulu import Kukulu
from token_manager import TokenManager
import logging, os, json, random, time

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

# 缓存 {mail: {"code":xxx,"body":xxx,"time":xxx}}
cache = {}

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
        with open(os.path.join(APP_DIR, "custom_domains.txt"), "r", encoding="utf-8") as f:
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
    force_refresh = request.args.get("refresh") == "1"
    now = time.time()

    # 有缓存并且没强制刷新 → 直接返回缓存
    if mailaddr in cache and not force_refresh:
        return jsonify({
            "mailaddress": mailaddr,
            "code": cache[mailaddr]["code"],
            "body": cache[mailaddr]["body"],
            "cached": True
        })

    # 强制刷新或没缓存 → 请求 Kukulu
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

@app.route("/ui")
def ui_page():
    return render_template("index.html")

@app.route("/api/health")
def api_health():
    return {"ok": True}, 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
