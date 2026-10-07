import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { FileAudio, Search, Trash2 } from 'lucide-react'
import Card, { CardContent } from '../components/Card'
import Button from '../components/Button'
import StatusBadge from '../components/StatusBadge'
import { audioService } from '../services/audioService'
import { formatCount, formatDuration, formatNumber, formatTimestamp, getDisplayFilename } from '../utils/format'
import toast from 'react-hot-toast'

export default function Transcriptions() {
  const [transcriptions, setTranscriptions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [total, setTotal] = useState(0)
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [pagination, setPagination] = useState({ skip: 0, limit: 10 })

  const loadTranscriptions = useCallback(async () => {
    setLoading(true); setError(false)
    try {
      const data = await audioService.listTranscriptions({ ...pagination, status: statusFilter !== 'all' ? statusFilter : undefined })
      setTranscriptions(data.transcriptions || [])
      setTotal(data.total ?? data.transcriptions?.length ?? 0)
    } catch { setError(true) } finally { setLoading(false) }
  }, [pagination, statusFilter])
  useEffect(() => { loadTranscriptions() }, [loadTranscriptions])

  const handleDelete = async (item) => {
    if (!window.confirm(`Tem certeza que deseja excluir “${getDisplayFilename(item)}”?`)) return
    try { await audioService.deleteTranscription(item.id); toast.success('Transcrição excluída'); await loadTranscriptions() } catch { toast.error('Não foi possível excluir a transcrição') }
  }
  const visible = transcriptions.filter((item) => getDisplayFilename(item).toLowerCase().includes(searchTerm.toLowerCase()))

  return <div className="space-y-6">
    <div className="flex flex-wrap items-start justify-between gap-4"><div><h1 className="text-3xl font-bold text-gray-900">Histórico</h1><p className="mt-1 text-gray-600">Acompanhe transcrições e status de processamento.</p></div><Link to="/new-transcription"><Button icon={FileAudio}>Nova transcrição</Button></Link></div>
    <Card className="p-4"><CardContent><div className="flex flex-col gap-3 md:flex-row md:items-center">
      <label className="relative min-w-0 flex-1"><Search aria-hidden="true" className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500"/><span className="sr-only">Buscar transcrições</span><input value={searchTerm} onChange={(event) => setSearchTerm(event.target.value)} placeholder="Buscar por nome do arquivo..." className="w-full rounded-lg border border-gray-300 py-2 pl-10 pr-3"/></label>
      <select aria-label="Filtrar por status" value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPagination((current) => ({ ...current, skip: 0 })) }} className="rounded-lg border border-gray-300 px-3 py-2"><option value="all">Todos os status</option><option value="completed">Concluídas</option><option value="processing">Processando</option><option value="queued">Na fila</option><option value="failed">Falharam</option></select>
    </div></CardContent></Card>
    <Card className="overflow-hidden !p-0"><CardContent>
      {loading ? <p role="status" className="p-8 text-center text-gray-600">Carregando transcrições...</p> : error ? <div className="space-y-3 p-6"><p role="alert">Não foi possível carregar ou atualizar o histórico.</p><Button onClick={loadTranscriptions}>Tentar novamente</Button></div> : visible.length === 0 ? <div className="p-10 text-center"><p className="text-gray-600">{searchTerm || statusFilter !== 'all' ? 'Nenhuma transcrição corresponde aos filtros.' : 'Nenhuma transcrição ainda.'}</p>{!searchTerm && statusFilter === 'all' && <Link className="mt-3 inline-block text-primary-700 hover:underline" to="/new-transcription">Enviar primeiro áudio</Link>}</div> : <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-sm"><thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500"><tr><th className="px-5 py-3">Arquivo</th><th className="px-4 py-3">Data</th><th className="px-4 py-3">Duração</th><th className="px-4 py-3">Palavras</th><th className="px-4 py-3">Status</th><th className="px-4 py-3 text-right">Ações</th></tr></thead><tbody className="divide-y divide-gray-200">{visible.map((item) => <tr key={item.id} className="hover:bg-gray-50"><td className="max-w-sm px-5 py-4"><Link className="block truncate font-medium text-gray-900 hover:underline" to={`/transcriptions/${item.id}`}>{getDisplayFilename(item)}</Link>{item.num_speakers > 0 && <p className="mt-1 text-xs text-gray-500">{formatCount(item.num_speakers, 'falante', 'falantes')}</p>}</td><td className="whitespace-nowrap px-4 py-4 text-gray-600">{formatTimestamp(item.created_at)}</td><td className="whitespace-nowrap px-4 py-4 text-gray-600">{formatDuration(item.duration_seconds)}</td><td className="px-4 py-4 text-gray-600">{formatNumber(item.word_count)}</td><td className="px-4 py-4"><StatusBadge status={item.status} /></td><td className="px-4 py-4 text-right"><div className="inline-flex items-center gap-2"><Link to={`/transcriptions/${item.id}`}><Button size="sm" variant="outline">Abrir</Button></Link><Button size="sm" variant="ghost" aria-label={`Excluir ${getDisplayFilename(item)}`} onClick={() => handleDelete(item)}><Trash2 className="h-4 w-4"/></Button></div></td></tr>)}</tbody></table></div>}
    </CardContent></Card>
    {!error && <div className="flex items-center justify-between gap-3"><Button variant="outline" disabled={loading || pagination.skip === 0} onClick={() => setPagination((current) => ({ ...current, skip: Math.max(0, current.skip - current.limit) }))}>Anterior</Button><p className="text-sm text-gray-600">Página {formatNumber(Math.floor(pagination.skip / pagination.limit) + 1)} · {formatCount(total, 'transcrição', 'transcrições')}</p><Button variant="outline" disabled={loading || pagination.skip + pagination.limit >= total} onClick={() => setPagination((current) => ({ ...current, skip: current.skip + current.limit }))}>Próxima</Button></div>}
  </div>
}
