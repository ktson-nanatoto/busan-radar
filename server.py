"""
server.py — 부산 청약 대시보드 Flask 서버
실행: python server.py
접속: http://localhost:5000
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

from flask import Flask, jsonify, send_file, request

BASE_DIR  = Path(__file__).parent
DATA_FILE = BASE_DIR / "data.json"
DASHBOARD = BASE_DIR / "dashboard.html"
CRAWLER   = BASE_DIR / "crawler.py"

app = Flask(__name__)


def load_data() -> dict:
    if not DATA_FILE.exists():
        return {"apts": [], "updatedAt": None, "errors": []}
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


@app.route("/")
def index():
    return send_file(DASHBOARD)


@app.route("/data.json")
@app.route("/api/data")
def api_data():
    return jsonify(load_data())


@app.route("/api/apts")
def api_apts():
    data = load_data()
    apts = data.get("apts", [])
    gu = request.args.get("gu")
    if gu:
        apts = [a for a in apts if gu in a.get("regionName", "")]
    return jsonify({"updatedAt": data.get("updatedAt"), "count": len(apts), "apts": apts})


@app.route("/api/apt/<apt_hash>")
def api_apt_detail(apt_hash):
    data = load_data()
    apt = next((a for a in data["apts"] if a["hash"] == apt_hash), None)
    if not apt:
        return jsonify({"error": "단지를 찾을 수 없습니다"}), 404
    return jsonify(apt)


@app.route("/api/crawl", methods=["POST"])
def api_crawl():
    quick = request.args.get("quick") == "1"
    cmd = [sys.executable, str(CRAWLER)]
    if quick:
        cmd.append("--no-detail")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=str(BASE_DIR))
        if result.returncode == 0:
            data = load_data()
            return jsonify({"success": True, "updatedAt": data.get("updatedAt"), "count": len(data.get("apts", []))})
        return jsonify({"success": False, "error": result.stderr[-500:]}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "타임아웃 (5분 초과)"}), 500


@app.route("/api/status")
def api_status():
    data = load_data()
    updated = data.get("updatedAt")
    stale = False
    if updated:
        delta = datetime.now() - datetime.fromisoformat(updated)
        stale = delta.total_seconds() > 86400
    return jsonify({
        "server": "running",
        "dataExists": DATA_FILE.exists(),
        "updatedAt": updated,
        "aptCount": len(data.get("apts", [])),
        "stale": stale,
        "errors": data.get("errors", []),
    })


if __name__ == "__main__":
    print("=" * 50)
    print("  부산 청약 대시보드 서버")
    print("  http://localhost:5000")
    print("=" * 50)
    if not DATA_FILE.exists():
        print("\n⚠️  data.json 없음 — 먼저 실행:")
        print("   python crawler.py --no-detail\n")
    app.run(host="127.0.0.1", port=5000, debug=False)