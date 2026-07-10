import os
import shutil

SUMMARY_TXT_PATH = "data/csv/summary.txt"
YEARLY_DIR = "data/csv/yearly"

def export_yearly_summary(year="2026"):
    if not os.path.exists(SUMMARY_TXT_PATH):
        print(f"summary.txtが見つかりません: {SUMMARY_TXT_PATH}")
        return

    os.makedirs(YEARLY_DIR, exist_ok=True)

    output_path = f"{YEARLY_DIR}/{year}_summary.txt"
    shutil.copyfile(SUMMARY_TXT_PATH, output_path)

    print(f"{year}_summary.txt 出力完了: {output_path}")