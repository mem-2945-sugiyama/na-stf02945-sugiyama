# TypeScript / React レビューチェックリスト

## よくあるミス

### 型
- **any・型アサーションでの握りつぶし**
  - 説明: `as any` や `as Foo` で型エラーを黙らせると、API の契約変更をコンパイル時に検知できない
- **API レスポンスの型と実装の乖離**
  - 説明: バックエンドのスキーマ(`backend/app/schemas.py`)と `frontend/src/api.ts` の型が一致しているか。null 許容の扱いに注意

### 非同期・fetch
- **エラー処理の欠落**
  - 説明: `fetch` は 4xx/5xx でも reject しない。`res.ok` を確認しているか
- **競合状態(古いレスポンスによる上書き)**
  - 説明: 日付切り替えなどで連続して取得したとき、遅れて返った古いレスポンスで状態を上書きしていないか(AbortController やフラグで防ぐ)

### React
- **useEffect の依存配列**
  - 説明: 依存の漏れで古い値を参照する、または不要な再実行で無限ループになる
- **state の直接変更**
  - 説明: 配列・オブジェクトを破壊的に変更してから set している(再描画されない)
- **リストの key にインデックスを使う**
  - 説明: 並び替えや削除で表示が崩れる。ID を使う
- **アンマウント後の setState**
  - 説明: 非同期処理の完了時にコンポーネントが既に消えていないか

### セキュリティ
- **dangerouslySetInnerHTML**
  - 説明: ユーザー入力や取り込みデータ(ログ・カレンダー)を HTML として埋め込んでいないか

## 参考資料
- [React 公式: useEffect](https://react.dev/reference/react/useEffect)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html)
