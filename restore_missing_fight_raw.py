import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent
FIGHT_DETAILS_PATH = REPOSITORY_ROOT / "data/csv/fight_details.json"
RAW_DIR = REPOSITORY_ROOT / "data/raw"
TIMELINE_DIR = RAW_DIR / "timeline"
COMBAT_SUFFIX = "_combat_timeline.json"


@dataclass(frozen=True)
class RawPaths:
    detail: Path
    timeline: Path
    combat: Path
    fight_context: Path
    fight_review_context: Path


def paths_for_match(match_id, raw_dir=RAW_DIR):
    raw_dir = Path(raw_dir)
    timeline_dir = raw_dir / "timeline"
    return RawPaths(
        detail=raw_dir / f"{match_id}.json",
        timeline=timeline_dir / f"{match_id}_timeline.json",
        combat=timeline_dir / f"{match_id}{COMBAT_SUFFIX}",
        fight_context=timeline_dir / f"{match_id}_fight_context.txt",
        fight_review_context=(
            timeline_dir / f"{match_id}_fight_review_context.txt"
        ),
    )


def load_published_match_ids(fight_details_path=FIGHT_DETAILS_PATH):
    with Path(fight_details_path).open("r", encoding="utf-8") as file:
        details = json.load(file)
    if not isinstance(details, dict):
        raise ValueError("fight_details.jsonのrootがobjectではありません")
    return set(details)


def load_combat_match_ids(timeline_dir=TIMELINE_DIR):
    return {
        path.name.removesuffix(COMBAT_SUFFIX)
        for path in Path(timeline_dir).glob(f"*{COMBAT_SUFFIX}")
        if path.is_file()
    }


def find_missing_match_ids(
    fight_details_path=FIGHT_DETAILS_PATH,
    timeline_dir=TIMELINE_DIR,
):
    return sorted(
        load_published_match_ids(fight_details_path)
        - load_combat_match_ids(timeline_dir)
    )


def select_match_ids(missing_ids, match_id=None, limit=None):
    selected = list(missing_ids)
    if match_id is not None:
        if match_id not in selected:
            raise ValueError(f"指定Match IDは復元対象ではありません: {match_id}")
        selected = [match_id]
    if limit is not None:
        if limit < 1:
            raise ValueError("--limitは1以上を指定してください")
        selected = selected[:limit]
    return selected


def scan_missing_raw(match_ids, raw_dir=RAW_DIR):
    states = []
    for match_id in match_ids:
        paths = paths_for_match(match_id, raw_dir)
        states.append(
            {
                "match_id": match_id,
                "paths": paths,
                "detail_missing": not paths.detail.is_file(),
                "timeline_missing": not paths.timeline.is_file(),
                "combat_missing": not paths.combat.is_file(),
            }
        )
    return states


def print_scan(missing_ids, selected_ids, states, apply):
    detail_missing = sum(item["detail_missing"] for item in states)
    timeline_missing = sum(item["timeline_missing"] for item in states)
    combat_missing = sum(item["combat_missing"] for item in states)
    api_targets = sum(
        item["detail_missing"] or item["timeline_missing"] for item in states
    )

    print(f"Mode: {'apply' if apply else 'dry-run'}")
    print(f"Missing count: {len(missing_ids)}")
    print(f"Selected count: {len(selected_ids)}")
    print(f"Match Detail missing: {detail_missing}")
    print(f"Timeline missing: {timeline_missing}")
    print(f"Combat timeline missing: {combat_missing}")
    print(f"API target count: {api_targets}")
    for item in states:
        print(
            f"MISSING {item['match_id']} "
            f"detail={'missing' if item['detail_missing'] else 'exists'} "
            f"timeline={'missing' if item['timeline_missing'] else 'exists'} "
            f"combat={'missing' if item['combat_missing'] else 'exists'}"
        )


def safe_error_name(error):
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    suffix = f" (HTTP {status_code})" if status_code is not None else ""
    return f"{type(error).__name__}{suffix}"


