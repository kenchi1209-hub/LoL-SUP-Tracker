# LoL Analytics — Project Status

最終更新: 2026-08-13

## プロジェクト概要

Riot APIから自分のLeague of Legends試合データを取得し、試合結果・Role・Champion・Patch・視界・戦闘内容を集計して、静的なGitHub PagesサイトとCSV／Excelレポートを生成する個人向け分析プロジェクトです。

Match Detailを「試合終了時の結果」、Match Timelineを「結果に至る過程」としてMatch IDで結合し、SUPを中心にFightの結果、死亡、生存、味方・敵別の参加者、キル経過、オブジェクト前後の価値を確認できる構成です。

## 現在の構成

- ブランチ: `build`
- HEAD / `origin/build`: `d67d6b4db66a2a6e3f7d700ccd609e841613c083`
- working tree: clean（本ファイル作成前）
- データ取得・解析: Python
- サイト生成: Pythonで静的HTMLを生成し、JavaScriptでフィルタ・チャート・Fight Detailを制御
- 配信: GitHub Actions + GitHub Pages
- タイムゾーン: 共通utilityによるJST固定
- 現在のデータ:
  - `my_matches.csv`: 393戦
  - `timeline_summary.csv`: 458試合分
  - `fight_details.json`: 458試合分、約7.3MB
  - 最新試合: `JP1_597173784` / `2026-08-13 00:56:50` JST
  - 現在Rank: Silver III / 1 LP / 34勝44敗

## 実装済み機能

### Riot API・データ更新

- Riot Account APIによるPUUID取得
- Match-V5による期間指定Match ID取得
- Match Detail取得・ローカルraw JSON保存
- Match Timeline API取得・ローカルraw JSON保存
- League-V4による現在Solo Rank取得
- APIキーは`.env`から読み込み
- Riot APIの日付境界、Match日時、更新日時をJSTへ明示統一

### Timeline解析

- `analyze_timeline.py`によるTimeline解析
- 自分のparticipant照合
- 戦闘イベントのグルーピングとFight分類
- `all_fights`、`my_fights`、`review_fights`生成
- phase / scale / result / survival分類
- Fight単位のK/D/A、参加者、キル交換、キル経過、オブジェクト文脈の抽出
- `timeline_summary_exporter.py`による試合単位Timeline集計CSV生成
- `my_matches.csv`生成時にMatch IDでTimeline SummaryをJOIN

### Match History / Fight

- Match Historyの期間・Champion・Queue・Role・勝敗フィルタ
- 日時・KDA・K/D/A・CS・Vision・Damage・試合時間等のソート
- 昇順／降順、20件ずつ追加表示
- 一覧カードにFight Summary表示
  - 例: `戦闘 8W-2E-7L · 生存 7/17 · 集団戦 8`
- 一覧カードの自分のK/D/Aに、CSV既存列を使ったTeam K/D/Aを併記
  - 例: `5 / 10 / 21 (54 / 46 / 69)`
- Fight Detailの展開表示
- Fight Detailは初回展開時だけDOMを生成するlazy方式
- 元の`fight_id`を維持（飛び番が正常）
- Fightの時刻、phase、scale、result、survival、K/D/A、キル交換、参加者、キル経過、Objective Contextを表示
- Fight参加者はcombat timelineの公式`team_id`を基に`FRIENDLY` / `ENEMY`へ分類し、公開用JSONの`relation`を使って味方・敵別に表示
- Fight Detailの表示文言・Champion名・Objective名を日本語化
- 未知の内部値・Champion名は元の値へフォールバック

### 集計・出力

- 全体、Rank、Role、Champion、Queue、Patch別集計
- 月別CSV／summary、年次summary
- result report、review template、final report
- Excelレポート生成
- 現在Rank JSONと最終更新日時の出力

## 主要データファイル

