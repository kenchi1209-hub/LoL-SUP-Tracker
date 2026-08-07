# site_builder

LoL-SUP-Tracker Ver2.0の静的サイト生成処理。

```text
site_builder/
├─ assets/          # ブラウザ側の分析・描画JavaScript
├─ static/          # public/assetsへコピーするCSS
├─ templates/       # TOP・ロール・Match HistoryのHTMLテンプレート
├─ champion_ids.py  # Data Dragon正式ID解決
├─ patches.py       # Patch major.minor正規化
├─ data.py          # CSV/JSON読込・型変換・集計
├─ render.py        # 共通HTML部品とテンプレート値生成
├─ role.py          # 5ロールページ生成
└─ top.py           # TOPページ生成
```

`build_site.py` がテンプレートを展開し、HTML、CSS、JavaScriptを `public/` に出力する。
