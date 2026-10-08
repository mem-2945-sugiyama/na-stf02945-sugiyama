import { useEffect, useRef, useState } from 'react'
import { type Activity } from '../api'
import { toDateKey } from '../dateUtils'

interface Props {
  date: string
  events: Activity[]
  onDelete: (activity: Activity) => void
}

const HOUR_HEIGHT = 40 // 1時間あたりの高さ(px)
const DEFAULT_START_HOUR = 8
const DEFAULT_END_HOUR = 20
// 終了時刻が無い予定や極端に短い予定も、件名が読める高さで表示するための最小の長さ
const MIN_EVENT_MINUTES = 30
const DEFAULT_EVENT_MINUTES = 30
// この長さ以下の予定は Google カレンダーと同じく1行(件名、開始時刻)で表示する
const COMPACT_EVENT_MINUTES = 30

interface PlacedEvent {
  activity: Activity
  startMin: number
  endMin: number
  column: number
  columns: number
}

function minutesOfDay(iso: string): number {
  const d = new Date(iso)
  return d.getHours() * 60 + d.getMinutes()
}

// Google カレンダーと同じ「午前9:30」「午後1時」の表記にする
function formatJa(totalMinutes: number): string {
  const h = Math.floor(totalMinutes / 60) % 24
  const m = totalMinutes % 60
  const period = h < 12 ? '午前' : '午後'
  const h12 = h % 12 === 0 ? 12 : h % 12
  return m === 0 ? `${period}${h12}時` : `${period}${h12}:${String(m).padStart(2, '0')}`
}

function formatRange(startMin: number, endMin: number): string {
  const start = formatJa(startMin)
  const end = formatJa(endMin)
  // 「午後1時〜午後2時」は冗長なので、午前・午後が同じなら終了側を省く
  return start.slice(0, 2) === end.slice(0, 2) ? `${start}〜${end.slice(2)}` : `${start}〜${end}`
}

// 時間が重なる予定を横に並べるため、重なりのまとまりごとに列を割り当てる
function placeEvents(events: Activity[]): PlacedEvent[] {
  const items = events
    .map((activity) => {
      const startMin = minutesOfDay(activity.started_at)
      const rawEnd = activity.ended_at
        ? minutesOfDay(activity.ended_at)
        : startMin + DEFAULT_EVENT_MINUTES
      // 日をまたぐ予定(終了が翌日)はその日の終わりまでとして描く
      const endMin = rawEnd > startMin ? rawEnd : 24 * 60
      return { activity, startMin, endMin, column: 0, columns: 1 }
    })
    .sort((a, b) => a.startMin - b.startMin || b.endMin - a.endMin)

  let cluster: PlacedEvent[] = []
  let clusterEnd = -1
  const columnEnds: number[] = []
  const flush = () => {
    const columns = Math.max(1, ...cluster.map((e) => e.column + 1))
    cluster.forEach((e) => (e.columns = columns))
    cluster = []
    columnEnds.length = 0
  }
  for (const item of items) {
    if (item.startMin >= clusterEnd && cluster.length > 0) flush()
    const free = columnEnds.findIndex((end) => end <= item.startMin)
    item.column = free === -1 ? columnEnds.length : free
    columnEnds[item.column] = Math.max(item.endMin, item.startMin + MIN_EVENT_MINUTES)
    cluster.push(item)
    clusterEnd = Math.max(clusterEnd, item.endMin, item.startMin + MIN_EVENT_MINUTES)
  }
  if (cluster.length > 0) flush()
  return items
}

// サイドバー用の1日分のカレンダー表示(Google カレンダーの日表示に寄せた見た目)
export function DaySchedule({ date, events, onDelete }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const placed = placeEvents(events)

  // 予定が範囲外(早朝・深夜)にあっても表示できるよう、既定の範囲を予定に合わせて広げる
  const startHour = Math.min(
    DEFAULT_START_HOUR,
    ...placed.map((e) => Math.floor(e.startMin / 60)),
  )
  const endHour = Math.max(DEFAULT_END_HOUR, ...placed.map((e) => Math.ceil(e.endMin / 60)))
  const hours = Array.from({ length: endHour - startHour }, (_, i) => startHour + i)
  const top = (min: number) => ((min - startHour * 60) / 60) * HOUR_HEIGHT

  // 現在時刻の線を動かすため、1分ごとに現在時刻を更新する
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60_000)
    return () => clearInterval(timer)
  }, [])
  const isToday = date === toDateKey(now)
  const nowMin = now.getHours() * 60 + now.getMinutes()
  const firstStart = placed[0]?.startMin

  // 最初の予定(なければ現在時刻)が見える位置までスクロールする。
  // 現在時刻は依存に含めない: 1分ごとの更新でスクロール位置が勝手に戻らないようにするため
  useEffect(() => {
    const current = new Date()
    const target = firstStart ?? (isToday ? current.getHours() * 60 + current.getMinutes() : null)
    if (scrollRef.current && target != null) {
      const offset = ((target - startHour * 60) / 60) * HOUR_HEIGHT
      scrollRef.current.scrollTop = Math.max(0, offset - HOUR_HEIGHT / 2)
    }
  }, [date, firstStart, isToday, startHour])

  return (
    <div className="day-schedule" ref={scrollRef}>
      <div className="day-grid" style={{ height: hours.length * HOUR_HEIGHT }}>
        {hours.map((h) => (
          <div key={h} className="hour-row" style={{ top: top(h * 60), height: HOUR_HEIGHT }}>
            <span className="hour-label">{formatJa(h * 60)}</span>
          </div>
        ))}

        <div className="event-layer">
          {placed.map((e) => {
            const height =
              (Math.max(e.endMin - e.startMin, MIN_EVENT_MINUTES) / 60) * HOUR_HEIGHT - 2
            const compact = e.endMin - e.startMin <= COMPACT_EVENT_MINUTES
            return (
              <div
                key={e.activity.id}
                className={`event-block${compact ? ' is-compact' : ''}`}
                style={{
                  top: top(e.startMin),
                  height,
                  left: `${(e.column / e.columns) * 100}%`,
                  width: `calc(${100 / e.columns}% - 2px)`,
                }}
                title={`${e.activity.title}\n${formatRange(e.startMin, e.endMin)}`}
              >
                {compact ? (
                  <span className="event-title">
                    {e.activity.title}、{formatJa(e.startMin)}
                  </span>
                ) : (
                  <>
                    <span className="event-title">{e.activity.title}</span>
                    <span className="event-time">{formatRange(e.startMin, e.endMin)}</span>
                  </>
                )}
                <button
                  type="button"
                  className="event-delete"
                  onClick={() => onDelete(e.activity)}
                  aria-label={`「${e.activity.title}」を削除`}
                  title="削除"
                >
                  ×
                </button>
              </div>
            )
          })}

          {isToday && nowMin >= startHour * 60 && nowMin <= endHour * 60 && (
            <div className="now-line" style={{ top: top(nowMin) }} />
          )}
        </div>
      </div>
    </div>
  )
}
