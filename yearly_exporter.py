import os
import shutil
from data_paths import CSV_ROOT

SUMMARY_TXT_PATH = CSV_ROOT / "summary.txt"
YEARLY_DIR = CSV_ROOT / "yearly"

def export_yearly_summary(year="2026", csv_root=CSV_ROOT):
    summary_path = csv_root / "summary.txt"
    yearly_dir = csv_root / "yearly"
    if not os.path.exists(summary_path):
        print(f"summary.txtが見つかりません: {summary_path}")
        return

    os.makedirs(yearly_dir, exist_ok=True)

    output_path = yearly_dir / f"{year}_summary.txt"
    shutil.copyfile(summary_path, output_path)

    print(f"{year}_summary.txt 出力完了: {output_path}")
