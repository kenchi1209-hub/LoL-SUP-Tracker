# Daily UpdateからPages公開まで

`daily_update.ps1` はデータ取得・Fight検証成功後、PrivateData push成功時に
`daily_update_pages.py` を呼びます。変更なしの場合も、ローカルHEADと
取得済みorigin/mainが一致したときだけ未公開SHAの復旧を許可します。
データ取得・検証・commit・pushの失敗、SHA不明では起動しません。

GitHub CLIの認証、Publicへのpush権限、workflowのactive状態を確認し、
既存runを調べます。確認不能はUNKNOWNで停止します。起動は次の引数です。

```
gh workflow run deploy.yml --repo kenchi1209-hub/LoL-SUP-Tracker --ref build -f private_data_pushed=true -f private_data_sha=<40桁SHA>
```

指定SHAは入力検証後にcheckoutし、実HEADと比較します。不一致はbuild失敗です。
Riot取得・PrivateData更新・Publicレジストリ更新は既存build-only条件でスキップします。
入力省略の既存手動実行、push、scheduleは従来のmain checkoutを維持します。
実SHAは既存の`PAGES_INPUT_PRIVATE_SHA`記録へ残します。

SHA付きdispatchのタイトルは`Pages PrivateData | <SHA>`です。実行中runを
このタイトルで照合し、完了成功は既存の実SHA記録とbuild/deploy両jobの成功を
必須とします。旧形式runの証跡不明、API失敗はUNKNOWNです。
公開済み・実行中は再起動せず、失敗済みは再試行可能です。
ローカルのOSファイルロックで同時照会・起動を防止します。
GitHubのworkflow_dispatch APIに原子的なSHA別重複排除機能はないため、
別PCから完全同時に起動する場合は照会とdispatch間の競合が残ります。
既存workflow concurrencyは維持しています。

起動前に見たrun IDを除外して新runを発見します。10秒間隔、処理全体の上限180秒、
個々のAPI呼び出しは最大10秒（既存証跡照会は最大6秒）です。
タイムアウトはPENDING、通信失敗はUNKNOWNです。直近1000件を取得し、
上限に達した場合は確認不十分としてUNKNOWNにします。

サマリーとallowlistログにはPages Trigger、Pages Deploy、Pages Detail、run IDを
分けて記録します。dispatch成功だけではSUCCESSにしません。
Pages失敗はデータ更新・pushの成功や終了コードを取り消しません。
GitHub出力や認証情報、生APIレスポンスを永続ログへ保存しません。

検証例（架空のID。API取得・push・deployは各fixtureでmock）:

```powershell
$env:RIOT_GAME_NAME='FixturePlayer'
$env:RIOT_TAG_LINE='TEST'
python -m unittest discover -q
node --test test_*.js
python build_site.py
```
