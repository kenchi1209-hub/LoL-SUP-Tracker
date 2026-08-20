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
    death_analysis: Path

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
        death_analysis=directory / "death_analysis.json",
    )


def legacy_paths_for_match(match_id: str, raw_root=DEFAULT_RAW_ROOT) -> MatchRawPaths:
    raw_root = Path(raw_root)
    timeline_root = raw_root / "timeline"
    return MatchRawPaths(
        directory=raw_root,
        detail=raw_root / f"{match_id}.json",
        timeline=timeline_root / f"{match_id}_timeline.json",
        combat=timeline_root / f"{match_id}_combat_timeline.json",
        fight_context=timeline_root / f"{match_id}_fight_context.txt",
        fight_review_context=timeline_root / f"{match_id}_fight_review_context.txt",
        death_analysis=timeline_root / f"{match_id}_death_analysis.json",
    )


def readable_paths_for_match(match_id: str, raw_root=DEFAULT_RAW_ROOT) -> MatchRawPaths:
    current = paths_for_match(match_id, raw_root)
    legacy = legacy_paths_for_match(match_id, raw_root)

    def prefer(current_path: Path, legacy_path: Path) -> Path:
        return current_path if current_path.is_file() else legacy_path

    return MatchRawPaths(
        directory=current.directory,
        detail=prefer(current.detail, legacy.detail),
        timeline=prefer(current.timeline, legacy.timeline),
        combat=prefer(current.combat, legacy.combat),
        fight_context=prefer(current.fight_context, legacy.fight_context),
        fight_review_context=prefer(
            current.fight_review_context, legacy.fight_review_context
        ),
        death_analysis=prefer(current.death_analysis, legacy.death_analysis),
    )


def iter_match_detail_paths(raw_root=DEFAULT_RAW_ROOT):
    raw_root = Path(raw_root)
    current = {path.parent.name: path for path in raw_root.glob("*/match.json")}
    legacy = {
        path.stem: path
        for path in raw_root.glob("*.json")
        if path.stem.startswith("JP")
    }
    yield from (current | {key: value for key, value in legacy.items() if key not in current}).values()


def iter_combat_timeline_paths(raw_root=DEFAULT_RAW_ROOT):
    raw_root = Path(raw_root)
    current = {
        path.parent.name: path for path in raw_root.glob("*/combat_timeline.json")
    }
    suffix = "_combat_timeline.json"
    legacy = {
        path.name[: -len(suffix)]: path
        for path in (raw_root / "timeline").glob(f"*{suffix}")
    }
    yield from (current | {key: value for key, value in legacy.items() if key not in current}).values()


def match_id_from_path(path: Path) -> str:
    path = Path(path)
    if path.name in {
        "match.json",
        "timeline.json",
        "combat_timeline.json",
        "fight_context.txt",
        "fight_review_context.txt",
        "death_analysis.json",
    }:
        return path.parent.name
    for suffix in (
        "_fight_review_context.txt",
        "_combat_timeline.json",
        "_fight_context.txt",
        "_death_analysis.json",
        "_timeline.json",
        ".json",
    ):
        if path.name.endswith(suffix):
            return path.name[: -len(suffix)]
    raise ValueError(f"Match IDを判定できないraw pathです: {path}")


def relative_paths_for_match(match_id: str) -> list[str]:
    paths = paths_for_match(match_id, Path("."))
    return [path.as_posix() for path in paths.required()]
