import { useCallback, useEffect, useRef, useState } from 'react'
import { type Activity, fetchActivities } from '../api'
import { DateNav } from '../components/DateNav'
import { MemoInput } from '../components/MemoInput'
import { ReportPanel } from '../components/ReportPanel'
import { Sidebar } from '../components/Sidebar'
import { todayKey } from '../dateUtils'

// 時刻順を保つための並べ替え(編集で started_at は変わらない契約だが、
// インポートなどで順不同に届いた場合に備えて都度ソートする)
function sortByStartedAt(activities: Activity[]): Activity[] {
  // 文字列比較だと小数秒の有無やタイムゾーン表記の違いで順序が崩れるため、時刻値で比較する
  return [...activities].sort((a, b) => Date.parse(a.started_at) - Date.parse(b.started_at))
}

export function DayPage() {
  const [date, setDate] = useState(todayKey())
  const [activities, setActivities] = useState<Activity[]>([])
  const [error, setError] = useState<string | null>(null)

  // 日付を素早く切り替えたとき、遅れて返った前の日付のレスポンスで一覧を上書きしないよう、
  // 表示中の日付と一致する場合だけ反映する
  const currentDate = useRef(date)

  const loadActivities = useCallback((d: string) => {
    fetchActivities(d)
      .then((list) => {
        if (currentDate.current === d) setActivities(sortByStartedAt(list))
      })
      .catch((err) => setError(err instanceof Error ? err.message : '活動一覧の取得に失敗しました'))
  }, [])

  useEffect(() => {
    currentDate.current = date
    setError(null)
    loadActivities(date)
  }, [date, loadActivities])

  function handleAdded(activity: Activity) {
    // 登録中に日付を切り替えた場合、別の日の活動を今の一覧に混ぜない
    if (activity.date !== currentDate.current) return
    setActivities((prev) => sortByStartedAt([...prev, activity]))
  }

  function handleDeleted(id: number) {
    setActivities((prev) => prev.filter((a) => a.id !== id))
  }

  return (
    <div className="day-page">
      <header className="page-header">
        <h1>nippo</h1>
        <DateNav date={date} onChange={setDate} />
      </header>

      {error && (
        <div className="error-banner" role="alert">
          {error}
          <button type="button" onClick={() => setError(null)}>
            閉じる
          </button>
        </div>
      )}

      {/* スクロールせずに使えるよう、日報(メイン)と当日の記録(サイドバー)を横に並べる */}
      <div className="page-body">
        <ReportPanel date={date} onError={setError} onReload={() => loadActivities(date)}>
          <MemoInput date={date} onAdded={handleAdded} onError={setError} />
        </ReportPanel>
        <Sidebar
          date={date}
          activities={activities}
          onDeleted={handleDeleted}
          onImported={() => loadActivities(date)}
          onError={setError}
        />
      </div>
    </div>
  )
}