def restore_matches(
    match_ids,
    raw_dir=RAW_DIR,
    game_name=None,
    tag_line=None,
    puuid_getter=None,
    detail_getter=None,
    timeline_getter=None,
    detail_saver=None,
    timeline_saver=None,
    analyzer=None,
):
    if any(
        dependency is None
        for dependency in (
            puuid_getter,
            detail_getter,
            timeline_getter,
            detail_saver,
            timeline_saver,
            analyzer,
        )
    ):
        from analyze_timeline import analyze_match_timeline
        from riot_api import (
            get_match_detail,
            get_match_timeline,
            get_puuid,
            save_match_json,
            save_match_timeline_json,
        )

        puuid_getter = puuid_getter or get_puuid
        detail_getter = detail_getter or get_match_detail
        timeline_getter = timeline_getter or get_match_timeline
        detail_saver = detail_saver or save_match_json
        timeline_saver = timeline_saver or save_match_timeline_json
        analyzer = analyzer or analyze_match_timeline

    success = []
    failed = []
    skipped = []
    pending = []

    for match_id in match_ids:
        paths = paths_for_match(match_id, raw_dir)
        if paths.combat.is_file():
            skipped.append(match_id)
            print(f"SKIP {match_id}: combat timeline already exists")
        else:
            pending.append(match_id)

    if not pending:
        print(
            f"Result: success {len(success)} / failed {len(failed)} / "
            f"skip {len(skipped)}"
        )
        return {"success": success, "failed": failed, "skipped": skipped}

    try:
        puuid = puuid_getter(game_name, tag_line)
    except Exception as error:
        failed.extend(pending)
        print(f"FAILED PUUID lookup: {safe_error_name(error)}")
        print(
            f"Result: success {len(success)} / failed {len(failed)} / "
            f"skip {len(skipped)}"
        )
        return {"success": success, "failed": failed, "skipped": skipped}

    for match_id in pending:
        paths = paths_for_match(match_id, raw_dir)
        try:
            if not paths.detail.is_file():
                detail_saver(match_id, detail_getter(match_id))
            if not paths.timeline.is_file():
                timeline_saver(
                    match_id,
                    timeline_getter(match_id),
                    timeline_dir=str(paths.timeline.parent),
                )
            if not paths.detail.is_file() or not paths.timeline.is_file():
                raise FileNotFoundError("取得済みrawの保存確認に失敗しました")

            analyzer(match_id, puuid=puuid)
            expected = (
                paths.combat,
                paths.fight_context,
                paths.fight_review_context,
            )
            if not all(path.is_file() for path in expected):
                raise FileNotFoundError("Timeline解析生成物が不足しています")
            success.append(match_id)
            print(f"SUCCESS {match_id}")
        except Exception as error:
            failed.append(match_id)
            print(f"FAILED {match_id}: {safe_error_name(error)}")

    print(
        f"Result: success {len(success)} / failed {len(failed)} / "
        f"skip {len(skipped)}"
    )
    return {"success": success, "failed": failed, "skipped": skipped}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="公開Fight Detailに不足する正規rawをRiot APIから復元します"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Riot API取得とTimeline解析を実行します（省略時はdry-run）",
    )
    parser.add_argument("--limit", type=int, help="先頭から最大N試合だけを対象にします")
    parser.add_argument("--match-id", help="指定した不足Match IDだけを対象にします")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    os.chdir(REPOSITORY_ROOT)
    try:
        missing_ids = find_missing_match_ids()
        selected_ids = select_match_ids(missing_ids, args.match_id, args.limit)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"復元対象の確認に失敗しました: {safe_error_name(error)}")
        return 1

    states = scan_missing_raw(selected_ids)
    print_scan(missing_ids, selected_ids, states, args.apply)
    if not args.apply:
        return 0
    if not selected_ids:
        print("復元対象はありません")
        return 0
    from config import API_KEY, GAME_NAME, TAG_LINE

    if not API_KEY or not GAME_NAME or not TAG_LINE:
        print("Riot API認証設定が不足しているため、取得を開始しません")
        return 1

    result = restore_matches(selected_ids, game_name=GAME_NAME, tag_line=TAG_LINE)
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
