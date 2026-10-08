// バックエンド(FastAPI)の API 契約に対応する型と fetch ラッパー。
// 本番は S3+CloudFront から同一オリジンの /api を叩くため、ベース URL は固定でよい。
const API_BASE = '/api'

export type Category = 'work' | 'meeting' | 'tech_learning' | 'business_learning'
export type Source = 'manual' | 'claude' | 'calendar' | 'slack'

export const CATEGORY_LABELS: Record<Category, string> = {
  work: '作業',
  meeting: '会議',
  tech_learning: '技術の学び',
  business_learning: 'ビジネスの学び',
}

export interface Activity {
  id: number
  date: string
  started_at: string
  ended_at: string | null
  category: Category
  project: string | null
  title: string
  detail: string | null
  source: Source
  external_id: string | null
  created_at: string
}

export interface CreateActivityInput {
  date: string
  category: Category
  title: string
  project?: string
  detail?: string
}

export interface ReportDraft {
  date: string
  body: string
}

export interface Report {
  date: string
  body: string
  comment: string
  updated_at: string
}

export interface ImportResult {
  imported: number
}

// API が返すエラーメッセージを拾えないケースもあるため、ステータスコードを添えて
// 画面上部のエラー表示にそのまま使える日本語文言を組み立てる。
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers:
      init?.body && !(init.body instanceof FormData)
        ? { 'Content-Type': 'application/json', ...init.headers }
        : init?.headers,
  })

  if (res.status === 204) {
    return undefined as T
  }

  if (!res.ok) {
    let detail = ''
    try {
      const data = await res.json()
      detail = typeof data?.detail === 'string' ? data.detail : JSON.stringify(data?.detail ?? '')
    } catch {
      // レスポンスが JSON でない場合は無視し、ステータスのみ伝える
    }
    throw new ApiError(res.status, detail || `リクエストに失敗しました(${res.status})`)
  }

  return (await res.json()) as T
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export function fetchActivities(date: string): Promise<Activity[]> {
  return request<Activity[]>(`/activities?date=${encodeURIComponent(date)}`)
}

export function createActivity(input: CreateActivityInput): Promise<Activity> {
  return request<Activity>('/activities', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function deleteActivity(id: number): Promise<void> {
  return request<void>(`/activities/${id}`, { method: 'DELETE' })
}

export function importIcs(date: string, file: File): Promise<ImportResult> {
  const formData = new FormData()
  formData.append('file', file)
  return request<ImportResult>(`/imports/ics?date=${encodeURIComponent(date)}`, {
    method: 'POST',
    body: formData,
  })
}

export interface BulkResult {
  created: number
  updated: number
}

// Slack の検索結果などを貼り付けたテキストを、そのまま1件の活動として登録する。
// 整形は日報作成時に AI が行うため、ここでは手を加えない
export function importSlackText(date: string, text: string): Promise<BulkResult> {
  return request<BulkResult>('/activities/bulk', {
    method: 'POST',
    body: JSON.stringify([
      {
        date,
        category: 'work',
        title: 'Slack の投稿(貼り付け)',
        detail: text,
        started_at: new Date().toISOString(),
        source: 'slack',
        // 貼り付けは1日に複数回あり得るため、毎回別の活動として登録する
        external_id: `paste-${crypto.randomUUID()}`,
      },
    ]),
  })
}

export function fetchReportDraft(date: string, comment: string): Promise<ReportDraft> {
  return request<ReportDraft>(
    `/reports/${date}/draft?comment=${encodeURIComponent(comment)}`,
  )
}

// 日報が未保存の場合バックエンドは 404 を返す契約のため、ここで null に正規化して
// 呼び出し側(DayPage)が「未保存=空欄」として扱えるようにする。
export async function fetchReport(date: string): Promise<Report | null> {
  try {
    return await request<Report>(`/reports/${date}`)
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) {
      return null
    }
    throw e
  }
}

// 本文には触れず今日の一言だけを保存する(AI 自動作成の前に一言を API へ届けるため)
export function saveComment(date: string, comment: string): Promise<Report> {
  return request<Report>(`/reports/${date}`, {
    method: 'PUT',
    body: JSON.stringify({ comment }),
  })
}

export function saveReport(date: string, body: string, comment: string): Promise<Report> {
  return request<Report>(`/reports/${date}`, {
    method: 'PUT',
    body: JSON.stringify({ body, comment }),
  })
}

// --- AI(Mac 上の importer/ai_server.py) ---

export interface AiResult {
  body: string
}

// AI サーバーが返すエラー。生成までは成功して保存に失敗した場合は unsavedBody に本文が入る
export class AiError extends Error {
  unsavedBody: string | null
  constructor(message: string, unsavedBody: string | null = null) {
    super(message)
    this.unsavedBody = unsavedBody
  }
}

const AI_SERVER_DOWN =
  'AI サーバーに接続できません。ターミナルで uv run importer/ai_server.py を実行してください'

async function aiRequest(path: string, payload: unknown): Promise<AiResult> {
  let res: Response
  try {
    res = await fetch(`/ai${path}`, {
      method: 'POST',
      // X-Nippo-Client: AI サーバーは、このヘッダーが無いリクエストを他サイトからのものとして拒否する
      headers: { 'Content-Type': 'application/json', 'X-Nippo-Client': 'web' },
      body: JSON.stringify(payload),
    })
  } catch {
    throw new AiError(AI_SERVER_DOWN)
  }
  let data: { body?: string; detail?: string; unsaved_body?: string | null } = {}
  try {
    data = await res.json()
  } catch {
    // AI サーバーが止まっているとき、開発サーバーのプロキシは JSON 以外のエラーを返す
    throw new AiError(AI_SERVER_DOWN)
  }
  if (!res.ok || typeof data.body !== 'string') {
    throw new AiError(data.detail ?? `AI の処理に失敗しました(${res.status})`, data.unsaved_body ?? null)
  }
  return { body: data.body }
}

/** 材料を集めて AI で日報を作成し、保存する(数十秒かかる)。 */
export function aiGenerate(date: string): Promise<AiResult> {
  return aiRequest('/generate', { date })
}

/** 本文を AI で短く書き直す。保存はしないので、呼び出し側で保存すること。 */
export function aiShorten(body: string): Promise<AiResult> {
  return aiRequest('/shorten', { body })
}
