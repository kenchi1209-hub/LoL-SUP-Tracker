import argparse
import json
from pathlib import Path


class VerificationError(RuntimeError):
    pass


def load_match_ids(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise VerificationError(f"Expected an object in {path}")
    return set(payload)


def combat_match_ids(timeline_dir: Path) -> set[str]:
    suffix = "_combat_timeline.json"
    return {
        path.name[: -len(suffix)]
        for path in timeline_dir.glob(f"*{suffix}")
        if path.is_file()
    }


def required_paths(raw_dir: Path, match_id: str) -> tuple[Path, ...]:
    timeline_dir = raw_dir / "timeline"
    return (
        raw_dir / f"{match_id}.json",
        timeline_dir / f"{match_id}_timeline.json",
        timeline_dir / f"{match_id}_combat_timeline.json",
        timeline_dir / f"{match_id}_fight_context.txt",
        timeline_dir / f"{match_id}_fight_review_context.txt",
    )


def verify(fight_details_path: Path, raw_dir: Path) -> dict[str, int]:
    existing_ids = load_match_ids(fight_details_path)
    combat_ids = combat_match_ids(raw_dir / "timeline")
    missing_combat = sorted(existing_ids - combat_ids)
    extra_combat = sorted(combat_ids - existing_ids)
    missing_files = [
        path
        for match_id in sorted(existing_ids)
        for path in required_paths(raw_dir, match_id)
        if not path.is_file()
    ]

    print(f"Fight Detail matches: {len(existing_ids)}")
    print(f"Combat timelines: {len(combat_ids)}")
    print(f"Missing combat timelines: {len(missing_combat)}")
    print(f"Extra combat timelines: {len(extra_combat)}")
    print(f"Missing required raw files: {len(missing_files)}")

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
        default=Path("data/csv/fight_details.json"),
    )
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    return parser.parse_args(argv)


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
