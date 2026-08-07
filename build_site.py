"""my_matches.csv から GitHub Pages 用の静的サイト (public/) を生成する。

Riot APIには一切アクセスしない純粋なビルド処理。
data/csv/my_matches.csv を読み、Pythonで集計してから
自己完結した public/index.html を書き出す（チャンピオンアイコンのみ
Data Dragon CDN を参照）。
"""
import json
import os
import urllib.request

from site_builder.data import load_matches
from site_builder.top import build_html

OUT_DIR = "public"

DDRAGON_FALLBACK_VERSION = "15.13.1"


def get_ddragon_version():
    """Data Dragon の最新バージョンを取得（失敗時は固定値）。"""
    try:
        url = "https://ddragon.leagueoflegends.com/api/versions.json"
        with urllib.request.urlopen(url, timeout=10) as res:
            versions = json.load(res)
            if versions:
                return versions[0]
    except Exception as e:  # noqa: BLE001
        print(f"ddragonバージョン取得に失敗、固定値を使用します: {e}")
    return DDRAGON_FALLBACK_VERSION


def main():
    rows = load_matches()
    if not rows:
        print("警告: 試合データが空です。プレースホルダを生成します。")
    version = get_ddragon_version()
    print(f"Data Dragon version: {version}")
    os.makedirs(OUT_DIR, exist_ok=True)
    html_out = build_html(rows, version)
    out_path = os.path.join(OUT_DIR, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_out)
    # .nojekyll: GitHub Pages の Jekyll 処理を無効化（保険）
    open(os.path.join(OUT_DIR, ".nojekyll"), "w").close()
    print(f"生成完了: {out_path} ({len(rows)}戦)")


if __name__ == "__main__":
    main()
