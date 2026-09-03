"""Read-only local connector for the League Client Update (LCU) API.

The LCU lockfile token is intentionally runtime-only.  Do not log, serialize,
or repr credentials from this module.
"""

import json
import os
import subprocess
import warnings
from dataclasses import dataclass
from pathlib import Path

import requests
from requests.exceptions import RequestException
from urllib3.exceptions import InsecureRequestWarning


LCU_PROCESS_NAME = "LeagueClientUx.exe"
SOLO_QUEUE_TYPE = "RANKED_SOLO_5x5"
SENSITIVE_SESSION_KEYS = {
    "puuid", "summonerId", "accountId", "account_id", "displayName",
    "gameName", "tagLine", "name", "playerName", "riotId",
}


class LCUError(RuntimeError):
    """Base error which never includes LCU credentials."""


class LCUUnavailable(LCUError):
    """The client, lockfile, or local LCU service is unavailable."""


@dataclass(frozen=True, repr=False)
class LCUCredentials:
    pid: int
    port: int
    token: str
    protocol: str
    lockfile: Path

    def __repr__(self):
        return (
            "LCUCredentials("
            f"pid={self.pid}, port={self.port}, protocol={self.protocol!r}, "
            f"lockfile={str(self.lockfile)!r})"
        )


def _windows_processes():
    """Return only process metadata needed to locate LeagueClientUx.exe."""
    if os.name != "nt":
        return []
    command = (
        "Get-CimInstance Win32_Process -Filter \"Name='LeagueClientUx.exe'\" "
        "| Select-Object ProcessId,ExecutablePath | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return []
    parsed = json.loads(completed.stdout)
    return parsed if isinstance(parsed, list) else [parsed]


def find_client(processes=None):
    """Find the active League Client UX executable without reading its command line."""
    processes = _windows_processes() if processes is None else processes
    for process in processes:
        executable = process.get("ExecutablePath") or process.get("executable_path")
        if executable:
            return Path(executable)
    return None


def find_lockfile(client_path):
    """Return the expected lockfile path only when it currently exists."""
    if not client_path:
        return None
    path = Path(client_path).parent / "lockfile"
    return path if path.is_file() else None


def read_lockfile(path):
    """Parse a lockfile without ever exposing its raw content in an exception."""
    try:
        fields = Path(path).read_text(encoding="utf-8").strip().split(":")
    except OSError as error:
        raise LCUUnavailable("LCU lockfile is unavailable") from error
    if len(fields) != 5:
        raise LCUUnavailable("LCU lockfile format is invalid")
    _, pid_text, port_text, token, protocol = fields
    try:
        pid = int(pid_text)
        port = int(port_text)
    except ValueError as error:
        raise LCUUnavailable("LCU lockfile port is invalid") from error
    if pid <= 0 or port <= 0 or not token or protocol not in {"https", "http"}:
        raise LCUUnavailable("LCU lockfile fields are invalid")
    return LCUCredentials(pid, port, token, protocol, Path(path))


def _safe_scalar(value):
    return value if isinstance(value, (str, int, float, bool)) or value is None else None


def session_diagnostic(session, phase=None):
    """Return a small PII-free schema diagnostic; never dump the session itself."""
    if not isinstance(session, dict):
        return {"phase": phase, "top_level_keys": []}
    game_data = session.get("gameData")
    game_data = game_data if isinstance(game_data, dict) else {}
    queue = game_data.get("queue")
    queue = queue if isinstance(queue, dict) else {}
    result = {
        "phase": phase,
        "top_level_keys": sorted(key for key in session if key not in SENSITIVE_SESSION_KEYS),
        "game_data_keys": sorted(key for key in game_data if key not in SENSITIVE_SESSION_KEYS),
        "queue_keys": sorted(key for key in queue if key not in SENSITIVE_SESSION_KEYS),
    }
    for output_key, source in (("queue_id", queue.get("id")), ("game_mode", game_data.get("gameMode")), ("game_type", game_data.get("gameType"))):
        value = _safe_scalar(source)
        if value is not None:
            result[output_key] = value
    return result


class LCUClient:
    """A reconnectable, GET-only LCU client bound to loopback HTTPS."""

    def __init__(self, process_provider=None, session=None):
        self.process_provider = process_provider or _windows_processes
        self.session = session or requests.Session()
        self.credentials = None

    @property
    def connected(self):
        return self.credentials is not None

    def connect(self):
        client = find_client(self.process_provider())
        lockfile = find_lockfile(client)
        if lockfile is None:
            self.disconnect()
            raise LCUUnavailable("League Client or LCU lockfile is unavailable")
        self.credentials = read_lockfile(lockfile)
        return self.credentials

    def disconnect(self):
        self.credentials = None

    def _url(self, path):
        if not self.credentials:
            raise LCUUnavailable("LCU is not connected")
        if not isinstance(path, str) or not path.startswith("/") or "://" in path:
            raise LCUError("LCU path must be a local absolute path")
        return f"{self.credentials.protocol}://127.0.0.1:{self.credentials.port}{path}"

    def get(self, path):
        """Perform an LCU GET. TLS bypass is scoped to this loopback request only."""
        url = self._url(path)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", InsecureRequestWarning)
                response = self.session.get(
                    url,
                    auth=("riot", self.credentials.token),
                    verify=False,
                    timeout=8,
                )
        except RequestException as error:
            self.disconnect()
            raise LCUUnavailable("LCU local HTTPS request failed") from error
        if response.status_code == 401:
            self.disconnect()
            raise LCUUnavailable("LCU authentication expired")
        return response

    def get_json(self, path, allow_not_found=False):
        response = self.get(path)
        if allow_not_found and response.status_code == 404:
            return None
        if response.status_code != 200:
            raise LCUError(f"LCU GET failed with HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as error:
            raise LCUError("LCU GET returned invalid JSON") from error

    def get_gameflow_phase(self):
        phase = self.get_json("/lol-gameflow/v1/gameflow-phase")
        return phase if isinstance(phase, str) else None

    def get_gameflow_session(self):
        return self.get_json("/lol-gameflow/v1/session", allow_not_found=True)

    def get_ranked_stats(self):
        return self.get_json("/lol-ranked/v1/current-ranked-stats")

    def get_current_puuid(self):
        """Return the active LCU account PUUID for in-memory equality checks only."""
        summoner = self.get_json("/lol-summoner/v1/current-summoner")
        puuid = summoner.get("puuid") if isinstance(summoner, dict) else None
        return puuid if isinstance(puuid, str) and puuid else None

    def get_solo_rank(self):
        stats = self.get_ranked_stats()
        queue_map = stats.get("queueMap") if isinstance(stats, dict) else None
        solo = queue_map.get(SOLO_QUEUE_TYPE) if isinstance(queue_map, dict) else None
        if not isinstance(solo, dict):
            return None
        required = ("tier", "division", "leaguePoints", "wins", "losses")
        if any(key not in solo for key in required):
            return None
        return {key: solo[key] for key in ("queueType", *required)}
