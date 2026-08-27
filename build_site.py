"""my_matches.csv から GitHub Pages 用の静的サイト (public/) を生成する。

Riot APIには一切アクセスしない純粋なビルド処理。
data/csv/my_matches.csv を読み、Pythonで集計してから
自己完結した public/index.html を書き出す（チャンピオンアイコンのみ
Data Dragon CDN を参照）。
"""
import argparse
import os
import shutil

from champion_registry import registry_version
from site_builder.data import configure_data_root as configure_site_data, load_matches
from site_builder.render import configure_data_root as configure_render_data
from site_builder.history import build_history_html
from site_builder.role import build_role_pages
from site_builder.top import build_html

OUT_DIR = "public"

def get_ddragon_version():
    """Git管理済みChampion RegistryのData Dragon versionを返す。"""
    return registry_version()


def main(data_root=None):
    configure_site_data(data_root)
    configure_render_data(data_root)
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
    with open(os.path.join(OUT_DIR, "history.html"), "w", encoding="utf-8") as f:
        f.write(build_history_html(rows, version))
    for filename, role_html in build_role_pages(rows, version).items():
        with open(os.path.join(OUT_DIR, filename), "w", encoding="utf-8") as f:
            f.write(role_html)
    asset_dir = os.path.join(OUT_DIR, "assets")
    os.makedirs(asset_dir, exist_ok=True)
    source_asset_dir = os.path.join(os.path.dirname(__file__), "site_builder", "assets")
    for filename in sorted(os.listdir(source_asset_dir)):
        if filename.endswith((".js", ".css")):
            shutil.copyfile(
                os.path.join(source_asset_dir, filename),
                os.path.join(asset_dir, filename),
            )
    source_static_dir = os.path.join(os.path.dirname(__file__), "site_builder", "static")
    for filename in sorted(os.listdir(source_static_dir)):
        if filename.endswith(".css"):
            shutil.copyfile(
                os.path.join(source_static_dir, filename),
                os.path.join(asset_dir, filename),
            )
    # .nojekyll: GitHub Pages の Jekyll 処理を無効化（保険）
    open(os.path.join(OUT_DIR, ".nojekyll"), "w").close()
    print(f"生成完了: {out_path} ({len(rows)}戦)")


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root")
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    main(args.data_root)
