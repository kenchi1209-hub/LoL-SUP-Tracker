"""Validated ISO-week storage for all-fight details (PrivateData only)."""

import hashlib
import argparse
import json
import os
import re
import tempfile
from collections import OrderedDict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from timezone_utils import JST


WEEK_RE = re.compile(r"^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])\.json$")
MANIFEST_NAME = "manifest.json"


class ShardError(ValueError):
    """The weekly data is incomplete, inconsistent or unsafe."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ShardError("duplicate JSON key: " + key)
        result[key] = value
    return result


def _parse(data):
    try:
        return json.loads(data, object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError) as error:
        raise ShardError("invalid shard JSON") from error


def week_for_match(raw_root, match_id):
    if not isinstance(match_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", match_id):
        raise ShardError("invalid match ID")
    path = Path(raw_root) / match_id / "match.json"
    try:
        match = _parse(path.read_bytes())
        if match.get("metadata", {}).get("matchId") != match_id:
            raise ShardError("match metadata ID mismatch: " + match_id)
        timestamp = match["info"]["gameStartTimestamp"]
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or timestamp <= 0:
            raise ShardError("invalid gameStartTimestamp: " + match_id)
        start = datetime.fromtimestamp(timestamp / 1000, timezone.utc).astimezone(JST)
    except (OSError, KeyError, TypeError, OverflowError) as error:
        raise ShardError("missing match start metadata: " + match_id) from error
    year, week, _ = start.isocalendar()
    return f"{year}-W{week:02d}.json"


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def prepare_shards(details, raw_root):
    if not isinstance(details, dict):
        raise ShardError("fight details root must be an object")
    groups = {}
    mapping = {}
    for match_id in sorted(details):
        fights = details[match_id]
        if not isinstance(fights, list):
            raise ShardError("fight details must be an array: " + match_id)
        week = week_for_match(raw_root, match_id)
        groups.setdefault(week, {})[match_id] = fights
        mapping[match_id] = week
    files = {week: _json_bytes(group) for week, group in sorted(groups.items())}
    manifest = {
        "schema_version": 1,
        "matches": mapping,
        "weeks": {week: hashlib.sha256(content).hexdigest() for week, content in files.items()},
    }
    files[MANIFEST_NAME] = _json_bytes(manifest)
    return files


def validate_shards(directory, raw_root=None):
    directory = Path(directory)
    try:
        manifest = _parse((directory / MANIFEST_NAME).read_bytes())
    except OSError as error:
        raise ShardError("weekly manifest missing") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ShardError("invalid weekly manifest")
    matches, weeks = manifest.get("matches"), manifest.get("weeks")
    if not isinstance(matches, dict) or not isinstance(weeks, dict):
        raise ShardError("invalid weekly manifest index")
    if any(not WEEK_RE.fullmatch(name) for name in weeks):
        raise ShardError("invalid weekly filename")
    actual = {path.name for path in directory.iterdir() if path.is_file() and path.suffix == ".json"}
    if actual != set(weeks) | {MANIFEST_NAME}:
        raise ShardError("missing or stale weekly files")
    seen = {}
    for week, digest in weeks.items():
        try:
            content = (directory / week).read_bytes()
        except OSError as error:
            raise ShardError("missing weekly file: " + week) from error
        if hashlib.sha256(content).hexdigest() != digest:
            raise ShardError("weekly checksum mismatch: " + week)
        shard = _parse(content)
        if not isinstance(shard, dict):
            raise ShardError("weekly root must be an object")
        for match_id, fights in shard.items():
            if match_id in seen or not isinstance(fights, list):
                raise ShardError("duplicate match or invalid fights: " + match_id)
            seen[match_id] = week
    if seen != matches:
        raise ShardError("weekly manifest and match IDs disagree")
    if raw_root is not None:
        for match_id, week in seen.items():
            if week_for_match(raw_root, match_id) != week:
                raise ShardError("weekly assignment does not match gameStartTimestamp")
    return manifest


def validate_data_root(root, deleted=()):
    root = Path(root)
    manifest = validate_shards(root / "csv" / "all_fight_details", root / "raw")
    try:
        self_fights = _parse((root / "csv" / "fight_details.json").read_bytes())
    except OSError as error:
        raise ShardError("self-fight data is missing") from error
    if not isinstance(self_fights, dict) or set(self_fights) != set(manifest["matches"]):
        raise ShardError("weekly fights do not match self-fight match IDs")
    for path in deleted:
        prefix = "csv/all_fight_details/"
        if not path.startswith(prefix) or not WEEK_RE.fullmatch(path[len(prefix):]):
            raise ShardError("unexpected deleted path")
        if path[len(prefix):] in manifest["weeks"]:
            raise ShardError("deleted week is still referenced")
    return manifest


def _atomic_write(path, content):
    descriptor, name = tempfile.mkstemp(prefix=".fight-shard-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_shards(details, raw_root, directory):
    """Prepare all data first, then atomically replace changed files; roll back on error."""
    files = prepare_shards(details, raw_root)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    old = {}
    for path in directory.iterdir():
        if path.is_file() and (WEEK_RE.fullmatch(path.name) or path.name == MANIFEST_NAME):
            old[path.name] = path.read_bytes()
        elif path.is_file() and path.suffix == ".json":
            raise ShardError("unexpected JSON file in shard directory")
    if old:
        existing = validate_shards(directory)
        incoming = _parse(files[MANIFEST_NAME])
        if set(existing["matches"]) - set(incoming["matches"]):
            raise ShardError("weekly export would remove existing matches")
    changed = [name for name in files if old.get(name) != files[name]]
    stale = sorted(set(old) - set(files))
    if not changed and not stale:
        return directory
    try:
        for name in [n for n in changed if n != MANIFEST_NAME]:
            _atomic_write(directory / name, files[name])
        for name in stale:
            (directory / name).unlink()
        if MANIFEST_NAME in changed:
            _atomic_write(directory / MANIFEST_NAME, files[MANIFEST_NAME])
        validate_shards(directory, raw_root)
    except Exception:
        for name in set(files) | set(old):
            path = directory / name
            if name in old:
                if not path.exists() or path.read_bytes() != old[name]:
                    _atomic_write(path, old[name])
            elif path.exists():
                path.unlink()
        raise
    return directory


class ShardReader:
    """Validate the complete set once; retain only a few weekly files in memory."""

    def __init__(self, directory, raw_root=None):
        self.directory = Path(directory)
        self.manifest = validate_shards(self.directory, raw_root)

    @lru_cache(maxsize=2)
    def _week(self, name):
        content = (self.directory / name).read_bytes()
        if hashlib.sha256(content).hexdigest() != self.manifest["weeks"][name]:
            raise ShardError("weekly file changed after validation")
        return _parse(content)

    def get(self, match_id):
        week = self.manifest["matches"].get(match_id)
        return self._week(week)[match_id] if week else []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-root", required=True)
    parser.add_argument("--deleted", nargs="*", default=[])
    args = parser.parse_args()
    try:
        manifest = validate_data_root(args.validate_root, args.deleted)
    except (OSError, ShardError) as error:
        parser.exit(1, f"Weekly Fight validation failed: {error}\n")
    print(f"Weekly Fight validation: {len(manifest['matches'])} matches / {len(manifest['weeks'])} weeks")


if __name__ == "__main__":
    main()
