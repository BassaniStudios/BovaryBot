"""Lightweight health endpoint for hosts that need a web process."""
from flask import Flask, jsonify
from threading import Thread
from datetime import datetime, timezone

app = Flask("")
_started_at = datetime.now(timezone.utc)


@app.route("/")
def home():
    return "🤖 O bot está ativo e rodando!"


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "bovary-bot",
        "uptime_seconds": int((datetime.now(timezone.utc) - _started_at).total_seconds()),
    })


def run():
    app.run(host="0.0.0.0", port=8080)


def keep_alive():
    t = Thread(target=run, daemon=True)
    t.start()
