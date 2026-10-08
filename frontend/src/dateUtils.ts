// Date.toISOString() は UTC 変換されるため、ローカル日付がずれる(例: JST 深夜に日付が1日戻る)。
// それを避けるため、ローカルの年月日から直接 "YYYY-MM-DD" を組み立てる。
export function toDateKey(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export function todayKey(): string {
  return toDateKey(new Date())
}

// "YYYY-MM-DD" に日数を加算して新しい日付キーを返す(前日/翌日ボタン用)。
export function addDays(dateKey: string, delta: number): string {
  const [y, m, d] = dateKey.split('-').map(Number)
  const date = new Date(y, m - 1, d)
  date.setDate(date.getDate() + delta)
  return toDateKey(date)
}
