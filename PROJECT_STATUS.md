# LoL Analytics — Project Status

最終更新: 2026-09-05

## プロジェクト概要

Riot APIから自分のLeague of Legends試合データを取得し、試合結果・Role・Champion・Patch・視界・戦闘内容を集計して、静的なGitHub PagesサイトとCSV／Excelレポートを生成する個人向け分析プロジェクトです。

Match Detailを「試合終了時の結果」、Match Timelineを「結果に至る過程」としてMatch IDで結合し、SUPを中心にFightの結果、死亡、生存、味方・敵別の参加者、キル経過、オブジェクト前後の価値を確認できる構成です。

## 現在の構成

- ブランチ: `build`
- 作業ブランチ: `build`（GitのHEAD / `origin/build`を作業開始時に確認する）
- working tree: 実装単位ごとにcleanを確認する
- データ取得・解析: Python
- サイト生成: Pythonで静的HTMLを生成し、JavaScriptでフィルタ・チャート・Fight Detailを制御
- 配信: GitHub Actions + GitHub Pages
- タイムゾーン: 共通utilityによるJST固定
- raw端末間同期: PrivateDataをraw正本として初回投入・Mac復元まで完了
- 現在のデータ:
  - `my_matches.csv`: 406戦（サイト対象はリメイク除外後394戦）
  - `timeline_summary.csv`: 508試合分
  - `fight_details.json`: 508試合分、約8.6MB
  - `match_details.json`: 508試合分、10人比較用の匿名化済み公開データ
  - PrivateData: 508 Match directory、必須raw 2,540ファイル
  - combat timeline: 508試合分（公開Fight Detailと完全一致）
  - 現在Rank: Silver IV / 56 LP / 36勝49敗

## 実装済み機能

### Riot API・データ更新

- Riot Account APIによるPUUID取得
- Match-V5による期間指定Match ID取得
- Match Detail取得・ローカルraw JSON保存
- Match Timeline API取得・ローカルraw JSON保存
- League-V4による現在Solo Rank取得
- API認証値は環境変数から読み込み、GitHub ActionsではRepository Secretsから注入（ローカル端末への配置は不要）
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
  - 例: `戦闘 8W-2E-7L / 17 · 生存 7/17 · 集団戦 8`
- 一覧カードの自分のK/D/Aに、CSV既存列を使ったTeam K/D/Aを併記
  - 例: `5 / 10 / 21 (54 / 46 / 69)`
- Fight Detailの展開表示
- Fight Detailは初回展開時だけDOMを生成するlazy方式
- 元の`fight_id`を維持（飛び番が正常）
- Fightの時刻、phase、scale、result、survival、K/D/A、キル交換、参加者、キル経過、Objective Contextを表示
- Fight参加者はcombat timelineの公式`team_id`を基に`FRIENDLY` / `ENEMY`へ分類し、公開用JSONの`relation`を使って味方・敵別に表示
- Fight Detailの表示文言・Champion名・Objective名を日本語化
- 未知の内部値・Champion名は元の値へフォールバック
- カード直下に独立した「試合詳細」「戦闘詳細」ボタンを表示し、各詳細を初回展開時だけlazy生成
- 各カードの操作を「試合概要」「戦闘詳細（自分）」「戦闘詳細（全体）」「試合詳細」「コピー」の5つへ再編
- 試合概要は既存の試合情報・パフォーマンスを維持し、Role別概要（SUP / ADC / MID / TOP / JG）を既存の安全な集計値で表示
- Fightの5指標（My Fights / W-E-L / Fight勝率 / 生存率 / Teamfight）は「戦闘詳細（自分）」の先頭にFight Summaryとして表示
- 新しい全Role共通「試合詳細」はCombat / Economy / Vision / Team Contributionと匿名10人比較を表示
- カード内のコピー設定panelから、展開状態に依存せず試合概要・Fight Detail・試合詳細をプレーンテキストとしてコピー可能
- 試合詳細に試合情報、自分の成績、Team K/D/A・KP・Damage Share・Death Share、視界、Fight Summaryを表示
- 試合詳細に公式`teamId`で分類したALLY 5人 / ENEMY 5人の匿名10人比較を表示
- 10人比較は正式positionを使用し、Champion、K/D/A、CS/m、VS/m、DPMを表示
- 試合詳細の公開データにはRiot ID、Summoner Name、PUUID等の個人識別情報を含めない

### 集計・出力

- 全体、Rank、Role、Champion、Queue、Patch別集計
- 月別CSV／summary、年次summary
- result report、review template、final report
- Excelレポート生成
- 現在Rank JSONと最終更新日時の出力

### PrivateData連携

