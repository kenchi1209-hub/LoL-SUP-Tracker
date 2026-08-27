import argparse
import json
from pathlib import Path
from raw_paths import (
    iter_combat_timeline_paths,
    match_id_from_path,
    paths_for_match,
)
from data_paths import get_data_paths


class VerificationError(RuntimeError):
    pass


def load_match_ids(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise VerificationError(f"Expected an object in {path}")
    return set(payload)


def combat_match_ids(raw_dir: Path) -> set[str]:
    return {match_id_from_path(path) for path in iter_combat_timeline_paths(raw_dir)}


def required_paths(raw_dir: Path, match_id: str) -> tuple[Path, ...]:
    return paths_for_match(match_id, raw_dir).required()


def verify(fight_details_path: Path, raw_dir: Path) -> dict[str, int]:
    existing_ids = load_match_ids(fight_details_path)
    combat_ids = combat_match_ids(raw_dir)
    missing_combat = sorted(existing_ids - combat_ids)
    extra_combat = sorted(combat_ids - existing_ids)
    missing_files = [
        path
        for match_id in sorted(existing_ids)
        for path in required_paths(raw_dir, match_id)
        if not path.is_file()
    ]
    incomplete_new_layout = {
        match_id: [path for path in paths_for_match(match_id, raw_dir).required() if not path.is_file()]
        for match_id in sorted(existing_ids)
        if paths_for_match(match_id, raw_dir).directory.exists()
        and not all(path.is_file() for path in paths_for_match(match_id, raw_dir).required())
    }

    print(f"Fight Detail matches: {len(existing_ids)}")
    print(f"Combat timelines: {len(combat_ids)}")
    print(f"Missing combat timelines: {len(missing_combat)}")
    print(f"Extra combat timelines: {len(extra_combat)}")
    print(f"Missing required raw files: {len(missing_files)}")
    print(f"Incomplete Match directories: {len(incomplete_new_layout)}")

    errors = []
    if missing_combat:
        errors.append("Missing combat: " + ", ".join(missing_combat))
    if extra_combat:
        errors.append("Extra combat: " + ", ".join(extra_combat))
    if missing_files:
        errors.append(
            "Missing raw files: "
            + ", ".join(str(path.relative_to(raw_dir)) for path in missing_files)
        )
    if incomplete_new_layout:
        errors.append(
            "Incomplete Match directories: "
            + ", ".join(
                f"{match_id} ({', '.join(path.name for path in paths)})"
                for match_id, paths in incomplete_new_layout.items()
            )
        )
    if errors:
        raise VerificationError("\n".join(errors))

    return {
        "matches": len(existing_ids),
        "combat_timelines": len(combat_ids),
        "required_files": len(existing_ids) * 5,
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Verify published Fight raw completeness")
    parser.add_argument(
        "--fight-details",
        type=Path,
        default=None,
    )
    parser.add_argument("--raw-dir", type=Path, default=None)
    parser.add_argument("--data-root", type=Path)
    args = parser.parse_args(argv)
    paths = get_data_paths(args.data_root)
    args.fight_details = args.fight_details or paths.csv / "fight_details.json"
    args.raw_dir = args.raw_dir or paths.raw
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        verify(args.fight_details, args.raw_dir)
    except (OSError, json.JSONDecodeError, VerificationError) as error:
        print(f"ERROR: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
