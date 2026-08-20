# LoL Analytics — Development Log

日付単位の追記型開発日報です。最新状態と次の作業は`PROJECT_STATUS.md`を正とします。

## 2026-08-11

### 今日やったこと

- Match日時処理を実行環境依存から明示的なJSTへ統一。
- Match-V5 Timeline API取得を追加。
- 指定Match IDのTimelineを`.env`のAPIキーで取得する`get_timeline.py`を追加。
- `analyze_timeline.py`でparticipant照合、死亡前後イベント、Fight、Objective文脈の解析を実装。
- `timeline_summary_exporter.py`で試合単位のFight集計をCSV化。
- `my_matches.csv`生成時にTimeline SummaryをMatch IDでJOIN。
- Match HistoryカードへFight Summaryと展開式Fight Detailを追加。

### 決定事項

- Match日時には引き続き`gameCreation`を使う。
- 日付境界・表示時刻・現在年はJSTを明示する。
- Match DetailとTimelineはMatch IDで結合する。
- Fight Detailでは`review_fights`を正とし、元の`fight_id`を維持する。
- Fight Detail DOMは展開時にlazy生成する。

### 実装・変更ファイル

- `timezone_utils.py`
- `my_exporter.py`
- `riot_api.py`
- `main.py`
- `get_timeline.py`
- `analyze_timeline.py`
- `timeline_summary_exporter.py`
- `site_builder/render.py`
- `site_builder/assets/match-history.js`
- `site_builder/static/match-history.css`

### 動作確認

- WindowsとUTC環境に依存しないJST変換を確認。
- 代表試合`JP1_576319447`の日時が`2026-04-13 00:41:20`で一致。
- `JP1_596841033`のTimeline取得がstatus 200で成功。
- 同試合のLeonaがparticipantId 5、5/10/21、死亡10件であることを確認。
- Fight Detail 17件と飛び番IDを確認。
- Match Historyのフィルタ、ソート、追加表示、Roleページ、390px表示を回帰確認。

### 未解決

- raw Timelineは`data/raw/`配下でGit管理外のため、この時点の実装ではGitHub PagesビルドにFight Detailが渡らない問題が残った。
- Rank履歴とRank専用ページは未実装。

### 次回

1. Fight DetailをGitHub Pagesで利用できる公開用データへ変換する。
2. Fight Detailの表示文言とChampion名を日本語化する。
3. Rank専用ページのデータ設計を検討する。

## 2026-08-12

### 今日やったこと

- Fight Detailの表示文言、phase、scale、result、survival、Objective名を表示時マッピングで日本語化。
- 参加者、killer、victim、assistのChampion名を既存`CHAMPION_JA_MAP`で日本語化。
- `fight_detail_exporter.py`を追加し、全combat timelineの`review_fights`を公開用JSONへ軽量化。
- `data/csv/fight_details.json`を生成しGit管理対象へ追加。
- `site_builder/render.py`のraw Timeline直接参照を廃止し、公開用JSON参照へ切り替え。
- `main.py`のTimeline解析後にTimeline SummaryとFight Detail公開JSONを再生成する処理を接続。
- 現在Rank取得データを更新。

### 決定事項

- `data/raw/`は引き続きGit管理対象外とする。
- `data/csv/fight_details.json`はGitHub Pagesビルドに必要なためGit管理する。
- GitHub Pagesのサイト生成はraw Match / Timelineに依存させない。
- Fight Detailの日本語化は表示層だけで行い、EARLY / WIN等の内部値は維持する。
- Rank専用ページを今後新設する。
- RankページはLP推移を最上部に置く。
- Role Filterは`ALL / SUP / MID / JG / TOP / ADC`とする。
- LP推移はRole Filter対象外とし、Summary / Monthly / Champion / Fight / Match HistoryはRole Filterへ連動させる。
- Rank履歴保存用に`rank_history.csv`を新設する予定。

### 実装・変更ファイル

- `.gitignore`
- `fight_detail_exporter.py`
- `data/csv/fight_details.json`
- `main.py`
- `site_builder/render.py`
- `site_builder/assets/match-history.js`
- `site_builder/static/match-history.css`
- Timeline集計を含む各CSV／レポート生成物

