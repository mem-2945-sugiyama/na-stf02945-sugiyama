import { useState } from 'react'
import { importSlackText } from '../api'

interface Props {
  date: string
  onImported: () => void
  onError: (message: string) => void
}

// Slack の検索結果(from:@自分 on:today など)を貼り付けて取り込む。
// Slack App の承認が不要な取り込み手段として用意している
export function SlackPaste({ date, onImported, onError }: Props) {
  const [text, setText] = useState('')
  const [importing, setImporting] = useState(false)
  const [done, setDone] = useState(false)

  async function handleImport() {
    if (!text.trim() || importing) return
    setImporting(true)
    setDone(false)
    try {
      await importSlackText(date, text.trim())
      setText('')
      setDone(true)
      onImported()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Slack の投稿の取り込みに失敗しました')
    } finally {
      setImporting(false)
    }
  }

  return (
    <div className="slack-paste">
      <p className="hint">
        Slack で <code>from:@自分 on:today</code> と検索し、結果をまとめてコピーして貼り付けてください(形式は問いません)
      </p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={4}
        placeholder="Slack の投稿を貼り付け"
      />
      <div className="slack-paste-actions">
        <button type="button" onClick={handleImport} disabled={!text.trim() || importing}>
          {importing ? '取り込み中...' : 'Slack の投稿を取り込む'}
        </button>
        {done && <span className="import-result">取り込みました</span>}
      </div>
    </div>
  )
}
