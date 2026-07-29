# LoL SUP Tracker

Riot APIから自分の対戦データを取得し、CSV / TXT / Excelのレポートと
成績Webサイトに変換するツール。毎日10:00(JST)にGitHub Actionsで自動更新し、
GitHub Pagesにサイトを公開する。

## セットアップ

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env   # RIOT_API_KEY / RIOT_GAME_NAME / RIOT_TAG_LINE を設定
```

## 手動実行（ローカル）

```bash
.venv/bin/python main.py        # データ取得 + 全レポート生成（Excel含む）
```

## Webサイト公開（GitHub Pages）

`data/csv/my_matches.csv` を集計して、成績サイト（`public/index.html`）を
`build_site.py` が生成する。GitHub Actions がこれをビルドして
**GitHub Pages**（`https://<ユーザー名>.github.io/<リポジトリ名>/`）に公開する。
独自ドメインは不要。

### サイトのローカルプレビュー

```bash
.venv/bin/python build_site.py     # public/index.html を生成
open public/index.html             # ブラウザで確認（macOS）
```

## 自動ビルド & 自動更新（GitHub Actions）

`.github/workflows/deploy.yml` が次の3つのトリガーで動く。

| トリガー | 動作 |
|---|---|
| `build` ブランチへの **push** | サイトを再ビルドして Pages にデプロイ（データ取得はしない） |
| **schedule**（`0 1 * * *` UTC = **10:00 JST**） | 最新データを取得 → `data/` を commit → サイトをビルド＆デプロイ |
| **workflow_dispatch**（手動） | Actions タブの「Run workflow」からテスト実行 |

### 事前設定（3ステップ）

1. **`build` を既定（デフォルト）ブランチにする**
   GitHub の **Settings → General → Default branch** で `build` に切り替える。
   ※ cron（schedule）は既定ブランチのワークフローでしか発火しないため必須。

2. **GitHub Pages を有効化**
   **Settings → Pages → Build and deployment → Source** を **「GitHub Actions」** にする。

3. **リポジトリSecretsを登録**
   **Settings → Secrets and variables → Actions → New repository secret** から以下を登録する。

   | Secret名 | 内容 |
   |---|---|
   | `RIOT_API_KEY` | Riot APIキー |
   | `RIOT_GAME_NAME` | Riot ID（ゲーム内の名前） |
   | `RIOT_TAG_LINE` | Riot ID（#以降のタグ） |

設定後、`build` に push するか Actions から手動実行するとサイトが公開される。

`MATCH_COUNT` / `START_DATE` / `END_DATE` は `config.py` のデフォルト値がそのまま使われる
（変更したい場合は `deploy.yml` の `env` に追加するか、リポジトリVariablesとして登録して参照する）。

- 実行結果（Excelレポート）は Actions の各実行ページから
  Artifact（`lol-report`）としてダウンロードできる（保持期間30日）
- `data/raw/*.json` は `.gitignore` 対象なのでリポジトリには積まず、
  `actions/cache` でrun間キャッシュして毎回全試合を再取得しないようにしている
- データ取得（`main.py`）が失敗した場合はcommitされないため、既存データは壊れない
- `data` に変更がない場合はcommitをスキップする
- GITHUB_TOKEN による自動pushは新たなワークフローを再発火しないため、
  データ更新でデプロイが無限ループすることはない

## 出力ファイル

| パス | 内容 |
|---|---|
| `data/raw/*.json` | 試合詳細の生JSON（キャッシュ。gitignore対象） |
| `data/csv/participants.csv` | 全参加者10人分の成績（追記型） |
| `data/csv/my_matches.csv` | 自分の試合ごとの成績 |
| `data/csv/result_report.csv` | 試合ごとの整形済みテキスト |
| `data/csv/review.csv` | 手入力の振り返り（MEMO / GOOD / BAD / 次回テーマ） |
| `data/csv/summary.txt` | 全体・ロール別・キュー別・チャンピオン別の集計 |
| `data/csv/final_report.txt` | 成績＋振り返りを結合した最終レポート |
| `data/csv/monthly/`, `data/csv/yearly/` | 月別・年別の集計 |
| **`data/excel/lol_report.xlsx`** | **Excelレポート（下記）** |

### Excelレポートのシート構成

| シート | 内容 |
|---|---|
| サマリー | 全体成績とSUP成績（勝率・平均KDA・CS/m・VS/m） |
| ロール別 / キュー別 | ロール・キューごとの集計。勝率50%以上は緑、未満は赤 |
| チャンピオン別 / SUPチャンピオン別 | チャンピオンごとの集計 |
| 試合履歴 | 全試合の一覧（オートフィルタ付き） |
| レビュー | `review.csv` の内容 |

`review.csv` に振り返りを書き込むと、次回実行時に `final_report.txt` とExcelの
レビューシートへ反映される（自動実行で消えないよう保護済み）。

## 注意

Riot APIの開発用キーは**24時間で失効する**。GitHub Actionsでの自動更新を継続させるには、
[Riot Developer Portal](https://developer.riotgames.com/) で失効しないキー
（Personal / Production API Key）の発行申請が必要。開発用キーのままだと、
キー失効後は毎日の実行が失敗し、Actionsの実行履歴に赤いバツが付く
（`RIOT_API_KEY` シークレットを都度更新すれば動くが、自動化の意味が薄れる）。