| ファイル | 状態 | 用途 |
|---|---|---|
| `data/csv/my_matches.csv` | Git管理 | Match DetailとTimeline SummaryをJOINしたサイト・集計の主データ |
| `data/csv/timeline_summary.csv` | Git管理 | Match ID単位のFight集計 |
| `data/csv/fight_details.json` | Git管理 | GitHub Pages用に軽量化した`review_fights`。Fight Detailの正規公開データ |
| `data/csv/current_rank.json` | Git管理 | 現在のSolo Rank |
| `data/csv/last_updated.txt` | Git管理 | データ更新日時 |
| `data/csv/monthly/` | Git管理（一部除外） | 月別match・summary |
| `data/excel/lol_report.xlsx` | Git管理 | Excelレポート |
| `data/raw/{match_id}.json` | Git管理外 | Match Detail raw JSON |
| `data/raw/timeline/{match_id}_timeline.json` | Git管理外 | Timeline raw JSON |
| `data/raw/timeline/{match_id}_combat_timeline.json` | Git管理外 | Timeline解析の詳細成果物 |

`data/raw/`はサイズと非公開データのためGitへ追加しません。GitHub Pagesビルドはraw Timelineへ依存せず、`data/csv/fight_details.json`だけでFight Detailを生成します。

## 主要スクリプト

| スクリプト | 役割 |
|---|---|
| `main.py` | API取得、Timeline解析、各exporterを順番に実行する更新パイプライン |
| `riot_api.py` | Riot Account / Match / Timeline / League APIアクセス |
| `get_timeline.py` | 指定Match IDのTimeline単体取得 |
| `analyze_timeline.py` | TimelineからFight・死亡・Objective等を解析 |
| `timeline_summary_exporter.py` | combat timelineから試合単位集計CSVを生成 |
| `fight_detail_exporter.py` | `review_fights`を公開用`fight_details.json`へ軽量化し、参加者の味方・敵関係を保持 |
| `my_exporter.py` | Match Detailを自分の試合行へ変換し、Timeline SummaryをJOIN |
| `monthly_exporter.py` / `yearly_exporter.py` | 月別・年別出力 |
| `summary_exporter.py` | 全体・Role・Champion等のsummary生成 |
| `excel_exporter.py` | Excelレポート生成 |
| `build_site.py` | `public/`へ静的サイト7ページとassetsを生成 |
| `timezone_utils.py` | JST定義、JST現在時刻、JST日付解析 |

## 現在のサイト構成

現行は7ページです。

1. `index.html` — Overview
2. `support.html` — SUP詳細
3. `mid.html` — MID詳細
4. `top.html` — TOP詳細
5. `adc.html` — ADC詳細
6. `jungle.html` — JG詳細
7. `history.html` — Match History

Role詳細にはOverview、Form & Streak、Performance Trend、Win/Loss Comparison、Patch Analysis、Records、Match Historyがあります。

## 重要な設計判断

- Match日時は`gameCreation`を使用し、`gameStartTimestamp`へ変更しない。
- Epoch変換・現在時刻・対象年はJSTを明示し、WindowsとGitHub Actionsで結果を一致させる。
- Match DetailとTimeline関連データはMatch IDで結合する。
- `review_fights`をサイトFight Detailの正とする。
- Fight IDは抽出後に振り直さず、元JSONのIDを表示する。
- Timeline Summaryは`my_matches.csv`へJOINするが、raw JSON自体はCSVへ埋め込まない。
- GitHub Pagesは`data/raw/`へ依存しない。公開用Fight Detailは`data/csv/fight_details.json`へ軽量化する。
- Fight Detailは初期表示性能のためlazy DOM生成とする。
- UI日本語化は表示時マッピングで行い、EARLY / WIN等の内部値は変更しない。
- Champion日本語名は既存`CHAMPION_JA_MAP`を再利用する。
- Fight参加者の味方・敵判定はChampion名や表示順から推測せず、combat timeline内の自分と各参加者の`team_id`を比較する。
- `.gitignore`の`data/raw/`と`public/`除外は維持する。

