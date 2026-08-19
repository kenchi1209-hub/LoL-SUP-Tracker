import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


PRIVATE_REPO_NAME = "LoL-SUP-Tracker-PrivateData"
PRIVATE_DIR_ENV = "LOL_PRIVATE_DATA_DIR"
PLACEHOLDER_NAMES = {".gitkeep"}


class SyncError(Exception):
    pass


@dataclass(frozen=True)
class SyncItem:
    action: str
    relative_path: Path
    source: Path
    destination: Path
    size: int


def run_git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def canonical(path):
    return Path(path).expanduser().resolve(strict=False)


def same_path(left, right):
    return os.path.normcase(str(canonical(left))) == os.path.normcase(
        str(canonical(right))
    )


def is_parent(parent, child):
    parent_text = os.path.normcase(str(canonical(parent)))
    child_text = os.path.normcase(str(canonical(child)))
    try:
        return os.path.commonpath([parent_text, child_text]) == parent_text
    except ValueError:
        return False


def ensure_separate_repositories(tracker_dir, private_dir):
    if same_path(tracker_dir, private_dir):
        raise SyncError("Tracker and PrivateData directories must be different")
    if is_parent(tracker_dir, private_dir) or is_parent(private_dir, tracker_dir):
        raise SyncError("Tracker and PrivateData directories must not be nested")