- Private repository `LoL-SUP-Tracker-PrivateData`をrawデータのクラウド正本とする構成の第一段階を実装
- `sync_private_data.py pull`でPrivateDataの`raw/`からPublicの`data/raw/`へ同期
- `sync_private_data.py push`でPublicの`data/raw/`からPrivateDataの`raw/`へ同期
- デフォルトはdry-runで、実コピーには`--apply`が必要
- 同期は追加専用で、削除と内容競合の自動上書きを行わない
- 同期スクリプトはGitのcommit / pull / pushを実行しない
- PrivateDataへ508試合分の主要raw 5種類を投入し、Macの`data/raw/`へrelative path + SHA-256完全一致で復元済み
- PrivateData側に、不足Matchを復元する手動GitHub Actions workflowを実装済み。Repository Secretsをapply時だけ注入し、既定はAPIを呼ばないdry-run
- 手動workflowは単一Matchに加えて`all_missing`一括復元へ対応。成功Matchの5 rawパスだけをmanifest経由で同期・stageし、一部失敗後も成功rawを保持する
- 手動復元workflowで不足rawの復元を完了し、公開Fight Detail 508試合とcombat timeline 508試合が一致
- Publicのschedule / workflow_dispatchは開始時にPrivateDataからrawを復元し、`main.py`後に新規rawだけをPrivateDataへ保存してからPublic生成データを更新する構成
- PrivateDataをrawの唯一のクラウド正本とし、従来の`actions/cache`によるraw保持は廃止
- Publicの通常`build` pushではRiot APIやPrivateDataへアクセスせず、Git管理済みデータからサイト生成・Pages配信だけを行う
- Public ActionsからPrivateDataへは`PRIVATE_DATA_TOKEN`を使用し、対象repositoryのContents read/writeだけを許可する
- 定期更新と手動復元は`private-raw-writer` concurrency方針を共有し、push前のremote SHA照合と通常pushで競合時に停止する
- rawの正式配置は`data/raw/{match_id}/`。PrivateDataは508試合・2,540必須rawを新構造だけで保持する
- read / writeともMatch directory構造だけを使用し、旧flat fallbackは撤去済み
- PrivateDataの旧flat rawとlegacy `death_analysis`は完全性確認後に削除済み。migrationスクリプトも保守対象から削除済み

## 主要データファイル

| ファイル | 状態 | 用途 |
|---|---|---|
| `data/csv/my_matches.csv` | Git管理 | Match DetailとTimeline SummaryをJOINしたサイト・集計の主データ |
| `data/csv/timeline_summary.csv` | Git管理 | Match ID単位のFight集計 |
| `data/csv/fight_details.json` | Git管理 | GitHub Pages用に軽量化した`review_fights`。Fight Detailの正規公開データ |
| `data/csv/match_details.json` | Git管理 | Match-V5から必要な戦績だけを匿名化した試合詳細・10人比較データ |
| `data/csv/current_rank.json` | Git管理 | 現在のSolo Rank |
| `data/csv/last_updated.txt` | Git管理 | データ更新日時 |
| `data/csv/monthly/` | Git管理（一部除外） | 月別match・summary |
| `data/excel/lol_report.xlsx` | Git管理 | Excelレポート |
| `data/raw/{match_id}/match.json` | Git管理外 | Match Detail raw JSON |
| `data/raw/{match_id}/timeline.json` | Git管理外 | Timeline raw JSON |
| `data/raw/{match_id}/combat_timeline.json` | Git管理外 | Timeline解析の詳細成果物 |
| `data/raw/{match_id}/fight_context.txt` | Git管理外 | Fight context |
| `data/raw/{match_id}/fight_review_context.txt` | Git管理外 | Fight review context |

`data/raw/`はサイズと非公開データのためGitへ追加しません。GitHub Pagesビルドはraw Timelineへ依存せず、`data/csv/fight_details.json`だけでFight Detailを生成します。

## 主要スクリプト

| スクリプト | 役割 |
|---|---|
| `main.py` | API取得、Timeline解析、各exporterを順番に実行する更新パイプライン |
| `riot_api.py` | Riot Account / Match / Timeline / League APIアクセス |
| `get_timeline.py` | 指定Match IDのTimeline単体取得 |
| `analyze_timeline.py` | TimelineからFight・死亡・Objective等を解析 |
| `timeline_summary_exporter.py` | combat timelineから試合単位集計CSVを生成 |
| `fight_detail_exporter.py` | `review_fights`を公開用`fight_details.json`へ軽量化。既存Match減少・解析失敗時は書き込みを拒否し、成功時はatomic replace |
| `match_detail_exporter.py` | Match-V5から匿名10人比較を`match_details.json`へ抽出。既存Match減少・解析失敗を拒否しatomic replace |
| `restore_missing_fight_raw.py` | 公開Fight Detailとcombat timelineの差集合を算出し、不足rawを既存Riot API・Timeline解析で復元する専用CLI（dry-run既定） |
| `sync_private_data.py` | PublicとPrivateDataのrawを非破壊でローカル同期 |
| `raw_paths.py` | Match単位の正式raw pathを一元管理 |
| `my_exporter.py` | Match Detailを自分の試合行へ変換し、Timeline SummaryをJOIN |
| `monthly_exporter.py` / `yearly_exporter.py` | 月別・年別出力 |
| `summary_exporter.py` | 全体・Role・Champion等のsummary生成 |
| `excel_exporter.py` | Excelレポート生成 |
| `build_site.py` | `public/`へ静的サイト7ページとassetsを生成 |
| `timezone_utils.py` | JST定義、JST現在時刻、JST日付解析 |

