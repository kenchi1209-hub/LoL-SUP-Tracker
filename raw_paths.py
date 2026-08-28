from dataclasses import dataclass
from pathlib import Path
from data_paths import RAW_ROOT


DEFAULT_RAW_ROOT = RAW_ROOT


@dataclass(frozen=True)
class MatchRawPaths:
    directory: Path
    detail: Path
    timeline: Path
    combat: Path
    fight_context: Path
    fight_review_context: Path
    rank_snapshot: Path
    rank_after: Path

    def required(self) -> tuple[Path, ...]:
        return (
            self.detail,
            self.timeline,
            self.combat,
            self.fight_context,
            self.fight_review_context,
        )


def paths_for_match(match_id: str, raw_root=None) -> MatchRawPaths:
    directory = Path(raw_root or DEFAULT_RAW_ROOT) / match_id
    return MatchRawPaths(
        directory=directory,
        detail=directory / "match.json",
        timeline=directory / "timeline.json",
        combat=directory / "combat_timeline.json",
        fight_context=directory / "fight_context.txt",
        fight_review_context=directory / "fight_review_context.txt",
        rank_snapshot=directory / "rank_snapshot.json",
        rank_after=directory / "rank_after.json",
    )


def iter_match_detail_paths(raw_root=None):
    raw_root = Path(raw_root or DEFAULT_RAW_ROOT)
    yield from raw_root.glob("*/match.json")


def iter_combat_timeline_paths(raw_root=None):
    raw_root = Path(raw_root or DEFAULT_RAW_ROOT)
    yield from raw_root.glob("*/combat_timeline.json")


def match_id_from_path(path: Path) -> str:
    path = Path(path)
    if path.name in {
        "match.json",
        "timeline.json",
        "combat_timeline.json",
        "fight_context.txt",
        "fight_review_context.txt",
        "rank_snapshot.json",
        "rank_after.json",
    }:
        return path.parent.name
    raise ValueError(f"Match IDを判定できないraw pathです: {path}")


def relative_paths_for_match(match_id: str) -> list[str]:
    paths = paths_for_match(match_id, Path("."))
    return [path.as_posix() for path in paths.required()]
