import { type ReactNode, useEffect, useRef, useState } from 'react'
import {
  AiError,
  aiGenerate,
  aiShorten,
  fetchReport,
  fetchReportDraft,
  saveComment,
  saveReport,
} from '../api'

interface Props {
  date: string
  onError: (message: string) => void
  // 「再読み込み」時に呼ぶ。AI 自動作成で取り込まれた記録もサイドバーに反映するため
  onReload?: () => void
  // 本文の下に置く入力欄(学びメモ)。日報と一緒に1画面で操作できるようにするため
  children?: ReactNode
}

// 日報エリア。日付切替のたびに保存済み日報を読み込み、生成・編集・保存・コピーを行う。
export function ReportPanel({ date, onError, onReload, children }: Props) {
  const [comment, setComment] = useState('')
  const [body, setBody] = useState('')
  const [generating, setGenerating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [copyMessage, setCopyMessage] = useState<string | null>(null)
  // 読み込み中は前の日付の本文が残っているため、保存・生成を止めて別の日に保存されるのを防ぐ
  const [loading, setLoading] = useState(true)
  // 読み込みに失敗した状態で保存すると、空欄で保存済みの日報を上書きしてしまうため保存系を止める
  const [loadFailed, setLoadFailed] = useState(false)
  // 最後に読み込み・保存した本文。未保存の編集があるかの判定に使う
  const [savedBody, setSavedBody] = useState('')
  // AI の処理中(数十秒かかる)は他の操作で本文が食い違わないよう、保存系も止める
  const [aiBusy, setAiBusy] = useState<'generate' | 'shorten' | null>(null)
  // 「AI で短く」の直前の本文。結果が気に入らないときに戻せるようにするため
  const [beforeShorten, setBeforeShorten] = useState<string | null>(null)
  const blocked = loading || loadFailed || aiBusy !== null
  const dirty = body !== savedBody
  // 非同期処理の完了時に、開始時と同じ日付を表示中かを確かめるため
  const currentDate = useRef(date)

  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    currentDate.current = date
    setCopyMessage(null)
    setLoading(true)
    fetchReport(date)
      .then((report) => {
        if (cancelled) return
        // 未保存(404 相当)の場合は report が null になるため空欄として扱う
        setComment(report?.comment ?? '')
        setBody(report?.body ?? '')
        setSavedBody(report?.body ?? '')
        setBeforeShorten(null)
        setLoadFailed(false)
      })
      .catch((err) => {
        if (cancelled) return
        setLoadFailed(true)
        onError(err instanceof Error ? err.message : '日報の読み込みに失敗しました')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [date, onError, reloadKey])

  async function handleAiGenerate() {
    if (dirty && !window.confirm('未保存の編集があります。AI で作成し直すと上書きされます。続けますか?')) {
      return
    }
    setAiBusy('generate')
    try {
      // AI サーバーは保存済みの一言を読むため、入力中の一言を先に保存しておく
      await saveComment(date, comment)
      const result = await aiGenerate(date)
      if (currentDate.current !== date) return
      setBody(result.body)
      setSavedBody(result.body)
      setBeforeShorten(null)
      // AI 作成時に取り込まれた Claude ログ・カレンダーをサイドバーにも反映する
      onReload?.()
    } catch (err) {
      if (err instanceof AiError && err.unsavedBody && currentDate.current === date) {
        // 生成はできたが保存に失敗した場合、本文は画面に出して手動で保存できるようにする
        setBody(err.unsavedBody)
      }
      onError(err instanceof Error ? err.message : 'AI での作成に失敗しました')
    } finally {
      setAiBusy(null)
    }
  }

  async function handleAiShorten() {
    setAiBusy('shorten')
    const original = body
    try {
      const result = await aiShorten(original)
      if (currentDate.current !== date) return
      setBeforeShorten(original)
      setBody(result.body)
    } catch (err) {
      onError(err instanceof Error ? err.message : 'AI での短縮に失敗しました')
    } finally {
      setAiBusy(null)
    }
  }

  function handleUndoShorten() {
    if (beforeShorten === null) return
    setBody(beforeShorten)
    setBeforeShorten(null)
  }

  async function handleGenerate() {
    setGenerating(true)
    try {
      const draft = await fetchReportDraft(date, comment)
      if (currentDate.current === date) setBody(draft.body)
    } catch (err) {
      onError(err instanceof Error ? err.message : '日報の生成に失敗しました')
    } finally {
      setGenerating(false)
    }
  }

  async function handleSave() {
    setSaving(true)
    try {
      const saved = await saveReport(date, body, comment)
      if (currentDate.current === date) {
        setSavedBody(saved.body)
        setBeforeShorten(null)
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : '日報の保存に失敗しました')
    } finally {
      setSaving(false)
    }
  }

  // 入力欄を離れた時点で一言だけ保存する。「保存」を押す前に AI 自動作成が走っても一言を反映させるため
  async function handleCommentBlur() {
    if (blocked) return
    try {
      await saveComment(date, comment)
    } catch (err) {
      onError(err instanceof Error ? err.message : '今日の一言の保存に失敗しました')
    }
  }

  function handleReload() {
    if (dirty && !window.confirm('未保存の編集があります。破棄して再読み込みしますか?')) return
    setReloadKey((k) => k + 1)
    onReload?.()
  }

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(body)
      setCopyMessage('コピーしました')
      setTimeout(() => setCopyMessage(null), 2000)
    } catch {
      onError('クリップボードへのコピーに失敗しました')
    }
  }

  return (
    <section className="report-panel">
      <div className="report-header">
        <h2>日報</h2>
        <div className="report-actions">
          <button type="button" className="ai" onClick={handleAiGenerate} disabled={blocked}>
            {aiBusy === 'generate' ? 'AI 作成中…(30秒ほど)' : 'AI で作成'}
          </button>
          <button type="button" className="ai" onClick={handleAiShorten} disabled={blocked || !body.trim()}>
            {aiBusy === 'shorten' ? '短くしています…' : 'AI で短く'}
          </button>
          {beforeShorten !== null && (
            <button type="button" onClick={handleUndoShorten} disabled={blocked}>
              元に戻す
            </button>
          )}
          <span className="action-separator" aria-hidden="true" />
          <button type="button" onClick={handleReload} disabled={loading || aiBusy !== null}>
            再読み込み
          </button>
          <button type="button" onClick={handleGenerate} disabled={blocked || generating}>
            {generating ? '生成中...' : '簡易生成(AI なし)'}
          </button>
          <button type="button" onClick={handleSave} disabled={blocked || saving}>
            {saving ? '保存中...' : dirty ? '保存 *' : '保存'}
          </button>
          <button type="button" className="primary" onClick={handleCopy} disabled={!body}>
            {copyMessage ?? 'コピー'}
          </button>
        </div>
      </div>
      <textarea
        className="report-body"
        value={body}
        onChange={(e) => {
          setBody(e.target.value)
          // 短縮後に手直ししたら「元に戻す」は出さない(押すと手直しが確認なしで消えるため)
          setBeforeShorten(null)
        }}
        aria-label="日報の本文"
        placeholder={
          '「AI で作成」を押すと、Claude のログ・カレンダー・Slack・メモから日報を自動で書きます。\n' +
          '(事前にターミナルで uv run importer/ai_server.py を起動しておいてください)'
        }
      />
      <label className="comment-row">
        <span>今日の一言</span>
        <input
          type="text"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          onBlur={handleCommentBlur}
          placeholder="未入力なら「特になし」になります"
        />
      </label>
      {children}
    </section>
  )
}
