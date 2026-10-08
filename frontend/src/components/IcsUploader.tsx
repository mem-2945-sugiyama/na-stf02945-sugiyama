import { useRef, useState } from 'react'
import { importIcs } from '../api'

interface Props {
  date: string
  onImported: () => void
  onError: (message: string) => void
}

// .ics ファイルを選択してアップロードし、取り込み件数を表示したあと一覧を再読込する
export function IcsUploader({ date, onImported, onError }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [resultCount, setResultCount] = useState<number | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  async function handleUpload() {
    if (!file || uploading) return
    setUploading(true)
    setResultCount(null)
    try {
      const result = await importIcs(date, file)
      setResultCount(result.imported)
      setFile(null)
      if (inputRef.current) inputRef.current.value = ''
      onImported()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'カレンダーファイルの取り込みに失敗しました')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="ics-uploader">
      <input
        ref={inputRef}
        type="file"
        accept=".ics,.zip"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      <button type="button" onClick={handleUpload} disabled={!file || uploading}>
        {uploading ? 'アップロード中...' : 'カレンダーを取り込む'}
      </button>
      {resultCount !== null && <span className="import-result">{resultCount} 件取り込みました</span>}
    </div>
  )
}
