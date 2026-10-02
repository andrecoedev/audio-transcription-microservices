import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { 
  Activity, 
  FileAudio, 
  Clock, 
  CheckCircle2, 
  XCircle,
  Users,
  Zap
} from 'lucide-react'
import Card, { CardHeader, CardTitle, CardContent } from '../components/Card'
import Button from '../components/Button'
import { audioService } from '../services/audioService'
import toast from 'react-hot-toast'

export default function Dashboard() {
  const [health, setHealth] = useState(null)
  const [stats, setStats] = useState(null)
  const [recentTranscriptions, setRecentTranscriptions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    loadDashboardData()
  }, [])

  const loadDashboardData = async () => {
    try {
      setLoading(true)
      setError(false)
      
      // Carregar dados em paralelo
      const [healthData, statsData, transcriptionsData] = await Promise.all([
        audioService.checkHealth(),
        audioService.getStats(),
        audioService.listTranscriptions({ limit: 5 })
      ])

      setHealth(healthData)
      setStats(statsData)
      setRecentTranscriptions(transcriptionsData.transcriptions || [])
    } catch {
      setError(true)
      toast.error('Erro ao carregar dados do dashboard')
    } finally {
      setLoading(false)
    }
  }

  const getStatusBadge = (status) => {
    const badges = {
      queued: { text: 'Na fila', class: 'badge-warning' },
      completed: { text: 'Concluída', class: 'badge-success' },
      processing: { text: 'Processando', class: 'badge-warning' },
      failed: { text: 'Falhou', class: 'badge-error' },
    }
    const badge = badges[status] || badges.processing
    return <span className={`badge ${badge.class}`}>{badge.text}</span>
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Carregando dashboard...</p>
        </div>
      </div>
    )
  }

  if (error) return <div className="space-y-3">
    <p role="alert">Não foi possível carregar o dashboard.</p>
    <Button onClick={loadDashboardData}>Tentar novamente</Button>
  </div>

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-gray-600 mt-1">Visão geral do sistema de transcrição</p>
        </div>
        <Link to="/new-transcription">
          <Button icon={FileAudio}>Nova Transcrição</Button>
        </Link>
      </div>

      {/* Status dos Modelos */}
      <Card>
        <CardHeader>
          <CardTitle>🧠 Configuração dos Providers</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <ModelStatusCard
              name="Detecção de falantes"
              icon={Users}
              configured={health?.models?.diarization?.configured}
              device={health?.models?.diarization?.device}
            />
            <ModelStatusCard
              name="Faster-Whisper (Local)"
              icon={Zap}
              configured={health?.models?.whisper?.configured}
              device={health?.models?.whisper?.device}
            />
            <ModelStatusCard
              name="AssemblyAI (Cloud)"
              icon={Activity}
              configured={health?.models?.assemblyai?.configured}
              device={health?.models?.assemblyai?.device}
            />
          </div>
          <p className="mt-3 text-xs text-gray-500">Configuração não comprova carregamento dos modelos ou disponibilidade das APIs externas.</p>
        </CardContent>
      </Card>

      {/* Estatísticas */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          icon={FileAudio}
          label="Total de Transcrições"
          value={stats?.total_transcriptions || 0}
          color="blue"
        />
        <StatCard
          icon={CheckCircle2}
          label="Concluídas"
          value={stats?.completed || 0}
          color="green"
        />
        <StatCard
          icon={Clock}
          label="Em Processamento"
          value={stats?.processing || 0}
          color="yellow"
        />
        <StatCard
          icon={XCircle}
          label="Falharam"
          value={stats?.failed || 0}
          color="red"
        />
      </div>

      {/* Transcrições Recentes */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>📋 Transcrições Recentes</CardTitle>
            <Link to="/transcriptions">
              <Button variant="ghost" size="sm">Ver Todas</Button>
            </Link>
          </div>
        </CardHeader>
        <CardContent>
          {recentTranscriptions.length === 0 ? (
            <div className="text-center py-12">
              <FileAudio className="w-12 h-12 text-gray-400 mx-auto mb-3" />
              <p className="text-gray-600">Nenhuma transcrição ainda</p>
              <Link to="/new-transcription">
                <Button variant="primary" size="sm" className="mt-4">
                  Criar Primeira Transcrição
                </Button>
              </Link>
            </div>
          ) : (
            <div className="space-y-3">
              {recentTranscriptions.map((transcription) => (
                <Link
                  key={transcription.id}
                  to={`/transcriptions/${transcription.id}`}
                  className="block p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3">
                        <FileAudio className="w-5 h-5 text-primary-600" />
                        <div>
                          <p className="font-medium text-gray-900">
                            {transcription.filename}
                          </p>
                          <p className="text-sm text-gray-500">
                            {new Date(transcription.created_at).toLocaleString('pt-BR')}
                          </p>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="text-right text-sm">
                        <p className="text-gray-600">
                          {transcription.duration_seconds?.toFixed(1)}s
                        </p>
                        <p className="text-gray-500">
                          {transcription.word_count || 0} palavras
                        </p>
                      </div>
                      {getStatusBadge(transcription.status)}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function StatCard({ icon: Icon, label, value, color }) {
  const colors = {
    blue: 'bg-blue-500',
    green: 'bg-green-500',
    yellow: 'bg-yellow-500',
    red: 'bg-red-500',
  }

  return (
    <Card>
      <div className="flex items-center gap-4">
        <div className={`p-3 rounded-lg ${colors[color]}`}>
          <Icon className="w-6 h-6 text-white" />
        </div>
        <div>
          <p className="text-sm text-gray-600">{label}</p>
          <p className="text-2xl font-bold text-gray-900">{value}</p>
        </div>
      </div>
    </Card>
  )
}

function ModelStatusCard({ name, icon: Icon, configured, device }) {
  return (
    <div className="flex items-center gap-3 p-3 border border-gray-200 rounded-lg">
      <div className={`p-2 rounded-lg ${configured ? 'bg-green-100' : 'bg-red-100'}`}>
        <Icon className={`w-5 h-5 ${configured ? 'text-green-600' : 'text-red-600'}`} />
      </div>
      <div className="flex-1">
        <p className="font-medium text-gray-900 text-sm">{name}</p>
        <p className="text-xs text-gray-500">
          {configured ? device || 'Configurado' : 'Não configurado'}
        </p>
      </div>
      <div className={`w-2 h-2 rounded-full ${configured ? 'bg-green-500' : 'bg-red-500'}`} />
    </div>
  )
}
