import argparse
import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from raw_paths import legacy_paths_for_match, paths_for_match


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class MigrationItem:
    action: str
    source: Path
    destination: Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reject_symlinks(root: Path):
    if root.is_symlink():
        raise MigrationError(f"Symlinkは使用できません: {root}")
    if root.exists():
        for path in root.rglob("*"):
            if path.is_symlink():
                raise MigrationError(f"Symlinkは使用できません: {path}")


def legacy_match_ids(raw_root: Path) -> set[str]:
    ids = {path.stem for path in raw_root.glob("JP*.json") if path.is_file()}
    timeline_root = raw_root / "timeline"
    suffixes = (
        "_fight_review_context.txt",
        "_combat_timeline.json",
        "_fight_context.txt",
        "_death_analysis.json",
        "_timeline.json",
    )
    for path in timeline_root.glob("JP*"):
        if not path.is_file():
            continue
        for suffix in suffixes:
            if path.name.endswith(suffix):
                ids.add(path.name[: -len(suffix)])
                break
    return ids


def build_plan(raw_root: Path):
    raw_root = Path(raw_root)
    reject_symlinks(raw_root)
    missing = {}
    plan = []
    for match_id in sorted(legacy_match_ids(raw_root)):
        source = legacy_paths_for_match(match_id, raw_root)
        destination = paths_for_match(match_id, raw_root)
        absent = [path for path in source.required() if not path.is_file()]
        if absent:
            missing[match_id] = absent
            continue
        for source_path, destination_path in zip(
            source.required(), destination.required()
        ):
            if destination_path.is_symlink():
                raise MigrationError(f"Symlinkは使用できません: {destination_path}")
            if not destination_path.exists():
                action = "COPY"
            elif not destination_path.is_file():
                action = "CONFLICT"
            elif sha256(source_path) == sha256(destination_path):
                action = "SKIP"
            else:
                action = "CONFLICT"
            plan.append(MigrationItem(action, source_path, destination_path))
    return plan, missing


def atomic_copy(source: Path, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        if sha256(source) != sha256(temporary):
            raise MigrationError(f"Copy verification failed: {source}")
        if destination.exists() or destination.is_symlink():
            raise MigrationError(f"Destination changed after scan: {destination}")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def migrate(raw_root: Path, apply=False) -> int:
    plan, missing = build_plan(raw_root)
    conflicts = [item for item in plan if item.action == "CONFLICT"]
    for item in plan:
        print(f"{item.action} {item.source} -> {item.destination}")
    for match_id, paths in missing.items():
        print(f"MISSING {match_id}: {', '.join(str(path) for path in paths)}")
    print(
        f"Matches: {len(legacy_match_ids(Path(raw_root)))} / "
        f"COPY {sum(item.action == 'COPY' for item in plan)} / "
        f"SKIP {sum(item.action == 'SKIP' for item in plan)} / "
        f"CONFLICT {len(conflicts)} / INCOMPLETE {len(missing)}"
    )
    if conflicts or missing:
        return 1
    if apply:
        for item in plan:
            if item.action == "COPY":
                atomic_copy(item.source, item.destination)
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="旧raw layoutを新layoutへcopyします")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        return migrate(args.raw_dir, args.apply)
    except (OSError, MigrationError) as error:
        print(f"ERROR: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
