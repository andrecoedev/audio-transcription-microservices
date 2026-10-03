import { useEffect, useRef, useState } from 'react'
import Card, { CardContent, CardHeader, CardTitle } from './Card'
import Button from './Button'
import { audioService } from '../services/audioService'

function EvidenceLinks({ evidence, references }) {
  return <div className="text-sm text-gray-500 mt-1">{evidence.map((item, index) => {
    const reference = references.find(ref => ref.segment_order === item.segment_order)
    return <a key={index} href={`#segment-${item.segment_order}`} title={item.quote} className="text-primary-700 underline mr-3">
      {reference ? `${reference.start.toFixed(1)}s–${reference.end.toFixed(1)}s` : `Segmento ${item.segment_order + 1}`}
    </a>
  })}</div>
}

export default function MeetingIntelligencePanel({ meetingId, onResultChange }) {
  const [status, setStatus] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const notifiedRevision = useRef(null)

  useEffect(() => {
    let cancelled = false
    let timer
    async function poll() {
      try {
        const current = await audioService.getMeetingIntelligenceStatus(meetingId)
        const content = current.completed_revision ? await audioService.getMeetingIntelligenceResult(meetingId) : null
        if (cancelled) return
        setStatus(current)
        setResult(content)
        if (content?.revision !== notifiedRevision.current) {
          notifiedRevision.current = content?.revision ?? null
          onResultChange?.(content?.revision ?? null)
        }
        setError('')
        if (['pending', 'processing'].includes(current.generation?.status)) timer = setTimeout(poll, 3000)
      } catch {
        if (!cancelled) setError('Não foi possível consultar a análise da reunião.')
      }
    }
    poll()
    return () => { cancelled = true; clearTimeout(timer) }
  }, [meetingId, refresh, onResultChange])

  async function generate() {
    setSubmitting(true)
    setError('')
    try {
      await audioService.requestMeetingIntelligence(meetingId, Boolean(result))
      setRefresh(value => value + 1)
    } catch (failure) {
      setError(failure.message || 'Não foi possível solicitar a análise.')
    } finally { setSubmitting(false) }
  }

  const state = status?.generation?.status
  const busy = ['pending', 'processing'].includes(state)
  const content = result?.content
  return <Card><CardHeader><CardTitle>Resumo inteligente</CardTitle></CardHeader><CardContent>
    <div className="space-y-4">
      {error && <p role="alert" className="text-red-700">{error}</p>}
      {error && <Button variant="outline" onClick={() => setRefresh(value => value + 1)}>Consultar novamente</Button>}
      {!status && !error && <p>Consultando análise...</p>}
      {status && !status.generation && <p>Ainda não gerada.</p>}
      {status && !status.configured && <p>Geração indisponível neste ambiente.</p>}
      {busy && <p role="status">{result ? 'Gerando novamente; a versão anterior continua disponível.' : 'Gerando resumo...'}</p>}
      {state === 'failed' && <p role="alert" className="text-red-700">A geração falhou. Você pode tentar novamente.</p>}
      {status && <Button onClick={generate} disabled={submitting || busy || !status.configured}>
        {submitting ? 'Solicitando...' : result ? 'Gerar novamente' : state === 'failed' ? 'Tentar novamente' : 'Gerar resumo'}
      </Button>}
      {content && <div className="space-y-5">
        <p className="text-sm text-gray-500">Versão {result.revision} · {result.provider} · {result.model}. Revise os itens com as evidências do transcript.</p>
        <section><h3 className="font-semibold text-gray-900">Resumo</h3><p className="whitespace-pre-wrap mt-2">{content.summary}</p></section>
        {[
          ['Tópicos', content.topics], ['Decisões', content.decisions],
          ['Tarefas', content.action_items], ['Pendências', content.open_questions],
        ].map(([title, items]) => <section key={title}>
          <h3 className="font-semibold text-gray-900">{title}</h3>
          {items.length === 0 ? <p className="text-gray-500 mt-2">Nenhum item identificado.</p> : <ul className="space-y-3 mt-2">
            {items.map((item, index) => <li key={index} className="p-3 bg-gray-50 rounded-lg">
              <p>{item.description}</p>
              {title === 'Tarefas' && <p className="text-sm text-gray-600 mt-1">Responsável: {item.assignee || 'Não identificado'} · Prazo: {item.due_date || 'Sem prazo explícito'}</p>}
              <EvidenceLinks evidence={item.evidence} references={result.references} />
            </li>)}
          </ul>}
        </section>)}
      </div>}
    </div>
  </CardContent></Card>
}