### 動作確認

- `fight_details.json`生成成功、失敗0件。
- rawパスへのアクセスを強制的に失敗させた状態でも`build_site.py`が成功。
- `JP1_596841033`のFight Detail 17件を公開JSONだけで生成。
- Fight ID `1, 4, 8, 10, 12, 14, 16, 19, 22, 23, 25, 27, 29, 30, 34, 40, 42`を維持。
- 一覧表示`戦闘 8W-2E-7L · 生存 7/17 · 集団戦 8`を確認。
- 日本語化された参加者、キル経過、Objective Contextを確認。
- lazy生成、既存フィルタ、ソート、Roleページ、レスポンシブ、console error 0件を確認。

### 未解決

- Rank専用ページと`rank_history.csv`はまだ存在しない。
- LP推移の蓄積開始時点、CSV列、同日・同値の重複排除ルールが未決定。
- 一部Pythonソースの既存日本語ログ／コメントに文字化けが残る。
- 公開用`fight_details.json`のサイズは今後増加するため、将来的な分割・遅延取得の余地がある。

### 次回

1. `rank_history.csv`のスキーマと追記ルールを決める。
2. Rank専用ページのbuilder / template / assetsを実装する。
3. LP推移を最上部に配置し、Role Filterから独立させる。
4. Role Filter連動のSummary / Monthly / Champion / Fight / Match Historyを実装する。

## 2026-08-13

### 今日やったこと

- Match Historyの自分のK/D/Aへ、`my_matches.csv`既存列のTeam K/D/Aを半角括弧で併記。
- `fight_detail_exporter.py`でcombat timeline内の自分とFight参加者の`team_id`を比較し、公開用参加者データへ`FRIENDLY` / `ENEMY`の`relation`を保持する処理を実装。
- Fight Detailの参加者表示を、既存のChampion日本語名を維持したまま味方・敵の2行へ分離。
- 旧公開JSONのように`relation`がない参加者は誤分類せず「不明」と表示する互換処理を追加。

### 変更ファイル

- `fight_detail_exporter.py`
- `site_builder/render.py`
- `site_builder/assets/match-history.js`
- `site_builder/static/match-history.css`
- `PROJECT_STATUS.md`
- `DEV_LOG.md`

### 検証結果

- Python構文チェック、全JavaScriptの`node --check`、`python build_site.py`、`git diff --check`に成功。
- Match Historyは381件を維持し、期間・Champion・Queue・Role・勝敗Filter、日時Sort、昇順／降順、20件追加表示を確認。
- 代表試合`JP1_596841033`で`5 / 10 / 21 (54 / 46 / 69)`、Fight Detail 17件、Fight ID、`8W-2E-7L`、生存`7/17`、Teamfight 8を確認。
- 複数Fight Detailの同時展開、lazy生成、Champion日本語表示、390px幅で横方向のはみ出しなし、console error / warningなしを確認。
- syntheticな公式`team_id`入力で、自分のレオナを含む味方と敵が正しく分離されることを確認。

### 設計判断

- Team K/D/Aは既存CSV列を再利用し、表示層で再計算しない。
- Fight参加者の陣営はChampion名、並び順、キル経過から推測しない。combat timelineの公式`team_id`だけを正とし、公開サイトは引き続き`data/csv/fight_details.json`だけを参照する。

### 未完了

- 現在のMac workspaceにはGit管理外のcombat timelineが0件であるため、`data/csv/fight_details.json`の参加者`relation`再生成は未完了。rawデータ復元後に全458試合分を再生成し、代表試合の味方・敵表示を最終確認する必要がある。
- Rank専用ページは未実装のまま。

## 2026-08-19

### 今日やったこと

