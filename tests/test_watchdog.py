import logging
from unittest.mock import MagicMock, patch

import requests

from watchdog.watchdog import run_check

URL = "http://localhost:5000/health"


def ok_response() -> MagicMock:
    """Build a fake HTTP 200 response."""
    return MagicMock(status_code=200)


@patch("watchdog.watchdog.time.sleep")
@patch("watchdog.watchdog.subprocess.run")
@patch("watchdog.watchdog.requests.get")
def test_healthy_check_does_nothing(mock_get, mock_run, _sleep) -> None:
    """A healthy service is not restarted."""
    mock_get.return_value = ok_response()

    assert run_check(URL, "myapp", 3, False, "") is True
    mock_run.assert_not_called()


@patch("watchdog.watchdog.time.sleep")
@patch("watchdog.watchdog.subprocess.run")
@patch("watchdog.watchdog.requests.get")
def test_failed_check_triggers_restart(mock_get, mock_run, _sleep) -> None:
    """An unhealthy service is restarted, then recovers."""
    mock_run.return_value = MagicMock(returncode=0)
    # First check fails, the re-check after the restart succeeds.
    mock_get.side_effect = [requests.ConnectionError(), ok_response()]

    assert run_check(URL, "myapp", 3, False, "") is True
    mock_run.assert_called_once_with(["systemctl", "restart", "myapp"])


@patch("watchdog.watchdog.time.sleep")
@patch("watchdog.watchdog.requests.post")
@patch("watchdog.watchdog.subprocess.run")
@patch("watchdog.watchdog.requests.get")
def test_exhausted_retries_escalates(
    mock_get, mock_run, mock_post, _sleep, caplog
) -> None:
    """After MAX_RETRIES failed restarts, log ESCALATE and send the alert."""
    mock_run.return_value = MagicMock(returncode=0)
    mock_get.side_effect = requests.ConnectionError()

    with caplog.at_level(logging.ERROR):
        result = run_check(URL, "myapp", 3, False, "http://hook.example")

    assert result is False
    assert mock_run.call_count == 3
    assert "ESCALATE" in caplog.text
    mock_post.assert_called_once()
