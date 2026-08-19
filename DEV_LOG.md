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
