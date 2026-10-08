# na-stf02945-sugiyama

ローカル開発のコードを置く個人リポジトリ。
作業ルール(言語・コミット規約・コメント方針など)は [CLAUDE.md](CLAUDE.md) を参照。

## nippo(日報アプリ)
Claude Code の作業ログ・Google カレンダー・Slack・手入力メモを集め、日報を自動で作成するアプリ。
Claude API キーは使えないため、VS Code 拡張に同梱の Claude Code CLI(`claude -p`)を本人のログインのまま使って日報を書かせる。
AI を使わない簡易生成(ルールベースの整形)も画面から使える。

### 出力する日報の形式
```
今日やったこと
- 【会議】朝会
- 日報 API の実装(変更 8 ファイル)

技術的に学んだこと
- ...

ビジネス・ヒューマンスキルで学んだこと
特になし

今日の一言
...
```
- 活動のカテゴリが日報のセクションを決める(作業・会議 → 今日やったこと / 技術の学び / ビジネスの学び)
- 「今日やったこと」はプロジェクトごとにまとめる(リポジトリ名・時刻は出さない)
- 書くことがないセクションは「特になし」と表示する

### 構成
| 層 | 技術 | ローカル | 本番(予定) |
| --- | --- | --- | --- |
| 画面 | React + Vite + TypeScript(`frontend/`) | `npm run dev` | S3 + CloudFront |
| API | Python + FastAPI + SQLAlchemy 2(`backend/`) | docker compose | ECS |
| DB | PostgreSQL 16 | docker compose | RDS |
| 取り込み・AI | Python(`importer/`)。AI は `claude -p` | ローカルの Mac で実行 | 同左 |

- API はすべて `/api` 配下に置く(CloudFront で `/api/*` だけを ECS に振り分けるため)
- DB の接続先は環境変数 `DATABASE_URL` で切り替える
- テーブルは API の起動時に作る(マイグレーションツールは未導入)
- ローカルでは DB・API とも 127.0.0.1 にだけ公開する
- **課題**:API に認証がない。CloudFront などで外部に公開する前に、認証を入れる必要がある

### 起動
前提: Docker Desktop・Node.js 22・uv

```bash
docker compose up -d --build        # DB と API(http://localhost:8000、API ドキュメントは /docs)
cd frontend && npm install && npm run dev   # 画面(http://localhost:5173)
uv run importer/ai_server.py        # 画面の AI ボタン用サーバー(http://127.0.0.1:8001)。別のターミナルで起動
```

### 日報の自動作成(AI)
画面の「**AI で作成**」を押すと、下記 1〜4 を実行して日報を表示する(30秒ほど)。作成後に「**AI で短く**」を押すと、手直しした内容も含めて今の本文を短く書き直す(保存はされないので、確認して「保存」を押す。「元に戻す」で短縮前に戻せる)。

- 画面の AI ボタンは、Mac 上の AI サーバー(`importer/ai_server.py`)が処理する。API サーバー(Docker・AWS)には Claude Code のログイン情報がなく、`claude` を呼べないため
- AI サーバーは 127.0.0.1 でだけ待ち受け、専用ヘッダー(`X-Nippo-Client`)が無いリクエストと、Host が localhost 以外のリクエストを拒否する。他のサイトから本人の利用枠を使われないようにするため
- 短くするときの指示は `importer/shorten_prompt.txt` で調整する

ターミナルからも実行できる(定時の自動実行もこちらを使う):
```bash
uv run importer/nippo_auto.py                  # 今日の日報を作成して保存
uv run importer/nippo_auto.py --date 2026-10-07
uv run importer/nippo_auto.py --dry-run        # 取り込みまで行い、Claude に渡すプロンプトを表示
```
1. Claude Code のログを取り込む(下記)
2. Google カレンダーの予定を取り込む(ダウンロードフォルダのエクスポート。下記)
3. 登録済みの活動(手入力メモ・Slack 貼り付けを含む)と「今日の一言」を集める
4. `claude -p` で4セクションの日報を書かせ、nippo に保存する(画面の「再読み込み」で表示)

- **カテゴリの手入力は不要。** 振り分けは AI が行う
- **学びの2セクションは「本人の入力」+「AI による抽出」**。手入力メモで「技術の学び」「ビジネスの学び」を選んだものはそのまま全て載り、Claude ログなどから読み取れる学びが追加される
- 今日の一言は本人の入力をそのまま使い、入力がなければ「特になし」
- **AI の呼び出し方**:ツールを無効にし、一時ディレクトリで実行し、セッションも保存しない。外部由来の文章に指示が紛れ込んでも操作につながらないようにするため。また、生成処理そのものが次回の Claude ログ取り込みに載らないようにするため
- **利用枠**:1回あたり数千〜数万トークン。Claude Code の利用枠から消費される
- **日報の書き方**:`importer/nippo_prompt.txt` を編集して調整する
- **上書きの扱い**:AI 自動作成は、保存済みの本文を上書きする。手直しは自動作成のあとに行う
  - 画面を開いたまま自動作成が走った場合は、「再読み込み」を押してから編集する(古い本文のまま「保存」すると、AI の本文を上書きしてしまう)
  - 今日の一言は、入力欄を離れた時点で自動保存されるので、自動作成にも反映される

