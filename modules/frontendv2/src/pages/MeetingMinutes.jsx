import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { FileText, Calendar, Users, Sparkles, Download, Loader2 } from 'lucide-react'
import Card, { CardHeader, CardTitle, CardContent } from '../components/Card'
import Button from '../components/Button'
import { audioService } from '../services/audioService'
import toast from 'react-hot-toast'
import { useAuthStore } from '../stores/authStore'

export default function MeetingMinutes() {
  const publicAccount = useAuthStore((state) => state.user?.registration_source === 'public')
  const [transcriptions, setTranscriptions] = useState([])
  const [selectedTranscription, setSelectedTranscription] = useState('')
  const [meetingData, setMeetingData] = useState({
    title: '',
    date: new Date().toISOString().split('T')[0],
    participants: '',
  })
  const [generatedMinutes, setGeneratedMinutes] = useState(null)
  const [loading, setLoading] = useState(false)
  const [loadingTranscriptions, setLoadingTranscriptions] = useState(true)
  const [geminiAvailable, setGeminiAvailable] = useState(false)

  const checkGeminiStatus = useCallback(async () => {
    try {
      const status = await audioService.getMeetingMinutesStatus()
      setGeminiAvailable(status.available)
      if (!status.available) {
        toast.error(
          publicAccount ? 'Providers externos exigirão sua própria credencial. BYOK ainda não disponível.' : 'Gemini indisponível. Solicite ao administrador a configuração do worker.',
          { duration: 6000 }
        )
      }
    } catch (error) {
      console.error('Erro ao verificar status do Gemini:', error)
      setGeminiAvailable(false)
    }
  }, [publicAccount])

  useEffect(() => {
    loadTranscriptions()
    checkGeminiStatus()
  }, [checkGeminiStatus])

  const loadTranscriptions = async () => {
    try {
      setLoadingTranscriptions(true)
      const data = await audioService.listTranscriptions()
      setTranscriptions((data.transcriptions || []).filter(item => item.status === 'completed'))
    } catch (error) {
      console.error('Erro ao carregar transcrições:', error)
      toast.error('Erro ao carregar transcrições')
    } finally {
      setLoadingTranscriptions(false)
    }
  }

  const handleGenerate = async () => {
    if (!selectedTranscription) {
      toast.error('Selecione uma transcrição')
      return
    }

    if (!meetingData.title.trim()) {
      toast.error('Digite o título da reunião')
      return
    }

    if (!geminiAvailable) {
      toast.error('Solicite ao administrador a configuração do Gemini no worker')
      return
    }

    try {
      setLoading(true)
      setGeneratedMinutes(null)

      const result = await audioService.generateMeetingMinutes(
        selectedTranscription,
        {
          title: meetingData.title,
          date: meetingData.date,
          participants: meetingData.participants.split(',').map(p => p.trim()).filter(Boolean),
        }
      )

      setGeneratedMinutes(result.minutes)
      toast.success('✨ Ata gerada com sucesso!')
    } catch (error) {
      console.error('Erro ao gerar ata:', error)
      const errorMsg = error.response?.data?.detail || error.message
      
      if (errorMsg.includes('API_KEY_INVALID') || errorMsg.includes('401')) {
        toast.error(
          'Gemini indisponível. Solicite ao administrador a verificação do worker.',
          { duration: 6000 }
        )
      } else if (errorMsg.includes('SAFETY')) {
        toast.error(
          'Conteúdo bloqueado por segurança. Tente com outra transcrição.',
          { duration: 6000 }
        )
      } else {
        toast.error(`Erro ao gerar ata: ${errorMsg}`)
      }
    } finally {
      setLoading(false)
    }
  }

  const handleExportMarkdown = () => {
    if (!generatedMinutes) return

    const markdown = generateMarkdown(generatedMinutes, meetingData)
    const blob = new Blob([markdown], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `ata_${meetingData.title.replace(/\s+/g, '_')}_${meetingData.date}.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    toast.success('Ata exportada em Markdown!')
  }

  const handleExportText = () => {
    if (!generatedMinutes) return

    const text = generatePlainText(generatedMinutes, meetingData)
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `ata_${meetingData.title.replace(/\s+/g, '_')}_${meetingData.date}.txt`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    toast.success('Ata exportada em texto!')
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-2">
          <Sparkles className="w-8 h-8 text-yellow-500" />
          Geração de Atas de Reunião
        </h1>
        <p className="text-gray-600 mt-1">
          Gerador legado: o resultado é temporário e não utiliza a revisão de tarefas.
        </p>
        <Link to="/meetings" className="text-primary-700 underline">Use Reuniões para análise persistente, tarefas revisadas e ata consolidada.</Link>
      </div>

      {/* Status do Gemini */}
      {!geminiAvailable && (
        <Card className="border-yellow-300 bg-yellow-50">
          <CardContent className="py-4">
            <div className="flex items-start gap-3">
              <div className="text-yellow-600 mt-1">⚠️</div>
              <div className="flex-1">
                <h3 className="font-semibold text-yellow-900 mb-1">
                  Gemini indisponível
                </h3>
                <p className="text-sm text-yellow-800">
                  Solicite ao administrador a configuração do Gemini no worker para usar este recurso.
                </p>
                <a
                  href="/settings"
                  className="text-sm font-medium text-yellow-900 hover:underline mt-2 inline-block"
                >
                  Ir para Configurações →
                </a>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Formulário de Entrada */}
        <Card>
          <CardHeader>
            <CardTitle>📝 Informações da Reunião</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Seleção de Transcrição */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                <FileText className="w-4 h-4 inline mr-1" />
                Transcrição
              </label>
              {loadingTranscriptions ? (
                <div className="flex items-center gap-2 text-gray-500">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Carregando transcrições...
                </div>
              ) : (
                <select
                  value={selectedTranscription}
                  onChange={(e) => setSelectedTranscription(e.target.value)}
                  className="input"
                  disabled={transcriptions.length === 0}
                >
                  <option value="">Selecione uma transcrição</option>
                  {transcriptions.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.filename} - {new Date(t.created_at).toLocaleDateString()}
                    </option>
                  ))}
                </select>
              )}
              {transcriptions.length === 0 && !loadingTranscriptions && (
                <p className="text-xs text-gray-500 mt-1">
                  Nenhuma transcrição disponível. Faça uma nova transcrição primeiro.
                </p>
              )}
            </div>

            {/* Título */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Título da Reunião *
              </label>
              <input
                type="text"
                value={meetingData.title}
                onChange={(e) => setMeetingData({ ...meetingData, title: e.target.value })}
                className="input"
                placeholder="Ex: Reunião de Planejamento Q1 2024"
              />
            </div>

            {/* Data */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                <Calendar className="w-4 h-4 inline mr-1" />
                Data
              </label>
              <input
                type="date"
                value={meetingData.date}
                onChange={(e) => setMeetingData({ ...meetingData, date: e.target.value })}
                className="input"
              />
            </div>

            {/* Participantes */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                <Users className="w-4 h-4 inline mr-1" />
                Participantes (separados por vírgula)
              </label>
              <textarea
                value={meetingData.participants}
                onChange={(e) => setMeetingData({ ...meetingData, participants: e.target.value })}
                className="input min-h-[80px]"
                placeholder="João Silva, Maria Santos, Pedro Costa"
              />
            </div>

            {/* Botão Gerar */}
            <Button
              onClick={handleGenerate}
              loading={loading}
              disabled={!selectedTranscription || !meetingData.title.trim() || !geminiAvailable}
              icon={Sparkles}
              className="w-full"
            >
              {loading ? 'Gerando Ata...' : 'Gerar Ata com IA'}
            </Button>

            {loading && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                <p className="text-sm text-blue-800 flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Processando com Gemini AI... Isso pode levar alguns segundos.
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Preview da Ata Gerada */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>✨ Ata Gerada</CardTitle>
              {generatedMinutes && (
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleExportMarkdown}
                    icon={Download}
                  >
                    MD
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleExportText}
                    icon={Download}
                  >
                    TXT
                  </Button>
                </div>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {!generatedMinutes ? (
              <div className="text-center py-12 text-gray-500">
                <Sparkles className="w-16 h-16 mx-auto mb-4 text-gray-300" />
                <p>A ata aparecerá aqui após a geração</p>
              </div>
            ) : (
              <div className="space-y-6 max-h-[600px] overflow-y-auto pr-2">
                {/* Resumo */}
                <Section title="📋 Resumo" content={generatedMinutes.summary} />

                {/* Objetivos */}
                {generatedMinutes.objectives && generatedMinutes.objectives.length > 0 && (
                  <Section title="🎯 Objetivos">
                    <ul className="list-disc list-inside space-y-1 text-gray-700">
                      {generatedMinutes.objectives.map((obj, i) => (
                        <li key={i}>{obj}</li>
                      ))}
                    </ul>
                  </Section>
                )}

                {/* Tópicos Discutidos */}
                {generatedMinutes.topics && generatedMinutes.topics.length > 0 && (
                  <Section title="💬 Tópicos Discutidos">
                    <ul className="list-disc list-inside space-y-2 text-gray-700">
                      {generatedMinutes.topics.map((topic, i) => (
                        <li key={i} className="leading-relaxed">{topic}</li>
                      ))}
                    </ul>
                  </Section>
                )}

                {/* Decisões */}
                {generatedMinutes.decisions && generatedMinutes.decisions.length > 0 && (
                  <Section title="✅ Decisões Tomadas">
                    <div className="space-y-3">
                      {generatedMinutes.decisions.map((decision, i) => (
                        <div key={i} className="bg-green-50 border border-green-200 rounded-lg p-3">
                          <p className="font-medium text-green-900">{decision.decision}</p>
                          {decision.responsible && (
                            <p className="text-sm text-green-700 mt-1">
                              👤 Responsável: {decision.responsible}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  </Section>
                )}

                {/* Lista de Tarefas */}
                {generatedMinutes.todo_list && generatedMinutes.todo_list.length > 0 && (
                  <Section title="✏️ Lista de Tarefas (To-Do)">
                    <div className="space-y-3">
                      {generatedMinutes.todo_list.map((todo, i) => (
                        <div key={i} className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                          <p className="font-medium text-blue-900">{todo.task}</p>
                          <div className="flex gap-4 mt-2 text-sm text-blue-700">
                            {todo.responsible && (
                              <span>👤 {todo.responsible}</span>
                            )}
                            {todo.deadline && (
                              <span>📅 {todo.deadline}</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </Section>
                )}

                {/* Próximos Passos */}
                {generatedMinutes.next_steps && generatedMinutes.next_steps.length > 0 && (
                  <Section title="➡️ Próximos Passos">
                    <ul className="list-disc list-inside space-y-1 text-gray-700">
                      {generatedMinutes.next_steps.map((step, i) => (
                        <li key={i}>{step}</li>
                      ))}
                    </ul>
                  </Section>
                )}

                {/* Observações */}
                {generatedMinutes.notes && (
                  <Section title="📝 Observações" content={generatedMinutes.notes} />
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function Section({ title, content, children }) {
  return (
    <div className="border-b border-gray-200 pb-4 last:border-0">
      <h3 className="font-semibold text-gray-900 mb-2">{title}</h3>
      {content && <p className="text-gray-700 leading-relaxed">{content}</p>}
      {children}
    </div>
  )
}

function generateMarkdown(minutes, meetingData) {
  let md = `# Ata de Reunião: ${meetingData.title}\n\n`
  md += `**Data:** ${new Date(meetingData.date).toLocaleDateString('pt-BR')}\n\n`
  
  if (meetingData.participants) {
    md += `**Participantes:** ${meetingData.participants}\n\n`
  }

  md += `---\n\n`
  
  if (minutes.summary) {
    md += `## 📋 Resumo\n\n${minutes.summary}\n\n`
  }

  if (minutes.objectives && minutes.objectives.length > 0) {
    md += `## 🎯 Objetivos\n\n`
    minutes.objectives.forEach(obj => {
      md += `- ${obj}\n`
    })
    md += `\n`
  }

  if (minutes.topics && minutes.topics.length > 0) {
    md += `## 💬 Tópicos Discutidos\n\n`
    minutes.topics.forEach(topic => {
      md += `- ${topic}\n`
    })
    md += `\n`
  }

  if (minutes.decisions && minutes.decisions.length > 0) {
    md += `## ✅ Decisões Tomadas\n\n`
    minutes.decisions.forEach(dec => {
      md += `- **${dec.decision}**\n`
      if (dec.responsible) {
        md += `  - Responsável: ${dec.responsible}\n`
      }
    })
    md += `\n`
  }

  if (minutes.todo_list && minutes.todo_list.length > 0) {
    md += `## ✏️ Lista de Tarefas\n\n`
    minutes.todo_list.forEach(todo => {
      md += `- [ ] **${todo.task}**\n`
      if (todo.responsible || todo.deadline) {
        md += `  - `
        if (todo.responsible) md += `Responsável: ${todo.responsible}`
        if (todo.responsible && todo.deadline) md += ` | `
        if (todo.deadline) md += `Prazo: ${todo.deadline}`
        md += `\n`
      }
    })
    md += `\n`
  }

  if (minutes.next_steps && minutes.next_steps.length > 0) {
    md += `## ➡️ Próximos Passos\n\n`
    minutes.next_steps.forEach(step => {
      md += `- ${step}\n`
    })
    md += `\n`
  }

  if (minutes.notes) {
    md += `## 📝 Observações\n\n${minutes.notes}\n\n`
  }

  md += `---\n\n`
  md += `*Ata gerada automaticamente com IA (Google Gemini)*\n`

  return md
}

function generatePlainText(minutes, meetingData) {
  let text = `ATA DE REUNIÃO: ${meetingData.title.toUpperCase()}\n\n`
  text += `Data: ${new Date(meetingData.date).toLocaleDateString('pt-BR')}\n\n`
  
  if (meetingData.participants) {
    text += `Participantes: ${meetingData.participants}\n\n`
  }

  text += `${'='.repeat(60)}\n\n`
  
  if (minutes.summary) {
    text += `RESUMO\n\n${minutes.summary}\n\n`
  }

  if (minutes.objectives && minutes.objectives.length > 0) {
    text += `OBJETIVOS\n\n`
    minutes.objectives.forEach((obj, i) => {
      text += `${i + 1}. ${obj}\n`
    })
    text += `\n`
  }

  if (minutes.topics && minutes.topics.length > 0) {
    text += `TÓPICOS DISCUTIDOS\n\n`
    minutes.topics.forEach((topic, i) => {
      text += `${i + 1}. ${topic}\n`
    })
    text += `\n`
  }

  if (minutes.decisions && minutes.decisions.length > 0) {
    text += `DECISÕES TOMADAS\n\n`
    minutes.decisions.forEach((dec, i) => {
      text += `${i + 1}. ${dec.decision}\n`
      if (dec.responsible) {
        text += `   Responsável: ${dec.responsible}\n`
      }
    })
    text += `\n`
  }

  if (minutes.todo_list && minutes.todo_list.length > 0) {
    text += `LISTA DE TAREFAS\n\n`
    minutes.todo_list.forEach((todo, i) => {
      text += `${i + 1}. ${todo.task}\n`
      if (todo.responsible) text += `   Responsável: ${todo.responsible}\n`
      if (todo.deadline) text += `   Prazo: ${todo.deadline}\n`
    })
    text += `\n`
  }

  if (minutes.next_steps && minutes.next_steps.length > 0) {
    text += `PRÓXIMOS PASSOS\n\n`
    minutes.next_steps.forEach((step, i) => {
      text += `${i + 1}. ${step}\n`
    })
    text += `\n`
  }

  if (minutes.notes) {
    text += `OBSERVAÇÕES\n\n${minutes.notes}\n\n`
  }

  text += `${'='.repeat(60)}\n\n`
  text += `Ata gerada automaticamente com IA (Google Gemini)\n`

  return text
}