## 現在のサイト構成

現行は8ページです。

1. `index.html` — Overview
2. `support.html` — SUP詳細
3. `mid.html` — MID詳細
4. `top.html` — TOP詳細
5. `adc.html` — ADC詳細
6. `jungle.html` — JG詳細
7. `history.html` — Match History
8. `lp.html` — LP Progress

Role詳細にはOverview、Form & Streak、Performance Trend、Win/Loss Comparison、Patch Analysis、Records、Match Historyがあります。

## 重要な設計判断

- Match日時は`gameCreation`を使用し、`gameStartTimestamp`へ変更しない。
- Epoch変換・現在時刻・対象年はJSTを明示し、WindowsとGitHub Actionsで結果を一致させる。
- Match DetailとTimeline関連データはMatch IDで結合する。
- `review_fights`をサイトFight Detailの正とする。
- Fight IDは抽出後に振り直さず、元JSONのIDを表示する。
- Timeline Summaryは`my_matches.csv`へJOINするが、raw JSON自体はCSVへ埋め込まない。
- GitHub Pagesは`data/raw/`へ依存しない。公開用Fight Detailは`data/csv/fight_details.json`へ軽量化する。
- 試合詳細・10人比較はPIIを除外した`data/csv/match_details.json`を使用し、Pages buildからrawを参照しない。
- 10人比較のALLY / ENEMYは公式`teamId`、RoleはMatch-V5の`teamPosition`（空の場合のみ`individualPosition`）を使い、Champion等から推測しない。
- Fight Detailは初期表示性能のためlazy DOM生成とする。
- UI日本語化は表示時マッピングで行い、EARLY / WIN等の内部値は変更しない。
- Champion日本語名・Data Dragon ID・icon versionは、Git管理済み`data/csv/champion_registry.json`を唯一の正本とする。Registryはschedule / workflow_dispatch時だけData Dragon `ja_JP/champion.json`から安全に更新し、通常のPages buildはネットワークへアクセスせず保存済みRegistryを使用する。
- Fight参加者の味方・敵判定はChampion名や表示順から推測せず、combat timeline内の自分と各参加者の`team_id`を比較する。
- raw参照パスは引き続き`data/raw/`とし、端末間共有はsymlinkや参照先変更ではなくPrivateDataとの同期コピーで行う。
- PrivateData同期は削除禁止、競合時停止、デフォルトdry-runとし、Git操作から分離する。
- 公開`fight_details.json`の再生成は、既存Match IDが欠落する場合にデフォルトで拒否する。意図的な減少だけ`--allow-removals`で許可する。
- `.gitignore`の`data/raw/`と`public/`除外は維持する。
- Champion Registry更新は取得・parse・validation完了後にatomic replaceし、取得失敗や既存より小さい応答では既存Registryを維持する。通常Championの手動一覧は持たず、Match-V5表示名とData Dragon IDの差異など特殊aliasだけをコード管理する。

## 現在の未解決事項

- Role別のさらに固有なStatsは、取得済みの公開データを監査しながら段階的に追加する余地がある。
- `main.py`など一部既存ソースの日本語コメント／ログに文字化けが残っている。機能は動作するが保守性の課題。
- `fight_details.json`は約7.3MBあり、将来的に分割配信やオンデマンド取得を検討できる。
- 公開`fight_details.json` 508試合とPrivateDataの主要raw 5種類は整合済み。
- Riot API認証情報はローカル端末へ配置せず、PublicまたはPrivateDataのActions Secretsから各workflowへ必要時だけ注入する。
- Public ActionsからPrivateDataへの連携と新per-match raw構造によるworkflow_dispatch実証は完了済み。

## 直近で進行中の作業

Match Historyの詳細UIをRole別概要・共通詳細Stats・コピー機能へ再編した。今後はRole別に追加可能な安全なStatsを整理する。

合意済み方針:

- LP Progressは実装済み。LP未確定区間は値を補完せず、usable point間を点線connectorで表示する。勝敗を持つ試合pointは青丸（WIN）／赤丸（LOSS）に統一し、official exactは塗りあり、external historicalは同色の半透明塗りと色枠で区別する。
- Queue 420の次試合開始前に同一アカウントのLCU Rankを取得できた場合だけ、直前の`rank_after`を再検証する。W/Lが同一でLPだけ異なる時は、終了直後の観測値を保持したまま最終LPへ補正する。照合不能・不一致の原因が確定できない場合は自動補正しない。
- Queue 420の`Matchmaking`検知時には、LCU Rankの再検証セッションを開始する。30秒間隔・最大5分で読み取り、queueキャンセル後も継続し、最新の安全なRankを次試合beforeへ渡す。ポーリング中はPrivateDataを書き換えない。

## 次にやること

1. Role別に追加できる公開Statsを監査し、必要なものだけ段階的に詳細UIへ加える。
2. PrivateDataに新規MatchがMatch directory単位で保存されることを次回更新時に確認する。
3. 次のQueue 420開始前snapshotで条件が揃った場合だけ、`JP1_600584640`のLP後補正を再検証する。

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