#### 設定ファイル
```bash
mkdir -p ~/.config/nippo && cp importer/config.sample.toml ~/.config/nippo/config.toml
chmod 600 ~/.config/nippo/config.toml
```
設定ファイルがなくても既定値で動く。モデルの変更やカレンダーの取得方法を切り替えるときに使う。
iCal の非公開アドレスを書く場合、この URL を知っていれば誰でも予定を読めるので、リポジトリやチャットには貼らない。

#### 平日 17:30 に自動実行する(任意)
```bash
sed -e "s#__UV__#$(command -v uv)#" -e "s#__REPO__#$(pwd)#" \
  importer/launchd/com.nippo.auto.plist.sample > ~/Library/LaunchAgents/com.nippo.auto.plist
launchctl load ~/Library/LaunchAgents/com.nippo.auto.plist     # 停止は launchctl unload
```
- 実行時に Docker(API・DB)が起動している必要がある
- ログは `/tmp/nippo-auto.log` に出る

### Claude Code の作業ログの取り込み
`~/.claude/projects/` のセッションログから、その日の作業をセッション単位で登録する。何度実行しても重複しない。

```bash
uv run importer/claude_logs.py                      # 今日の分
uv run importer/claude_logs.py --date 2026-10-07    # 日付を指定
uv run importer/claude_logs.py --dry-run            # 送信せず内容だけを表示
```

- タイトルは Claude Code が付けたセッション名、プロジェクトは作業ディレクトリ名
- 依頼文の抜粋、Claude の回答の抜粋、変更したファイルを詳細欄に入れる(画面で確認・編集できる)
- 取り込み後に画面で付け替えたカテゴリは、再取り込みしても維持される

### カレンダーの取り込み
会社の設定で iCal の非公開アドレスと claude.ai のコネクタが使えないため、**エクスポートしたファイルを自動で拾う方式**を標準にしている。

1. Google カレンダーの「設定 → インポート/エクスポート → エクスポート」を押す(zip がダウンロードフォルダに保存される)
2. `nippo_auto.py` を実行すると、ダウンロードフォルダにある当日保存の最新の zip を自動で取り込む

- 祝日カレンダーや共有のグループカレンダーは取り込まない
- 選択中の日付に開始する予定だけを「会議」として登録する(終日予定・キャンセル済みの予定は除外)
- 画面から zip / `.ics` を直接アップロードすることもできる
- iCal の非公開アドレスや claude.ai のコネクタが使えるようになった場合は、設定ファイルで切り替えられる(`importer/config.sample.toml` を参照)

### Slack の取り込み(貼り付け)
Slack App は社内の承認が必要なことが多いため、現時点では貼り付け方式にしている。
Slack で `from:@自分 on:today` と検索し、結果をまとめてコピーして画面の貼り付け欄に入れる。
形式は問わない(AI が日報作成時に内容を読み取る)。

### テスト
```bash
cd backend && uv run pytest
uv run --with pytest --with truststore pytest importer
cd frontend && npm run lint && npm run build
```

## セットアップ

### 前提
- [uv](https://docs.astral.sh/uv/)(`uvx` で pre-commit を実行するため)

### 手順
```bash
git clone https://github.com/mem-2945-sugiyama/na-stf02945-sugiyama.git
cd na-stf02945-sugiyama
uvx pre-commit install      # コミット時のチェック(衛生・シークレット検知)を有効化
```

全ファイルへ手動でチェックをかける場合:
```bash
uvx pre-commit run --all-files
```

## コミット前チェック(pre-commit)
| チェック | 内容 |
| --- | --- |
| pre-commit-hooks | 行末空白・末尾改行・YAML/TOML/JSON 構文・コンフリクトマーカー・大きなファイル・秘密鍵 |
| ruff | Python の lint と整形(設定は `ruff.toml`) |
| gitleaks | API キー・トークン等のシークレット検知 |

- frontend(TypeScript)の lint は npm 依存のため pre-commit には入れていない。`npm run lint` で実行する。
- shellcheck は未導入(社内ネットワークの SSL 証明書で shellcheck-py のバイナリ取得が失敗するため)。シェルスクリプトを置くようになったら、brew 等で入れた shellcheck を `repo: local` で追加する。

## Claude Code
- `.claude/settings.json`・`.claude/hooks/security-guard.sh` は会社配布のセキュリティポリシー(編集しない)
- `.claude/skills/code-review` : 変更のレビュー用スキル
- 個人設定は `.claude/settings.local.json`(gitignore 済み)