def ensure_git_repository(path, label):
    if not path.exists() or not path.is_dir():
        raise SyncError(f"{label} repository does not exist: {path}")
    result = run_git(path, "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        raise SyncError(f"{label} is not a Git repository: {path}")
    git_root = canonical(result.stdout.strip())
    if not same_path(git_root, path):
        raise SyncError(f"{label} must be the Git repository root: {path}")


def ensure_public_raw_is_safe(tracker_dir):
    tracked = run_git(tracker_dir, "ls-files", "--", "data/raw")
    if tracked.returncode != 0:
        raise SyncError("Unable to inspect tracked files under data/raw")
    if tracked.stdout.strip():
        raise SyncError("Tracked files exist under Public data/raw")

    ignored = run_git(
        tracker_dir,
        "check-ignore",
        "--quiet",
        "--",
        "data/raw/.sync-private-data-safety-check",
    )
    if ignored.returncode != 0:
        raise SyncError("Public data/raw is not covered by .gitignore")


def ensure_path_is_not_symlink(path, label):
    if path.is_symlink():
        raise SyncError(f"Symlink is not allowed for {label}: {path}")


def ensure_tree_has_no_symlinks(path, label):
    if not path.exists():
        return
    ensure_path_is_not_symlink(path, label)
    for current, directories, files in os.walk(path, followlinks=False):
        current_path = Path(current)
        for name in directories + files:
            candidate = current_path / name
            if candidate.is_symlink():
                raise SyncError(f"Symlink is not allowed in {label}: {candidate}")


def ensure_existing_components_are_not_symlinks(root, path, label):
    ensure_path_is_not_symlink(root, label)
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        if current.exists() or current.is_symlink():
            ensure_path_is_not_symlink(current, label)


def source_files(source_root):
    files = []
    for current, directories, names in os.walk(source_root, followlinks=False):
        current_path = Path(current)
        directories.sort()
        for name in sorted(names):
            path = current_path / name
            if path.is_symlink():
                raise SyncError(f"Symlink is not allowed in source: {path}")
            if name in PLACEHOLDER_NAMES:
                continue
            if not path.is_file():
                raise SyncError(f"Source contains a non-regular file: {path}")
            files.append(path)
    if not files:
        raise SyncError(f"Source raw directory is empty: {source_root}")
    return files


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_plan(source_root, destination_root):
    plan = []
    for source in source_files(source_root):
        relative_path = source.relative_to(source_root)
        destination = destination_root / relative_path
        if destination.is_symlink():
            raise SyncError(f"Symlink is not allowed in destination: {destination}")
        size = source.stat().st_size
        if not destination.exists():
            action = "COPY"
        elif not destination.is_file():
            action = "CONFLICT"
        elif sha256(source) == sha256(destination):
            action = "SKIP"
        else:
            action = "CONFLICT"
        plan.append(SyncItem(action, relative_path, source, destination, size))
    return plan


def atomic_copy(source, destination, destination_root):
    destination.parent.mkdir(parents=True, exist_ok=True)
    ensure_existing_components_are_not_symlinks(
        destination_root,
        destination.parent,
        "destination",
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        if destination.exists() or destination.is_symlink():
            raise SyncError(f"Destination changed after scan: {destination}")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def print_plan(mode, apply, source_root, destination_root, plan, output=print):
    output(f"Mode: {mode}")
    output(f"Dry run: {'no' if apply else 'yes'}")
    output(f"Source: {source_root}")
    output(f"Destination: {destination_root}")
    for item in plan:
        output(f"{item.action} {item.relative_path.as_posix()}")
    output(f"COPY count: {sum(item.action == 'COPY' for item in plan)}")
    output(f"SKIP count: {sum(item.action == 'SKIP' for item in plan)}")
    output(f"CONFLICT count: {sum(item.action == 'CONFLICT' for item in plan)}")
    output(f"Total bytes: {sum(item.size for item in plan if item.action == 'COPY')}")


def synchronize(mode, tracker_dir, private_dir, apply=False, output=print):
    if mode not in {"pull", "push"}:
        raise SyncError(f"Unsupported mode: {mode}")
    tracker_input = Path(os.path.abspath(os.path.expanduser(str(tracker_dir))))
    private_input = Path(os.path.abspath(os.path.expanduser(str(private_dir))))
    ensure_path_is_not_symlink(tracker_input, "Tracker repository")
    ensure_path_is_not_symlink(private_input, "PrivateData repository")
    tracker_dir = canonical(tracker_dir)
    private_dir = canonical(private_dir)
    ensure_separate_repositories(tracker_dir, private_dir)
    ensure_git_repository(tracker_dir, "Tracker")
    ensure_git_repository(private_dir, "PrivateData")
    ensure_public_raw_is_safe(tracker_dir)

    public_raw = tracker_dir / "data" / "raw"
    private_raw = private_dir / "raw"
    source_root, destination_root = (
        (private_raw, public_raw) if mode == "pull" else (public_raw, private_raw)
    )
    if not source_root.exists() or not source_root.is_dir():
        raise SyncError(f"Source raw directory does not exist: {source_root}")

    ensure_tree_has_no_symlinks(source_root, "source")
    ensure_tree_has_no_symlinks(destination_root, "destination")
    ensure_existing_components_are_not_symlinks(
        tracker_dir,
        public_raw,
        "Public data/raw",
    )
    ensure_existing_components_are_not_symlinks(
        private_dir,
        private_raw,
        "PrivateData raw",
    )

    plan = build_plan(source_root, destination_root)
    print_plan(mode, apply, source_root, destination_root, plan, output)
    if any(item.action == "CONFLICT" for item in plan):
        raise SyncError("Conflicts found; no files were copied")
    if apply:
        for item in plan:
            if item.action == "COPY":
                atomic_copy(item.source, item.destination, destination_root)
    return plan


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Synchronize raw data without deleting or overwriting files"
    )
    parser.add_argument("mode", choices=("pull", "push"))
    parser.add_argument("--private-data-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def private_data_dir(args, tracker_dir):
    if args.private_data_dir is not None:
        return args.private_data_dir
    environment_path = os.getenv(PRIVATE_DIR_ENV)
    if environment_path:
        return Path(environment_path)
    return tracker_dir.parent / PRIVATE_REPO_NAME


def main(argv=None):
    args = parse_args(argv)
    tracker_dir = Path(__file__).resolve().parent
    selected_private_dir = private_data_dir(args, tracker_dir)
    try:
        synchronize(
            args.mode,
            tracker_dir,
            selected_private_dir,
            apply=args.apply,
        )
    except SyncError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
