data.py
CSV/JSON読込・型変換・集計

render.py
HTML部品・TOP描画・CSS

build_site.py
全体制御・public出力

# site_builder
LoL-SUP-Tracker Ver2.0のサイト生成処理を分割するためのディレクトリ。
現行の`build_site.py`は、データ読込・集計・HTML生成・CSS・ファイル出力を1ファイルで処理している。
Ver2.0では、表示を維持したまま段階的に以下の構成へ整理する。
## 想定構成
```text
site_builder/
├─ __init__.py
├─ data.py
├─ render.py
└─ README.md
