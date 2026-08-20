from dataclasses import dataclass
from pathlib import Path


DEFAULT_RAW_ROOT = Path("data/raw")


@dataclass(frozen=True)
class MatchRawPaths:
    directory: Path
    detail: Path
    timeline: Path
    combat: Path
    fight_context: Path
    fight_review_context: Path

    def required(self) -> tuple[Path, ...]:
        return (
            self.detail,
            self.timeline,
            self.combat,
            self.fight_context,
            self.fight_review_context,
        )


def paths_for_match(match_id: str, raw_root=DEFAULT_RAW_ROOT) -> MatchRawPaths:
    directory = Path(raw_root) / match_id
    return MatchRawPaths(
        directory=directory,
        detail=directory / "match.json",
        timeline=directory / "timeline.json",
        combat=directory / "combat_timeline.json",
        fight_context=directory / "fight_context.txt",
        fight_review_context=directory / "fight_review_context.txt",
    )


def iter_match_detail_paths(raw_root=DEFAULT_RAW_ROOT):
    raw_root = Path(raw_root)
    yield from raw_root.glob("*/match.json")


def iter_combat_timeline_paths(raw_root=DEFAULT_RAW_ROOT):
    raw_root = Path(raw_root)
    yield from raw_root.glob("*/combat_timeline.json")


def match_id_from_path(path: Path) -> str:
    path = Path(path)
    if path.name in {
        "match.json",
        "timeline.json",
        "combat_timeline.json",
        "fight_context.txt",
        "fight_review_context.txt",
    }:
        return path.parent.name
    raise ValueError(f"Match IDを判定できないraw pathです: {path}")


def relative_paths_for_match(match_id: str) -> list[str]:
    paths = paths_for_match(match_id, Path("."))
    return [path.as_posix() for path in paths.required()]
