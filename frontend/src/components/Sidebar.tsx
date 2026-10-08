import { type Activity, CATEGORY_LABELS, deleteActivity } from '../api'
import { DaySchedule } from './DaySchedule'
import { IcsUploader } from './IcsUploader'
import { SlackPaste } from './SlackPaste'

interface Props {
  date: string
  activities: Activity[]
  onDeleted: (id: number) => void
  onImported: () => void
  onError: (message: string) => void
}

// 日報の材料になる「その日の記録」を種類ごとに一覧する。
// 時刻に意味があるのはカレンダーの予定だけなので、予定だけカレンダー形式で表示する
export function Sidebar({ date, activities, onDeleted, onImported, onError }: Props) {
  const schedule = activities.filter((a) => a.source === 'calendar')
  const claudeWork = activities.filter((a) => a.source === 'claude')
  const slack = activities.filter((a) => a.source === 'slack')
  const memos = activities.filter((a) => a.source === 'manual')

  async function handleDelete(activity: Activity) {
    if (!window.confirm(`「${activity.title}」を削除しますか?`)) return
    try {
      await deleteActivity(activity.id)
      onDeleted(activity.id)
    } catch (err) {
      onError(err instanceof Error ? err.message : '削除に失敗しました')
    }
  }

  function deleteButton(activity: Activity) {
    return (
      <button
        type="button"
        className="icon-button"
        onClick={() => handleDelete(activity)}
        aria-label={`「${activity.title}」を削除`}
        title="削除"
      >
        ×
      </button>
    )
  }

  return (
    <aside className="sidebar">
      <section>
        <h3>本日の予定</h3>
        <DaySchedule date={date} events={schedule} onDelete={handleDelete} />
      </section>

      <section>
        <h3>Claude での作業</h3>
        {claudeWork.length === 0 ? (
          <p className="empty">取り込まれた作業はありません</p>
        ) : (
          <ul className="item-list">
            {claudeWork.map((a) => (
              // 詳細(依頼・回答の抜粋)は長いため、ホバーで確認できるようにだけしておく
              <li key={a.id} title={a.detail ?? undefined}>
                <span className="item-title">{a.title}</span>
                {deleteButton(a)}
              </li>
            ))}
          </ul>
        )}
      </section>

      {memos.length > 0 && (
        <section>
          <h3>メモ</h3>
          <ul className="item-list">
            {memos.map((a) => (
              <li key={a.id}>
                <span className={`badge badge--${a.category}`}>{CATEGORY_LABELS[a.category]}</span>
                <span className="item-title">{a.title}</span>
                {deleteButton(a)}
              </li>
            ))}
          </ul>
        </section>
      )}

      {slack.length > 0 && (
        <section>
          <h3>Slack</h3>
          <ul className="item-list">
            {slack.map((a) => (
              <li key={a.id} title={a.detail ?? undefined}>
                <span className="item-title">
                  貼り付け({(a.detail ?? '').length.toLocaleString()} 文字)
                </span>
                {deleteButton(a)}
              </li>
            ))}
          </ul>
        </section>
      )}

      <details className="imports">
        <summary>カレンダー・Slack を取り込む</summary>
        <IcsUploader date={date} onImported={onImported} onError={onError} />
        <SlackPaste date={date} onImported={onImported} onError={onError} />
      </details>
    </aside>
  )
}
