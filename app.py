from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import time
import re
from datetime import datetime
from threading import Lock
import json
import os

# ------------------------
# APP SETUP
# ------------------------
app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["1 per second"]
)

# ------------------------
# IN-MEMORY CACHE
# ------------------------
cache = {}
inflight = {}
lock = Lock()

# ------------------------
# DATABASE (SEARCH COUNTER)
# ------------------------
DB_PATH = os.path.join(os.getcwd(), "database", "stats.json")

def load_stats():
    if not os.path.exists(DB_PATH):
        return {"month": "", "count": 0}
    with open(DB_PATH, "r") as f:
        return json.load(f)

def save_stats(data):
    with open(DB_PATH, "w") as f:
        json.dump(data, f, indent=2)

# ------------------------
# HELPERS
# ------------------------
def normalize_name(name: str) -> str:
    return name.strip().lower()

def valid_name(name: str) -> bool:
    return re.fullmatch(r"[a-z0-9_]{3,16}", name) is not None

def check_availability_somehow(name: str):
    # placeholder
    return None

# ------------------------
# API ROUTES
# ------------------------
@app.route("/api/check", methods=["POST"])
@limiter.limit("1 per second")
def check_name():
    data = request.get_json(force=True, silent=True)
    if not data or "name" not in data:
        return jsonify(error="Missing name"), 400

    name = normalize_name(data["name"])
    if not valid_name(name):
        return jsonify(error="Invalid username format"), 400

    # update monthly searches
    with lock:
        stats = load_stats()
        current_month = datetime.utcnow().strftime("%Y-%m")

        if stats["month"] != current_month:
            stats["month"] = current_month
            stats["count"] = 0

        stats["count"] += 1
        save_stats(stats)

    if name in cache:
        return jsonify({
            "name": name,
            **cache[name],
            "cached": True
        })

    with lock:
        if inflight.get(name):
            while inflight.get(name):
                time.sleep(0.1)
            return jsonify({
                "name": name,
                **cache[name],
                "cached": False,
                "shared": True
            })
        inflight[name] = True

    try:
        time.sleep(1)

        result = check_availability_somehow(name)
        payload = {
            "available": result,
            "checkedAt": datetime.utcnow().isoformat() + "Z"
        }

        cache[name] = payload

        return jsonify({
            "name": name,
            **payload,
            "cached": False
        })

    finally:
        with lock:
            inflight.pop(name, None)

@app.route("/api/searches")
def searches():
    stats = load_stats()
    return jsonify({"count": stats["count"]})

# ------------------------
# FRONTEND
# ------------------------
@app.route("/")
def index():
    return send_file(os.path.join(os.getcwd(), "public", "index.html"))

# serve /public/* files (images, backgrounds, etc.)
@app.route("/public/<path:filename>")
def public_files(filename):
    return send_from_directory("public", filename)

# ------------------------
# START SERVER (RENDER SAFE)
# ------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port, debug=False)