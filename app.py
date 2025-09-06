from flask import Flask, jsonify, request, render_template
from kukulu import Kukulu
from token_manager import TokenManager
import logging, os, json, random, time
from urllib.parse import unquote

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "data")
TOKENS_DB = os.path.join(DATA_DIR, "mail_tokens.json")
os.makedirs(DATA_DIR, exist_ok=True)
LOGS_DIR = os.path.join(APP_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(LOGS_DIR, "kukulu_api.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

CUSTOM_DOMAINS_FILE = os.path.join(APP_DIR, "custom_domains.txt")

def load_domains():
    if not os.path.exists(CUSTOM_DOMAINS_FILE):
        return []
    with open(CUSTOM_DOMAINS_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def save_domains(domains):
    with open(CUSTOM_DOMAINS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(domains) + "\n")

def load_map():
    if not os.path.exists(TOKENS_DB):
        return {}
    try:
        with open(TOKENS_DB, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_map(m):
    tmp = TOKENS_DB + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
    os.replace(tmp, TOKENS_DB)

def set_mapping(email, csrf, shash):
    m = load_map()
    m[email.lower()] = {"csrf_token": csrf, "sessionhash": shash, "ts": int(time.time())}
    save_map(m)

def get_mapping(email):
    return load_map().get(email.lower())

app = Flask(__name__, template_folder="templates", static_folder="static")
manager = TokenManager()

# --- 创建邮箱（随机后缀）
@app.route("/api/create_random", methods=["GET"])
@app.route("/api/create_随机后缀", methods=["GET"])
def api_create_random():
    token = manager.get_token()
    k = Kukulu(token['csrf_token'], token['sessionhash'])
    mail = k.create_mailaddress()
    set_mapping(mail, token['csrf_token'], token['sessionhash'])
    logging.info(f"[CREATE_AUTO] mail={mail} token={json.dumps(token)}")
    return jsonify({"mailaddress": mail, **token})

# --- 创建邮箱（指定后缀池随机挑一个）
@app.route("/api/create_custom", methods=["GET"])
@app.route("/api/create_指定后缀", methods=["GET"])
def api_create_custom():
    domains = load_domains()
    if not domains:
        return jsonify({"error": "no custom domains"}), 400
    domain = random.choice(domains)
    token = manager.get_token()
    k = Kukulu(token['csrf_token'], token['sessionhash'])
    mail = k.specify_address(domain)
    set_mapping(mail, token['csrf_token'], token['sessionhash'])
    logging.info(f"[CREATE_CUSTOM] mail={mail} domain={domain} token={json.dumps(token)}")
    return jsonify({"mailaddress": mail, **token})

# --- 仅传邮箱获取验证码（自动用缓存 token，失败轮换）
@app.route("/api/check_captcha/<path:mailaddr>", methods=["GET"])
def api_check_captcha(mailaddr):
    email = unquote(mailaddr)
    rec = get_mapping(email)
    if not rec:
        return jsonify({"error": "no token cached"}), 404
    k = Kukulu(rec["csrf_token"], rec["sessionhash"])
    code = k.check_top_mail(email)
    if code:
        return jsonify({"mailaddress": email, "code": code})
    token = rec
    for _ in range(4):
        token = manager.rotate_token()
        k = Kukulu(token["csrf_token"], token["sessionhash"])
        code = k.check_top_mail(email)
        if code:
            set_mapping(email, token["csrf_token"], token["sessionhash"])
            return jsonify({"mailaddress": email, "code": code})
    return jsonify({"mailaddress": email, "code": None}), 404

# --- 无密钥的后缀池管理（GET/POST）
@app.route("/api/domains", methods=["GET", "POST"])
def api_domains():
    if request.method == "GET":
        return jsonify({"domains": load_domains()})
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, list):
        return jsonify({"error": "body must be a JSON array of domains"}), 400
    domains_clean = [str(x).strip() for x in data if str(x).strip()]
    save_domains(domains_clean)
    return jsonify({"ok": True, "domains": domains_clean})

# --- 历史记录（从 data/mail_tokens.json 读取）
@app.route("/api/history", methods=["GET"])
def api_history():
    m = load_map()
    history = [
        {"mailaddress": mail, **info}
        for mail, info in sorted(m.items(), key=lambda kv: kv[1].get("ts", 0), reverse=True)
    ]
    return jsonify({"history": history})

@app.route("/ui")
def ui_page():
    return render_template("index.html")

@app.route("/api/health")
def api_health():
    return {"ok": True}, 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
