"""Migration utility for copying legacy Public processed data into PrivateData.

Phase 3 writes processed data directly to PrivateData; this remains for recovery
and manual verification only.
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from data_paths import DEFAULT_DATA_ROOT


REPOSITORY_ROOT = Path(__file__).resolve().parent
DEFAULT_PRIVATE_DATA_DIR = REPOSITORY_ROOT.parent / "LoL-SUP-Tracker-PrivateData"
EXCLUDED_CSV_PATHS = {Path("champion_registry.json"), Path(".DS_Store")}


class SyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class SyncItem:
    relative_path: Path
    source: Path
    destination: Path
    size: int
    action: str


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_private_repository(private_data_dir):
    private_data_dir = Path(private_data_dir).expanduser().resolve()
    if not private_data_dir.is_dir():
        raise SyncError(f"PrivateData repository does not exist: {private_data_dir}")
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=private_data_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SyncError(f"PrivateData is not a Git repository: {private_data_dir}")
    if Path(result.stdout.strip()).resolve() != private_data_dir:
        raise SyncError(f"Path is not the PrivateData repository root: {private_data_dir}")
    return private_data_dir


def source_files(data_root):
    data_root = Path(data_root).expanduser().resolve()
    files = []
    for area in ("csv", "excel"):
        source_root = data_root / area
        if not source_root.is_dir():
            raise SyncError(f"Source directory does not exist: {source_root}")
        for path in sorted(source_root.rglob("*")):
            if path.is_symlink():
                raise SyncError(f"Source symlink is not allowed: {path}")
            if not path.is_file():
                continue
            within_area = path.relative_to(source_root)
            if area == "csv" and within_area in EXCLUDED_CSV_PATHS:
                continue
            files.append((Path(area) / within_area, path))
    if not files:
        raise SyncError("No processed data files were found")
    return files


def build_plan(data_root, private_data_dir):
    private_data_dir = ensure_private_repository(private_data_dir)
    items = []
    for relative_path, source in source_files(data_root):
        destination = private_data_dir / relative_path
        if destination.is_symlink():
            raise SyncError(f"Destination symlink is not allowed: {destination}")
        if destination.exists() and not destination.is_file():
            raise SyncError(f"Destination is not a regular file: {destination}")
        if not destination.exists():
            action = "COPY"
        elif sha256(source) == sha256(destination):
            action = "SKIP"
        else:
            action = "CONFLICT"
        items.append(
            SyncItem(
                relative_path=relative_path,
                source=source,
                destination=destination,
                size=source.stat().st_size,
                action=action,
            )
        )
    return items


def copy_atomic(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    try:
        shutil.copy2(source, temporary_name)
        os.replace(temporary_name, destination)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def execute_plan(items, apply=False):
    conflicts = [item for item in items if item.action == "CONFLICT"]
    if conflicts:
        raise SyncError(
            "Conflicts detected; no files were copied: "
            + ", ".join(item.relative_path.as_posix() for item in conflicts)
        )
    if apply:
        for item in items:
            if item.action == "COPY":
                copy_atomic(item.source, item.destination)


def print_plan(items, data_root, private_data_dir, apply):
    counts = {
        action: sum(item.action == action for item in items)
        for action in ("COPY", "SKIP", "CONFLICT")
    }
    print(f"Mode: {'apply' if apply else 'preview'}")
    print(f"Source: {Path(data_root).resolve()}")
    print(f"Destination: {Path(private_data_dir).resolve()}")
    for item in items:
        print(f"{item.action} {item.relative_path.as_posix()}")
    print(f"COPY: {counts['COPY']}")
    print(f"SKIP: {counts['SKIP']}")
    print(f"CONFLICT: {counts['CONFLICT']}")
    print(f"Total bytes: {sum(item.size for item in items)}")
    return counts


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Copy processed Public data to PrivateData without overwrites"
    )
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument(
        "--private-data-dir", type=Path, default=DEFAULT_PRIVATE_DATA_DIR
    )
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        items = build_plan(args.data_root, args.private_data_dir)
        print_plan(items, args.data_root, args.private_data_dir, args.apply)
        execute_plan(items, args.apply)
    except SyncError as error:
        print(f"ERROR: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
