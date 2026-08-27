import argparse
import json
import os
import tempfile
from pathlib import Path
from raw_paths import (
    iter_combat_timeline_paths,
    match_id_from_path,
    paths_for_match,
    relative_paths_for_match,
)
from data_paths import get_data_paths

REPOSITORY_ROOT = Path(__file__).resolve().parent


def load_published_match_ids(fight_details_path=None):
    fight_details_path = fight_details_path or (
        get_data_paths().csv / "fight_details.json"
    )
    with Path(fight_details_path).open("r", encoding="utf-8") as file:
        details = json.load(file)
    if not isinstance(details, dict):
        raise ValueError("fight_details.jsonのrootがobjectではありません")
    return set(details)


def load_combat_match_ids(raw_dir=None):
    raw_dir = raw_dir or get_data_paths().raw
    return {match_id_from_path(path) for path in iter_combat_timeline_paths(raw_dir)}


def find_missing_match_ids(
    fight_details_path=None,
    raw_dir=None,
):
    paths = get_data_paths()
    fight_details_path = fight_details_path or paths.csv / "fight_details.json"
    raw_dir = raw_dir or paths.raw
    return sorted(
        load_published_match_ids(fight_details_path)
        - load_combat_match_ids(raw_dir)
    )


def select_match_ids(
    missing_ids,
    match_id=None,
    all_missing=False,
    limit=None,
    published_ids=None,
):
    selected = list(missing_ids)
    skipped = []
    if not all_missing and match_id is not None:
        if published_ids is not None and match_id not in published_ids:
            raise ValueError(f"指定Match IDは公開Fight Detailに存在しません: {match_id}")
        if match_id not in selected:
            selected = []
            skipped = [match_id]
        else:
            selected = [match_id]
    if limit is not None:
        if limit < 1:
            raise ValueError("--limitは1以上を指定してください")
        selected = selected[:limit]
    return selected, skipped


def raw_relative_paths(match_id):
    return relative_paths_for_match(match_id)


def write_text_atomic(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def write_result_files(result, result_file=None, raw_manifest=None):
    if result_file:
        write_text_atomic(
            result_file,
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        )
    if raw_manifest:
        paths = [
            path
            for match_id in result["success"]
            for path in raw_relative_paths(match_id)
        ]
        write_text_atomic(raw_manifest, "".join(f"{path}\n" for path in paths))


def scan_missing_raw(match_ids, raw_dir=None):
    raw_dir = raw_dir or get_data_paths().raw
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
    raw_dir=None,
    game_name=None,
    tag_line=None,
    puuid_getter=None,
    detail_getter=None,
    timeline_getter=None,
    detail_saver=None,
    timeline_saver=None,
    analyzer=None,
):
    raw_dir = raw_dir or get_data_paths().raw
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
                detail_saver(match_id, detail_getter(match_id), raw_root=raw_dir)
            if not paths.timeline.is_file():
                timeline_saver(match_id, timeline_getter(match_id), raw_root=raw_dir)
            paths = paths_for_match(match_id, raw_dir)
            if not paths.detail.is_file() or not paths.timeline.is_file():
                raise FileNotFoundError("取得済みrawの保存確認に失敗しました")

            analyzer(match_id, puuid=puuid, raw_root=raw_dir)
            paths = paths_for_match(match_id, raw_dir)
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
    parser.add_argument("--match-id", help="指定したMatch IDだけを対象にします")
    parser.add_argument(
        "--all-missing",
        action="store_true",
        help="現在不足している全Matchを対象にします（--match-idより優先）",
    )
    parser.add_argument("--result-file", type=Path, help="実行結果JSONの出力先")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument(
        "--fight-details",
        type=Path,
        default=None,
        help="不足判定に使う公開Fight Detail JSON",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=None,
        help="復元対象raw root",
    )
    parser.add_argument(
        "--raw-manifest",
        type=Path,
        help="成功Matchの同期対象raw相対パス一覧の出力先",
    )
    args = parser.parse_args(argv)
    paths = get_data_paths(args.data_root)
    args.fight_details = args.fight_details or paths.csv / "fight_details.json"
    args.raw_dir = args.raw_dir or paths.raw
    return args


def main(argv=None):
    args = parse_args(argv)
    os.chdir(REPOSITORY_ROOT)
    try:
        published_ids = load_published_match_ids(args.fight_details)
        missing_ids = sorted(published_ids - load_combat_match_ids(args.raw_dir))
        selected_ids, pre_skipped = select_match_ids(
            missing_ids,
            match_id=args.match_id,
            all_missing=args.all_missing,
            limit=args.limit,
            published_ids=published_ids,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"復元対象の確認に失敗しました: {safe_error_name(error)}")
        return 1

    states = scan_missing_raw(selected_ids, args.raw_dir)
    print_scan(missing_ids, selected_ids, states, args.apply)
    for match_id in pre_skipped:
        print(f"SKIP {match_id} already restored")
    if not args.apply:
        print(f"Result: success 0 / failed 0 / skip {len(pre_skipped)}")
        return 0
    if not selected_ids:
        result = {"success": [], "failed": [], "skipped": pre_skipped}
        print(
            f"Result: success 0 / failed 0 / skip {len(pre_skipped)}"
        )
        write_result_files(result, args.result_file, args.raw_manifest)
        return 0
    from config import API_KEY, GAME_NAME, TAG_LINE

    if not API_KEY or not GAME_NAME or not TAG_LINE:
        print("Riot API認証設定が不足しているため、取得を開始しません")
        return 1

    result = restore_matches(
        selected_ids,
        raw_dir=args.raw_dir,
        game_name=GAME_NAME,
        tag_line=TAG_LINE,
    )
    result["skipped"] = pre_skipped + result["skipped"]
    write_result_files(result, args.result_file, args.raw_manifest)
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
