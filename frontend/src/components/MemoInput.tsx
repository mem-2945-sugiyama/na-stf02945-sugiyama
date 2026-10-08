import { useState } from 'react'
import { type Activity, type Category, createActivity } from '../api'

interface Props {
  date: string
  onAdded: (activity: Activity) => void
  onError: (message: string) => void
}

// AI には分からない「学び」と、作業の補足だけを手入力する欄。
// 作業内容や予定は自動で取り込むため、プロジェクト名・時刻などの入力は求めない
const MEMO_KINDS: { category: Category; label: string; placeholder: string }[] = [
  { category: 'tech_learning', label: '技術の学び', placeholder: '例: FastAPI の def エンドポイントはスレッドプールで動く' },
  { category: 'business_learning', label: 'ビジネスの学び', placeholder: '例: 報告は結論から伝えると話が早い' },
  { category: 'work', label: '作業メモ', placeholder: '例: 〇〇さんと仕様のすり合わせ(Claude 以外の作業の補足)' },
]

export function MemoInput({ date, onAdded, onError }: Props) {
  const [kind, setKind] = useState(MEMO_KINDS[0])
  const [text, setText] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!text.trim() || submitting) return
    setSubmitting(true)
    try {
      onAdded(await createActivity({ date, category: kind.category, title: text.trim() }))
      setText('')
    } catch (err) {
      onError(err instanceof Error ? err.message : 'メモの登録に失敗しました')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="memo-input" onSubmit={handleSubmit}>
      <div className="segmented" role="radiogroup" aria-label="メモの種類">
        {MEMO_KINDS.map((k) => (
          <button
            key={k.category}
            type="button"
            role="radio"
            aria-checked={kind.category === k.category}
            className={kind.category === k.category ? 'is-active' : ''}
            onClick={() => setKind(k)}
          >
            {k.label}
          </button>
        ))}
      </div>
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={kind.placeholder}
        aria-label={kind.label}
      />
      <button type="submit" disabled={!text.trim() || submitting}>
        追加
      </button>
    </form>
  )
}
