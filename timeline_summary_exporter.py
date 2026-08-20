import csv
import json
import os
from raw_paths import DEFAULT_RAW_ROOT, iter_combat_timeline_paths


OUTPUT_PATH = os.path.join(
    "data",
    "csv",
    "timeline_summary.csv",
)


FIELDNAMES = [
    "match_id",
    "champion",
    "kills",
    "deaths",
    "assists",
    "combat_events",
    "all_fights",
    "my_fights",
    "fight_wins",
    "fight_evens",
    "fight_losses",
    "survived_fights",
    "died_fights",
    "small_fights",
    "skirmishes",
    "teamfights",
    "early_fights",
    "mid_fights",
    "late_fights",
    "objective_before_gain",
    "objective_before_loss",
    "objective_during_gain",
    "objective_during_loss",
    "objective_after_gain",
    "objective_after_loss",
]


def load_json(path):
    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def count_value(
    fights,
    key,
    value,
):
    return sum(
        1
        for fight in fights
        if fight.get(key) == value
    )


def count_objective_context(
    fights,
    timing,
    value,
):
    return sum(
        1
        for fight in fights
        if fight.get(
            "objective_context",
            {},
        ).get(timing) == value
    )


def build_summary_row(data):
    summary = data.get(
        "summary",
        {},
    )

    participant = data.get(
        "participant",
        {},
    )

    fights = data.get(
        "review_fights",
        [],
    )

    return {
        "match_id": data.get(
            "match_id"
        ),
        "champion": participant.get(
            "champion"
        ),
        "kills": summary.get(
            "kills",
            0,
        ),
        "deaths": summary.get(
            "deaths",
            0,
        ),
        "assists": summary.get(
            "assists",
            0,
        ),
        "combat_events": summary.get(
            "combat_events",
            0,
        ),
        "all_fights": summary.get(
            "all_fights",
            0,
        ),
        "my_fights": summary.get(
            "my_fights",
            0,
        ),
        "fight_wins": count_value(
            fights,
            "result",
            "WIN",
        ),
        "fight_evens": count_value(
            fights,
            "result",
            "EVEN",
        ),
        "fight_losses": count_value(
            fights,
            "result",
            "LOSS",
        ),
        "survived_fights": count_value(
            fights,
            "survival",
            "SURVIVED",
        ),
        "died_fights": count_value(
            fights,
            "survival",
            "DIED",
        ),
        "small_fights": count_value(
            fights,
            "scale",
            "SMALL",
        ),
        "skirmishes": count_value(
            fights,
            "scale",
            "SKIRMISH",
        ),
        "teamfights": count_value(
            fights,
            "scale",
            "TEAMFIGHT",
        ),
        "early_fights": count_value(
            fights,
            "phase",
            "EARLY",
        ),
        "mid_fights": count_value(
            fights,
            "phase",
            "MID",
        ),
        "late_fights": count_value(
            fights,
            "phase",
            "LATE",
        ),
        "objective_before_gain": (
            count_objective_context(
                fights,
                "before",
                "GAIN",
            )
        ),
        "objective_before_loss": (
            count_objective_context(
                fights,
                "before",
                "LOSS",
            )
        ),
        "objective_during_gain": (
            count_objective_context(
                fights,
                "during",
                "GAIN",
            )
        ),
        "objective_during_loss": (
            count_objective_context(
                fights,
                "during",
                "LOSS",
            )
        ),
        "objective_after_gain": (
            count_objective_context(
                fights,
                "after",
                "GAIN",
            )
        ),
        "objective_after_loss": (
            count_objective_context(
                fights,
                "after",
                "LOSS",
            )
        ),
    }


def export_timeline_summary(raw_root=DEFAULT_RAW_ROOT, output_path=OUTPUT_PATH):
    os.makedirs(
        "data/csv",
        exist_ok=True,
    )

    paths = sorted(iter_combat_timeline_paths(raw_root))

    rows = []

    failed = 0

    for path in paths:
        try:
            data = load_json(path)

            rows.append(
                build_summary_row(data)
            )

        except Exception as error:
            failed += 1

            print(
                f"Timeline Summary読込失敗: "
                f"{path} | {error}"
            )

    with open(
        output_path,
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=FIELDNAMES,
        )

        writer.writeheader()
        writer.writerows(rows)

    print(
        "timeline_summary.csv 出力完了: "
        f"{len(rows)}件 "
        f"/ 失敗 {failed}件 "
        f"/ {output_path}"
    )

    return output_path


if __name__ == "__main__":
    export_timeline_summary()