- Public / Privateの2Repo間でrawを同期する`sync_private_data.py`を追加。
- `pull`（PrivateDataからTracker）と`push`（TrackerからPrivateData）を、Git操作を伴わないローカルディレクトリ同期として実装。
- dry-run既定、`--apply`必須、SHA-256比較、削除禁止、競合時の全コピー停止、symlink拒否、atomic copyを実装。
- `--private-data-dir`、`LOL_PRIVATE_DATA_DIR`、sibling directoryの順でPrivateDataパスを選択する構成を実装。
- Publicの`data/raw/`がGit ignore対象で、追跡ファイルがないことを実行前に検査する安全処理を追加。
- PrivateData側へrawディレクトリ雛形と運用READMEを追加。

### 変更ファイル

- `sync_private_data.py`
- `PROJECT_STATUS.md`
- `DEV_LOG.md`
- PrivateData: `README.md`
- PrivateData: `raw/.gitkeep`
- PrivateData: `raw/timeline/.gitkeep`

### 検証結果

- 実rawは使用せず、一時ディレクトリ内の一時Git repositoryだけで13テストを実施し、全件成功。
- COPY / SKIP / CONFLICT、競合時の全コピー停止、dry-run / apply、空・不存在・非Git・同一 / 入れ子・symlink拒否を確認。
- destinationだけに存在するファイルが削除されないこと、pull / push両方向、Public raw追跡時の停止、パス指定優先順位を確認。
- Python構文チェックと`git diff --check`を実施。

### 未実装・次工程

- PrivateDataへの実raw投入は未実施。Windows端末からの初回投入が次工程。
- GitHub ActionsとのPrivateData連携は未実装。現在の自動更新rawは従来どおりActions cacheで保持する。
- Actions連携前にPrivate repositoryの認証方式、競合処理、同時実行時の更新順序を確定する。

## 2026-08-20

### 今日やったこと

- PrivateDataのraw 2,351ファイルをMacのPublic `data/raw/`へ復元し、relative path + SHA-256の全件一致を確認済みの状態を引き継いだ。
- Public fast-forward前の`fight_details.json` 499試合とcombat timeline 470試合を比較し、不足29 Match IDを差集合で再確認した。
- `fight_detail_exporter.py`へ、既存公開Matchの減少と解析失敗がある場合に書き込み前で停止する安全装置を追加した。
- exporterの正常出力を同一ディレクトリ内の一時ファイル生成と`os.replace`によるatomic replaceへ変更した。
- 明示的な公開データ減少時だけ使用する`--allow-removals`を追加した。通常の`main.py`呼び出しは従来どおり減少を許可しない。
- `restore_missing_fight_raw.py`を追加し、公開Fight Detailとcombat timelineの差集合から復元対象を自動算出するdry-run / apply CLIを実装した。
- 復元処理は既存`riot_api.py`の取得・保存関数と`analyze_timeline.py`を再利用し、`--limit`と`--match-id`による限定実行に対応した。

### 変更ファイル

- `fight_detail_exporter.py`
- `restore_missing_fight_raw.py`
- `PROJECT_STATUS.md`
- `DEV_LOG.md`
- PrivateData: `.github/workflows/restore-missing-fight-raw.yml`
- PrivateData: `README.md`
- PrivateData: `.gitignore`（`.DS_Store`除外）

### 検証結果

- Public fast-forward前の実データでexporterを通常実行し、`existing: 499` / `generated: 470` / `missing: 29`として非zero終了し、`fight_details.json`のSHA-256が不変であることを確認した。
- Public fast-forward前の復元スクリプトdry-runで不足29件を検出し、Match Detail / Timeline / combat timelineの不足とAPI取得対象が各29件であることを確認した。
- `JP1_556572228`が復元対象へ含まれることを確認した。
- 一時ディレクトリとモックで、減少拒否、欠落なし書き込み、明示的減少許可、解析失敗拒否、atomic replace、差集合、dry-run、`--limit`、`--match-id`、既存raw skip、API失敗記録、成功raw保持、API key相当文字列の非表示を確認した。

### 未実施・次工程

