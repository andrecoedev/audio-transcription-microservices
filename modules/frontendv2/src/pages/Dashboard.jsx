import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { FileAudio } from 'lucide-react'
import Card, { CardContent, CardHeader, CardTitle } from '../components/Card'
import Button from '../components/Button'
import { audioService } from '../services/audioService'
import { formatDuration, formatTimestamp } from '../utils/format'

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

  const labels = { queued: 'Na fila', processing: 'Processando', completed: 'Concluída', failed: 'Falhou' }
  return <div className="space-y-6">
    <Card>
      <CardHeader><CardTitle>Atividade recente</CardTitle></CardHeader>
      <CardContent>
        {loading ? <p role="status" className="py-8 text-center text-gray-600">Carregando atividade...</p> : error ? <div className="space-y-3"><p role="alert">Não foi possível carregar as transcrições recentes.</p><Button variant="outline" onClick={load}>Tentar novamente</Button></div> : recentTranscriptions.length === 0 ? <div className="py-10 text-center"><FileAudio className="mx-auto mb-3 h-10 w-10 text-gray-400"/><p className="text-gray-600">Nenhuma transcrição ainda.</p><Link className="mt-3 inline-block text-primary-700 hover:underline" to="/new-transcription">Enviar seu primeiro áudio</Link></div> :
          <div className="grid min-w-0 grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">{recentTranscriptions.map((item) => <Link key={item.id} to={`/transcriptions/${item.id}`} className="min-w-0 rounded-lg border border-gray-200 p-4 transition-colors hover:bg-gray-50">
            <div className="mb-3 flex items-center justify-between gap-2"><span className={`rounded-full px-2.5 py-1 text-xs font-medium ${item.status === 'completed' ? 'bg-primary-50 text-primary-800' : item.status === 'failed' ? 'bg-red-50 text-red-700' : 'bg-gray-100 text-gray-700'}`}>{labels[item.status] || item.status}</span><span className="text-xs text-gray-500">{formatTimestamp(item.created_at)}</span></div>
            <p className="truncate font-medium text-gray-900">{item.filename}</p><p className="mt-2 text-sm text-gray-600">{formatDuration(item.duration_seconds)}</p>
          </Link>)}</div>}
      </CardContent>
    </Card>
  </div>
}
