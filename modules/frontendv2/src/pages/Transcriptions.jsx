import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { 
  Search, 
  Filter, 
  FileAudio, 
  Clock,
  CheckCircle2,
  XCircle,
  Eye,
  Trash2
} from 'lucide-react'
import Card, { CardHeader, CardTitle, CardContent } from '../components/Card'
import Button from '../components/Button'
import { audioService } from '../services/audioService'
import toast from 'react-hot-toast'

export default function Transcriptions() {
  const [transcriptions, setTranscriptions] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [pagination] = useState({ skip: 0, limit: 10 })

  const loadTranscriptions = useCallback(async () => {
    try {
      setLoading(true)
      const params = { 
        ...pagination,
        status: statusFilter !== 'all' ? statusFilter : undefined 
      }
      const data = await audioService.listTranscriptions(params)
      setTranscriptions(data.transcriptions || [])
    } catch (error) {
      toast.error('Erro ao carregar transcrições')
      console.error(error)
    } finally {
      setLoading(false)
    }
  }, [pagination, statusFilter])

  useEffect(() => {
    loadTranscriptions()
  }, [loadTranscriptions])

  const handleDelete = async (id) => {
    if (!confirm('Tem certeza que deseja excluir esta transcrição?')) return

    try {
      await audioService.deleteTranscription(id)
      toast.success('Transcrição excluída com sucesso')
      loadTranscriptions()
    } catch (error) {
      toast.error('Erro ao excluir transcrição')
      console.error(error)
    }
  }

  const getStatusBadge = (status) => {
    const badges = {
      completed: { 
        text: 'Concluída', 
        class: 'badge-success',
        icon: CheckCircle2 
      },
      processing: { 
        text: 'Processando', 
        class: 'badge-warning',
        icon: Clock
      },
      failed: { 
        text: 'Falhou', 
        class: 'badge-error',
        icon: XCircle
      },
    }
    const badge = badges[status] || badges.processing
    const Icon = badge.icon
    return (
      <span className={`badge ${badge.class} flex items-center gap-1`}>
        <Icon className="w-3 h-3" />
        {badge.text}
      </span>
    )
  }

  const filteredTranscriptions = transcriptions.filter(t =>
    t.filename.toLowerCase().includes(searchTerm.toLowerCase())
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Transcrições</h1>
          <p className="text-gray-600 mt-1">Gerencie todas as suas transcrições</p>
        </div>
        <Link to="/new-transcription">
          <Button icon={FileAudio}>Nova Transcrição</Button>
        </Link>
      </div>

      {/* Filtros */}
      <Card>
        <CardContent>
          <div className="flex flex-col md:flex-row gap-4">
            {/* Busca */}
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input
                type="text"
                placeholder="Buscar por nome do arquivo..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>

            {/* Filtro de Status */}
            <div className="flex items-center gap-2">
              <Filter className="w-5 h-5 text-gray-400" />
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              >
                <option value="all">Todos os status</option>
                <option value="completed">Concluídas</option>
                <option value="processing">Processando</option>
                <option value="failed">Falharam</option>
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Lista de Transcrições */}
      <Card>
        <CardHeader>
          <CardTitle>📋 Todas as Transcrições ({filteredTranscriptions.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
              <p className="mt-4 text-gray-600">Carregando transcrições...</p>
            </div>
          ) : filteredTranscriptions.length === 0 ? (
            <div className="text-center py-12">
              <FileAudio className="w-12 h-12 text-gray-400 mx-auto mb-3" />
              <p className="text-gray-600 mb-4">
                {searchTerm ? 'Nenhuma transcrição encontrada' : 'Nenhuma transcrição ainda'}
              </p>
              {!searchTerm && (
                <Link to="/new-transcription">
                  <Button size="sm">Criar Primeira Transcrição</Button>
                </Link>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              {filteredTranscriptions.map((transcription) => (
                <div
                  key={transcription.id}
                  className="p-4 border border-gray-200 rounded-lg hover:shadow-md transition-shadow"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4 flex-1">
                      <div className="p-3 bg-primary-100 rounded-lg">
                        <FileAudio className="w-6 h-6 text-primary-600" />
                      </div>
                      
                      <div className="flex-1">
                        <h3 className="font-medium text-gray-900">{transcription.filename}</h3>
                        <div className="flex items-center gap-4 mt-1 text-sm text-gray-500">
                          <span>📅 {new Date(transcription.created_at).toLocaleDateString('pt-BR')}</span>
                          <span>⏱️ {transcription.duration_seconds?.toFixed(1)}s</span>
                          <span>📝 {transcription.word_count || 0} palavras</span>
                          {transcription.num_speakers && (
                            <span>🗣️ {transcription.num_speakers} falantes</span>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      {getStatusBadge(transcription.status)}
                      
                      <div className="flex items-center gap-2">
                        <Link to={`/transcriptions/${transcription.id}`}>
                          <Button variant="outline" size="sm" icon={Eye}>
                            Ver
                          </Button>
                        </Link>
                        <Button
                          variant="ghost"
                          size="sm"
                          aria-label={`Excluir ${transcription.filename}`}
                          onClick={() => handleDelete(transcription.id)}
                          className="text-red-600 hover:bg-red-50"
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
