"""Tiny Flask service used as the target for the watchdog."""
import logging
import os
import sys

from flask import Flask, jsonify, request

app = Flask(__name__)

# Send request logs to stdout so systemd/journald (or the console) captures them.
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("app")


@app.before_request
def log_request() -> None:
    """Log every incoming request (method and path) to stdout."""
    log.info("%s %s", request.method, request.path)


@app.route("/health")
def health():
    """Health endpoint the watchdog polls; 200 means the service is alive."""
    return jsonify({"status": "ok"}), 200


@app.route("/")
def index() -> str:
    """Return a simple text message."""
    return "Hello from the self-healing service!"


@app.route("/crash")
def crash():
    """Kill the process immediately to simulate a hard failure."""
    log.warning("/crash called - terminating process")
    # os._exit skips cleanup and exits non-zero, like a real crash would.
    os._exit(1)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
