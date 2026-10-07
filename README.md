# na-stf02945-sugiyama

ローカル開発のコードを置く個人リポジトリ。
作業ルール(言語・コミット規約・コメント方針など)は [CLAUDE.md](CLAUDE.md) を参照。

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
| gitleaks | API キー・トークン等のシークレット検知 |

- 主言語が決まったら、その言語の lint/整形を `.pre-commit-config.yaml` に追加する。
- shellcheck は未導入(社内ネットワークの SSL 証明書で shellcheck-py のバイナリ取得が失敗するため)。シェルスクリプトを置くようになったら、brew 等で入れた shellcheck を `repo: local` で追加する。

## Claude Code
- `.claude/settings.json`・`.claude/hooks/security-guard.sh` は会社配布のセキュリティポリシー(編集しない)
- `.claude/skills/code-review` : 変更のレビュー用スキル
- 個人設定は `.claude/settings.local.json`(gitignore 済み)
