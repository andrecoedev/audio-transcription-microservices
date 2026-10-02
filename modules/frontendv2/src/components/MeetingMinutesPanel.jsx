import { useCallback, useEffect, useState } from 'react'
import { Copy, Download } from 'lucide-react'
import toast from 'react-hot-toast'
import Button from './Button'
import Card, { CardContent, CardHeader, CardTitle } from './Card'
import { audioService } from '../services/audioService'

function textValue(value) {
  if (typeof value === 'string') return value
  if (typeof value === 'number') return String(value)
  if (value && typeof value === 'object') return value.decision || value.description || value.question || value.topic || value.text || ''
  return ''
}

function Section({ title, children }) {
  return <section className="space-y-2">
    <h3 className="font-semibold text-gray-900">{title}</h3>
    {children}
  </section>
}

function TextList({ values, empty }) {
  return values?.length
    ? <ul className="list-disc space-y-1 pl-5 text-gray-700">{values.map((value, index) => <li key={index}>{textValue(value)}</li>)}</ul>
    : <p className="text-sm text-gray-500">{empty}</p>
}

export default function MeetingMinutesPanel({ meetingId, version = 0 }) {
  const [minutes, setMinutes] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      setMinutes(await audioService.getMeetingMinutes(meetingId))
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [meetingId])

  useEffect(() => { load() }, [load, version])

  async function getMarkdown() {
    setExporting(true)
    setExportError(false)
    try {
      return await audioService.getMeetingMinutesMarkdown(meetingId)
    } catch {
      setExportError(true)
      return null
    } finally {
      setExporting(false)
    }
  }

  async function download() {
    const markdown = await getMarkdown()
    if (markdown == null) return
    const url = URL.createObjectURL(new Blob([markdown], { type: 'text/markdown;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `meeting-${meetingId}-minutes.md`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  async function copy() {
    try {
      const markdown = await getMarkdown()
      if (markdown == null) return
      await navigator.clipboard.writeText(markdown)
      toast.success('Ata copiada')
    } catch {
      toast.error('Não foi possível copiar a ata neste navegador')
    }
  }

  return <Card><CardHeader className="flex items-center justify-between gap-3 sm:flex-row">
    <CardTitle>Ata da reunião</CardTitle>
    {minutes && <div className="flex gap-2">
      <Button variant="outline" size="sm" icon={Copy} disabled={exporting} onClick={copy}>Copiar</Button>
      <Button variant="outline" size="sm" icon={Download} disabled={exporting} onClick={download}>Baixar Markdown</Button>
    </div>}
  </CardHeader><CardContent>
    {exportError && <p role="alert" className="mb-3 text-red-700">Não foi possível exportar a ata. Tente novamente.</p>}
    {loading ? <p role="status">Carregando ata...</p> : error ? <div className="space-y-2">
      <p role="alert" className="text-red-700">Não foi possível carregar a ata.</p>
      <Button variant="outline" size="sm" onClick={load}>Tentar novamente</Button>
    </div> : <article className="space-y-5">
      <header>
        <h2 className="text-xl font-semibold text-gray-900">{minutes.title}</h2>
        {minutes.created_at && <p className="text-sm text-gray-600">{new Date(minutes.created_at).toLocaleString('pt-BR')}</p>}
        {(minutes.summary || (minutes.topics || []).length || (minutes.decisions || []).length || (minutes.open_questions || []).length) &&
          <p className="mt-2 text-xs text-gray-500">Resumo e demais conteúdos analíticos são gerados por IA; revise antes de utilizar.</p>}
      </header>
      <Section title="Resumo"><p className="whitespace-pre-wrap text-gray-700">{minutes.summary || 'Nenhum resumo disponível.'}</p></Section>
      <Section title="Tópicos"><TextList values={minutes.topics} empty="Nenhum tópico registrado." /></Section>
      <Section title="Decisões"><TextList values={minutes.decisions} empty="Nenhuma decisão registrada." /></Section>
      <Section title="Action Items">
        {minutes.action_items?.length ? <ul className="space-y-2">{minutes.action_items.map(action => <li key={action.id} className="rounded border border-gray-200 p-3">
          <p className={action.status === 'done' ? 'text-gray-500 line-through' : 'text-gray-800'}>{action.description}</p>
          <p className="mt-1 text-sm text-gray-600">{action.status === 'done' ? 'Concluída' : 'Aberta'} · {action.source === 'manual' ? 'Criada manualmente' : 'IA → revisada'}{action.assignee ? ` · ${action.assignee}` : ''}{action.due_date ? ` · ${action.due_date}` : ''}</p>
        </li>)}</ul> : <p className="text-sm text-gray-500">Nenhuma tarefa operacional registrada.</p>}
      </Section>
      <Section title="Perguntas em aberto"><TextList values={minutes.open_questions} empty="Nenhuma pergunta em aberto." /></Section>
    </article>}
  </CardContent></Card>
}
