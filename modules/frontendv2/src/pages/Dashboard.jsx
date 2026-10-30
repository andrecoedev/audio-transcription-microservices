import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { FileAudio } from 'lucide-react'
import StatusBadge from '../components/StatusBadge'
import Button from '../components/Button'
import { audioService } from '../services/audioService'
import { formatDuration, formatTimestamp, getDisplayFilename } from '../utils/format'

export default function Dashboard() {
  const [recentTranscriptions, setRecentTranscriptions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const data = await audioService.listTranscriptions({ limit: 5 })
      setRecentTranscriptions(data.transcriptions || [])
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => { load() }, [load])

  return <section aria-labelledby="recent-activity-title" className="space-y-4">
      <h2 id="recent-activity-title" className="text-base font-semibold text-gray-900">Atividade recente</h2>
        {loading ? <p role="status" className="py-8 text-center text-gray-600">Carregando atividade...</p> : error ? <div className="space-y-3"><p role="alert">Não foi possível carregar as transcrições recentes.</p><Button variant="outline" onClick={load}>Tentar novamente</Button></div> : recentTranscriptions.length === 0 ? <div className="py-10 text-center"><FileAudio className="mx-auto mb-3 h-10 w-10 text-gray-400"/><p className="text-gray-600">Você ainda não tem transcrições.</p><Link className="mt-3 inline-block text-primary-700 hover:underline" to="/new-transcription">Criar a primeira transcrição</Link></div> :
          <ul className="divide-y divide-gray-200 border-y border-gray-200">{recentTranscriptions.map((item) => <li key={item.id}>
            <Link to={`/transcriptions/${item.id}`} className="flex min-w-0 flex-wrap items-center justify-between gap-3 py-4 hover:bg-surface-secondary">
              <div className="min-w-0 flex-1"><p className="break-words font-medium text-gray-900">{getDisplayFilename(item)}</p>
                <p className="mt-1 text-sm text-gray-600">{formatTimestamp(item.created_at)} · {formatDuration(item.duration_seconds)}</p></div>
              <StatusBadge status={item.status} />
            </Link>
          </li>)}</ul>}
  </section>
}
