# LCU Watcher Runbook

## Persistent event log

On Windows, `lcu_watcher.py` writes the same non-PII operational events shown
in the console to `logs/lcu_watcher.log`. The directory is ignored by Git. The
file rotates at 5 MiB and retains three previous files.

The log intentionally excludes Riot IDs, PUUIDs, Summoner/account IDs, LCU
lockfile credentials, authorization headers, and API keys. Match IDs may be
recorded only by existing safe update tooling.

## Heartbeat recovery

The watcher polls the local LCU gameflow phase. If no successful phase read is
recorded for 15 seconds, it logs a heartbeat recovery, disconnects, reloads
the LCU lockfile on the next poll, and reconnects. Existing active match and
Queue IN recheck state are retained; only connection-scoped observations are
reset.

## Finish recovery

`WaitingForStats` or `EndOfGame` for Queue 420 can create a marked recovery
pending record when the start phase was missed. The normal one-candidate exact
capture rule still applies. Multiple uncaptured candidates stop at
`CHECKPOINT_REQUIRED`; no match ID is guessed. `PreEndOfGame` alone never
triggers recovery.

## Incident triage

For a missed game, inspect the log in this order:

1. `phase read failed`, `waiting for client`, `lockfile reloaded`, and
   `reconnect succeeded` identify LCU availability or reconnect issues.
2. `queue unavailable` or a non-420 `queue:` line identifies queue detection.
3. `pending started`, `finish recovery`, and `ranked finished` identify the
   watcher state transition.
4. `CHECKPOINT_REQUIRED`, `LIVE PROCESS FAILED`, and automatic publish logs
   identify capture or publish failures.