- 最新`origin/build`へ競合なしでfast-forward後、`fight_details.json`と`timeline_summary.csv`が508試合、combat timelineが470試合、missingが38試合になったことを確認した。増加した9試合もraw未復元のためmissingへ加わった。
- 不足38試合への実Riot APIアクセスは未実施。
- `fight_details.json`の本番再生成は未実施で、remote最新の508試合を維持している。
- MacローカルへRiot API認証情報は配置せず、PrivateData repositoryのActions Secretsを使う方針へ変更した。
- PrivateData側へ手動`Restore missing Fight raw` workflowを追加した。Match IDを1件指定し、`apply: false`では検出のみ、明示的な`apply: true`でだけAPI取得・5ファイル検証・PrivateDataへの非破壊同期・対象5パス限定commitを行う。
- workflowはPublic `build`の復元スクリプトをcheckoutして再利用し、Public repositoryや`fight_details.json`を更新しない。
- workflowとSecrets連携は静的検証までで、実dispatchと実APIアクセスは未実施。
- 次工程は両repoの関連変更をcommit・push後、workflowをdry-runし、`JP1_556572228`を1件限定で実復元すること。

### 追加対応: 残りmissing一括復元基盤

- Actionsで`JP1_556572228`の5 raw復元とPrivateData保存が成功したことを確認し、MacのPublic rawへ非破壊同期した。
- 同期後は公開Fight Detail 508試合、combat timeline 471試合、missing 37試合。`JP1_556572228`はmissingから除外された。
- 復元済みMatchを`--match-id`へ指定した場合は、エラーではなくAPIを呼ばない正常SKIPへ変更した。
- `restore_missing_fight_raw.py`へ`--all-missing`、`--limit`併用、結果JSON、成功raw manifest出力を追加した。
- `sync_private_data.py`へ同期対象相対パスmanifestを追加し、成功Matchの5 rawだけをPrivateDataへ同期できるようにした。
- PrivateData workflowへ`all_missing`入力を追加し、apply時に一部API失敗があっても成功結果を同期・1 commitへまとめた後、最終結果を非zeroにする構成へ変更した。
- 一括実API取得、workflow dispatch、公開`fight_details.json`再生成は未実施。

### 追加対応: 定期ActionsのPrivateData自動保存

- Public `deploy.yml`のschedule / workflow_dispatch経路へ、PrivateData checkout、rawのdry-run / apply pull、`main.py`、完全性検証、dry-run / apply pushを追加した。
- PrivateData同期が成功し、新規rawをPrivateDataへ通常pushした後にだけPublic生成データをcommitする順序へ変更した。
- PrivateDataでは既存tracked rawの変更とraw外の変更を拒否し、新規`raw/`だけをstageする。開始時SHAとpush直前の`origin/main`が一致しない場合も停止する。
- rawの二重正本化を避けるため、`actions/cache`による`data/raw`保持を廃止し、PrivateDataを唯一のクラウド正本とした。
- 通常の`build` pushはPrivateData checkout、raw同期、Riot API処理を通らず、従来どおり静的サイト生成とPages配信だけを行う。
- `verify_fight_raw_completeness.py`を追加し、公開Fight Detailとcombat timelineのMatch集合および全Matchの主要raw 5種類をcommit前に検証する構成とした。
- PublicからPrivateDataへは、PrivateData repositoryのContents read/writeだけを許可した`PRIVATE_DATA_TOKEN`を使用する設計とした。Secret値はworkflowで出力しない。
- Publicの定期workflowとPrivateDataの手動復元workflowは`private-raw-writer`という同一方針名を使用する。GitHubのconcurrencyはrepository単位のため、実際のcross-repository競合はremote SHA再確認とforceなしの通常pushで防止する。
- 実Actions実行、Riot APIアクセス、raw更新、commit / pushは未実施。

## 運用ルール

### 作業開始時

1. `git pull`
2. `PROJECT_STATUS.md`を読む
3. 必要に応じて本ファイルの最新日付を読む

### 作業終了時

1. `PROJECT_STATUS.md`を最新状態へ更新
2. 本ファイルへ当日の作業内容を追記
3. コード変更と一緒にcommit / push

`PROJECT_STATUS.md`は最新状態のみ、本ファイルは履歴として追記します。同じ情報を両方へ冗長に書きすぎないようにします。
