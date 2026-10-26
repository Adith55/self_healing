# self-healing-service

A small SRE portfolio project showing three ideas together:

- **Auto-remediation**: a Python watchdog health-checks a Flask service and restarts it when it fails.
- **CI/CD**: GitHub Actions runs lint and tests on every push and pull request.
- **DevSecOps**: `pip-audit` scans dependencies for known vulnerabilities in CI.

## Architecture

```
            +---------------------+
            |  GitHub Actions CI  |  flake8 -> pytest -> pip-audit
            +---------------------+

  Linux VM (systemd)
  +--------------------------------------------------+
  |                                                  |
  |  watchdog.service            myapp.service       |
  |  +----------------+  GET    +----------------+   |
  |  | watchdog.py    |-------->| Flask app      |   |
  |  | every 30s      | /health | :5000          |   |
  |  |                |<--------|                |   |
  |  +-------+--------+  200?   +-------^--------+   |
  |          | unhealthy                |            |
  |          +-- systemctl restart ------+            |
  |          |                                       |
  |          +-- still failing after 3 tries ------> webhook alert
  +--------------------------------------------------+
```

Two layers of healing: systemd (`Restart=on-failure`) restarts a crashed process within seconds; the watchdog catches cases systemd cannot see, such as a process that is running but not answering `/health`.

## Run locally

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

python app/app.py               # terminal 1: service on http://localhost:5000
DRY_RUN=true python watchdog/watchdog.py   # terminal 2: logs instead of restarting
```

On Windows PowerShell set the variable first: `$env:DRY_RUN="true"`. `systemctl` only exists on Linux, so use `DRY_RUN` elsewhere.

Watchdog settings (environment variables):

| Variable | Default | Meaning |
|---|---|---|
| `HEALTH_URL` | `http://localhost:5000/health` | Endpoint to check |
| `SERVICE_NAME` | `myapp` | systemd unit to restart |
| `CHECK_INTERVAL` | `30` | Seconds between checks |
| `MAX_RETRIES` | `3` | Restart attempts before escalating |
| `DRY_RUN` | `false` | Log actions, do not run `systemctl` |
| `WEBHOOK_URL` | empty | Where to POST the JSON alert |

## Run tests

```bash
pytest
flake8 app watchdog tests --max-line-length=100
pip-audit -r requirements.txt
```

## Deploy with systemd on a Linux VM

1. Copy the project to `/opt/self-healing-service` and create the virtualenv there (`python3.12 -m venv venv && venv/bin/pip install -r requirements.txt`).
2. Create the app user: `sudo useradd --system myapp`.
3. Edit the placeholder paths and user in `deploy/*.service` if yours differ.
4. Install and start:

```bash
sudo cp deploy/myapp.service deploy/watchdog.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now myapp watchdog
sudo systemctl status myapp watchdog
```

### Test the self-healing

```bash
# Layer 1: systemd restarts a crashed process
curl localhost:5000/crash            # process dies
sleep 5; curl localhost:5000/health  # back, restarted by systemd

# Layer 2: the watchdog restarts a service that is down but not "failed"
sudo systemctl stop myapp            # a manual stop is not restarted by systemd
tail -f /opt/self-healing-service/watchdog.log
# within CHECK_INTERVAL: "Health check FAILED" -> "systemctl restart myapp"
#                        -> "Recovered after 1 restart(s)"
```

To see the escalation path, stop `myapp` and mask it (`sudo systemctl mask myapp`) so restarts fail; the log shows `ESCALATE` and the webhook is called. Run `sudo systemctl unmask myapp` afterwards.

## SLO

**99.9% of health checks succeed**, measured over 30 days. With a 30 s check interval that is about 86,400 checks per month, so roughly 86 failed checks (about 43 minutes of downtime) is the error budget.

## Runbook: service is down

1. Confirm: `curl -i http://localhost:5000/health`.
2. Check unit state: `systemctl status myapp`.
3. Read app logs: `journalctl -u myapp -n 100 --no-pager`.
4. Read watchdog logs: `tail -n 100 watchdog.log` and `systemctl status watchdog` (is the watchdog itself running?).
5. Restart manually: `sudo systemctl restart myapp`, then re-check `/health`.
6. If it keeps failing, look for the cause: recent deploy, full disk (`df -h`), memory (`free -m`), port in use (`ss -ltnp | grep 5000`). Roll back to the last good version if a deploy caused it.
7. After recovery, write down what happened and what would prevent it.

## What I would add for production

- **Metrics and dashboards**: expose Prometheus metrics (request count, latency, errors) and graph them in Grafana; track the SLO as a dashboard.
- **Alerting**: alert on SLO burn rate and on `ESCALATE` events through a real pager (PagerDuty/Opsgenie) instead of a bare webhook.
- **Multiple instances behind a load balancer**: remove the single point of failure; let the load balancer health-check and drain bad instances.
- **Secrets management**: keep webhook URLs and tokens in a secrets manager (e.g. Vault, cloud key vault) instead of environment variables in unit files.
- Also: run the app with a production WSGI server (gunicorn), and run the watchdog as a non-root user with a narrow sudoers rule.
