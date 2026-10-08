import { addDays, todayKey } from '../dateUtils'

interface Props {
  date: string
  onChange: (date: string) => void
}

// 日付選択 + 前日/翌日/今日 ボタン
export function DateNav({ date, onChange }: Props) {
  return (
    <div className="date-nav">
      <button type="button" onClick={() => onChange(addDays(date, -1))}>
        前日
      </button>
      <input
        type="date"
        value={date}
        onChange={(e) => e.target.value && onChange(e.target.value)}
      />
      <button type="button" onClick={() => onChange(addDays(date, 1))}>
        翌日
      </button>
      <button type="button" onClick={() => onChange(todayKey())}>
        今日
      </button>
    </div>
  )
}