## 現在の未解決事項

- Rank専用ページは未実装。
- Rank履歴を保存する`data/csv/rank_history.csv`は未作成。
- LP推移データがないため、現状は現在Rankのみ表示可能。
- `main.py`など一部既存ソースの日本語コメント／ログに文字化けが残っている。機能は動作するが保守性の課題。
- `fight_details.json`は約7.3MBあり、将来的に分割配信やオンデマンド取得を検討できる。
- 現在のMac workspaceには`data/raw/`が存在しないため、既存`fight_details.json`への参加者`relation`反映は未完了。combat timelineを復元後、`fight_detail_exporter.py`で公開用JSONを再生成して検証する。

## 直近で進行中の作業

次期機能としてRank専用ページの仕様を整理中です。現時点ではコード・テンプレート・CSVは未実装です。

合意済み方針:

- Rank専用ページを新設する。
- LP推移をページ最上部へ置く。
- Role Filterは`ALL / SUP / MID / JG / TOP / ADC`。
- LP推移はRole Filterの対象外。
- Summary / Monthly / Champion / Fight / Match HistoryはRole Filterに連動する。
- `data/csv/rank_history.csv`を新設し、更新時点のRank・LPを履歴保存する。

## 次にやること

1. `rank_history.csv`の列設計と重複記録ルールを確定する。
2. 日次更新時に現在Rankを履歴へ追記するexporterを実装する。
3. Rank専用ページのPython builder、HTML template、CSS、JavaScriptを追加する。
4. LP推移を最上部へ実装し、Role Filterから独立させる。
5. Role Filter連動のSummary / Monthly / Champion / Fight / Match Historyを実装する。
6. GitHub Actions環境でGit管理データだけを使ってRankページを生成できることを確認する。

## 注意事項

- raw Match / Timeline JSONやAPIキーをGitへ追加しない。
- Fight Detailデータを更新・再生成した場合は、`data/csv/fight_details.json`もcommit対象とする。
- `fight_details.json`を再生成する前に、必要なcombat timelineがローカルに揃っているか確認する。
- `build_site.py`単体はRiot APIへアクセスせず、Git管理済みデータだけで生成できる状態を維持する。
- Fight分類、内部enum、Match ID、集計列を表示都合で書き換えない。
- 既存のMatch Historyフィルタ・ソート・Roleページ・390pxレスポンシブを回帰確認する。

## 端末間・セッション間の運用ルール

`PROJECT_STATUS.md`をChatGPT / Codex間の「現在地の共有メモリ」、`DEV_LOG.md`を実装履歴・経緯確認用の共有ログとして扱います。

### 作業開始時

1. Codexは必ず`git pull`を実行する
2. `PROJECT_STATUS.md`を確認する
3. 必要に応じて`DEV_LOG.md`の最新エントリも確認する

### 実装単位の完了時

1. 実装結果に合わせて`PROJECT_STATUS.md`を最新状態へ更新する
2. `DEV_LOG.md`へ作業内容を追記する
3. コード変更とドキュメント更新を一緒にcommit / pushする

未実装の仕様は「予定」「合意済み方針」などと明示し、実装済みの内容と混同しません。実装によって仕様・ファイル構成・データ構造・現在値が変わった場合は、コードだけを更新して`PROJECT_STATUS.md`を古い状態のまま残しません。

ChatGPT側は開発相談の再開時、必要に応じてGitHub上の最新`PROJECT_STATUS.md`と`DEV_LOG.md`を参照して現在地を同期します。Gitへpushされていないローカル変更はChatGPT側から確認できないため、作業途中の状態は必要に応じてユーザーが共有します。

`PROJECT_STATUS.md`は常に最新状態だけを残します。`DEV_LOG.md`は日付単位の追記型履歴です。同じ説明を両方へ過度に重複させず、現状はStatus、経緯はLogへ記録します。
