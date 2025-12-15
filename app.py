from flask import Flask, request, jsonify, send_from_directory
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import time
import re
from datetime import datetime
from threading import Lock
import json
import os

app = Flask(__name__, static_folder="public")

# --- rate limiting (120 checks per minute per IP)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["120 per minute"]
)

# --- in-memory cache (swap to Redis later)
cache = {}      # name -> { available, checkedAt }
inflight = {}   # name -> bool
lock = Lock()   # prevent double checks

# ------------------------
# DATABASE (SEARCH COUNTER)
# ------------------------
DB_PATH = "database/stats.json"

def load_stats():
    if not os.path.exists(DB_PATH):
        return {"month": "", "count": 0}
    with open(DB_PATH, "r") as f:
        return json.load(f)

def save_stats(data):
    with open(DB_PATH, "w") as f:
        json.dump(data, f)


def normalize_name(name: str) -> str:
    return name.strip().lower()


def valid_name(name: str) -> bool:
    # adjust when Hytale rules are confirmed
    return re.fullmatch(r"[a-z0-9_]{3,16}", name) is not None


def check_availability_somehow(name: str):
    """
    PLACEHOLDER.
    Replace this ONLY with an official / allowed check.
    Return:
      True  -> available
      False -> taken
      None  -> unknown
    """
    return None


@app.route("/api/check", methods=["POST"])
@limiter.limit("1 per second")
def check_name():
    data = request.get_json(force=True, silent=True)
    if not data or "name" not in data:
        return jsonify(error="Missing name"), 400

    name = normalize_name(data["name"])

    if not valid_name(name):
        return jsonify(error="Invalid username format"), 400

    # ------------------------
    # UPDATE MONTHLY SEARCHES
    # ------------------------
    with lock:
        stats = load_stats()
        current_month = datetime.utcnow().strftime("%Y-%m")

        if stats["month"] != current_month:
            stats["month"] = current_month
            stats["count"] = 0

        stats["count"] += 1
        save_stats(stats)

    # instant return if cached
    if name in cache:
        return jsonify({
            "name": name,
            **cache[name],
            "cached": True
        })

    # prevent duplicate checks for same name
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
        # intentional delay (~1s)
        time.sleep(1)

        result = check_availability_somehow(name)

        payload = {
            "available": result,  # True / False / None
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
    return jsonify({
        "count": stats["count"]
    })


@app.route("/")
def index():
    return send_from_directory("public", "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("public", path)


if __name__ == "__main__":
    app.run(debug=True, port=3000)
