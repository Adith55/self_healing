"""Watchdog: health-checks a service and restarts it when it is unhealthy."""
import logging
import os
import subprocess
import time

import requests

# --- Configuration (environment variables with defaults) ---
HEALTH_URL = os.getenv("HEALTH_URL", "http://localhost:5000/health")
SERVICE_NAME = os.getenv("SERVICE_NAME", "myapp")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "30"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

HEALTH_TIMEOUT = 3  # seconds to wait for the health endpoint
RESTART_WAIT = 5  # seconds to wait after a restart before re-checking

log = logging.getLogger("watchdog")


def setup_logging() -> None:
    """Log to both watchdog.log and the console, with timestamps."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler("watchdog.log"), logging.StreamHandler()],
    )


def is_healthy(url: str) -> bool:
    """Return True if the health endpoint answers HTTP 200 within the timeout."""
    try:
        return requests.get(url, timeout=HEALTH_TIMEOUT).status_code == 200
    except requests.RequestException:
        # Connection refused, timeout, DNS failure etc. all count as unhealthy.
        return False


def restart_service(name: str, dry_run: bool = False) -> None:
    """Restart the systemd service (or just log it in dry-run mode)."""
    if dry_run:
        log.info("[DRY_RUN] would run: systemctl restart %s", name)
        return
    log.info("Running: systemctl restart %s", name)
    result = subprocess.run(["systemctl", "restart", name])
    if result.returncode != 0:
        log.error("systemctl restart %s failed (exit %s)", name, result.returncode)


def send_alert(webhook_url: str, message: str) -> None:
    """POST a JSON alert to the webhook; do nothing if no webhook is set."""
    if not webhook_url:
        return
    try:
        requests.post(webhook_url, json={"text": message}, timeout=HEALTH_TIMEOUT)
    except requests.RequestException as exc:
        log.error("Could not send alert: %s", exc)


def run_check(
    url: str = HEALTH_URL,
    service: str = SERVICE_NAME,
    max_retries: int = MAX_RETRIES,
    dry_run: bool = DRY_RUN,
    webhook_url: str = WEBHOOK_URL,
) -> bool:
    """Check health once; on failure restart up to max_retries, then escalate."""
    if is_healthy(url):
        log.info("Health check OK")
        return True

    log.warning("Health check FAILED for %s", url)

    for attempt in range(1, max_retries + 1):
        restart_service(service, dry_run)
        time.sleep(RESTART_WAIT)
        if is_healthy(url):
            log.info("Recovered after %d restart(s)", attempt)
            return True

    message = f"ESCALATE: {service} still unhealthy after {max_retries} restarts"
    log.error(message)
    send_alert(webhook_url, message)
    return False


if __name__ == "__main__":
    setup_logging()
    log.info("Watchdog started: url=%s service=%s dry_run=%s",
             HEALTH_URL, SERVICE_NAME, DRY_RUN)
    while True:
        run_check()
        time.sleep(CHECK_INTERVAL)
