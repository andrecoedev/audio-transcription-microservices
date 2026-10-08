import { useEffect, useState } from 'react'

import Button from './Button'
import HelpPopover from './HelpPopover'
import { usageService } from '../services/usageService'
import { useAuthStore } from '../stores/authStore'
import { formatCount, formatNumber, formatTimestamp } from '../utils/format'

function numberValue(value) {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) && number >= 0 ? number : null
}

function aggregate(metrics, metricName, unit) {
  const matching = metrics.filter((metric) => metric.metric === metricName && metric.unit === unit)
  const observations = matching.reduce((total, metric) => total + (numberValue(metric.observations) ?? 0), 0)
  const knownValues = matching.map((metric) => numberValue(metric.quantity_total)).filter((value) => value !== null)
  const unknownCount = matching.reduce((total, metric) => {
    const explicitUnknown = numberValue(metric.unknown_observations) ?? 0
    const observationsForMetric = numberValue(metric.observations) ?? 0
    return total + Math.max(explicitUnknown, metric.quantity_total == null ? observationsForMetric : 0)
  }, 0)

  return {
    observations,
    total: knownValues.length ? knownValues.reduce((sum, value) => sum + value, 0) : null,
    partial: knownValues.length > 0 && unknownCount > 0,
  }
}

function MetricValue({ metric, emptyLabel, format }) {
  if (!metric.observations) return <span>{emptyLabel}</span>
  if (metric.total === null) return <span>Não informado</span>
  return <>
    <span>{format(metric.total)}</span>
    {metric.partial && <span className="mt-1 block text-xs font-normal text-amber-800">Soma parcial: há registros sem quantidade informada.</span>}
  </>
}

export default function UsageOverview() {
  const userId = useAuthStore((state) => state.user?.id)
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  const [request, setRequest] = useState({ userId: null, overview: null, loading: true, error: false })
  const [planRequest, setPlanRequest] = useState({ userId: null, plan: null, loading: true, error: false })
  const [retry, setRetry] = useState(0)
  const [planRetry, setPlanRetry] = useState(0)

  useEffect(() => {
    if (!isAuthenticated || !userId) return undefined

    let active = true
    setPlanRequest({ userId, plan: null, loading: true, error: false })
    usageService.getPlan().then((plan) => {
      if (active) setPlanRequest({ userId, plan, loading: false, error: false })
    }).catch(() => {
      if (active) setPlanRequest({ userId, plan: null, loading: false, error: true })
    })

    return () => { active = false }
  }, [isAuthenticated, userId, planRetry])

  useEffect(() => {
    if (!isAuthenticated || !userId) return undefined

    let active = true
    setRequest({ userId, overview: null, loading: true, error: false })
    usageService.getOverview().then((result) => {
      if (active) setRequest({ userId, overview: result, loading: false, error: false })
    }).catch(() => {
      if (active) setRequest({ userId, overview: null, loading: false, error: true })
    })

    return () => { active = false }
  }, [isAuthenticated, userId, retry])

  if (!isAuthenticated || !userId) return null

  const currentRequest = request.userId === userId ? request : null
  const currentPlanRequest = planRequest.userId === userId ? planRequest : null
  const loading = !currentRequest || currentRequest.loading
  const error = Boolean(currentRequest?.error)
  const overview = currentRequest?.overview
  const planLoading = !currentPlanRequest || currentPlanRequest.loading
  const planError = Boolean(currentPlanRequest?.error)
  const plan = currentPlanRequest?.plan
  const metrics = Array.isArray(overview?.metrics) ? overview.metrics : []
  const hasRecordedData = metrics.some((metric) => (numberValue(metric.observations) ?? 0) > 0)
  const audio = aggregate(metrics, 'audio_seconds', 'second')
  const attempts = aggregate(metrics, 'attempt', 'attempt')
  const after = overview?.after ? formatTimestamp(overview.after) : null
  const before = overview?.before ? formatTimestamp(overview.before) : null
  const validAfter = after && after !== '—' ? after : null
  const validBefore = before && before !== '—' ? before : null
  const period = validAfter && validBefore ? `Período: ${validAfter} – ${validBefore}`
    : validAfter ? `A partir de ${validAfter}`
      : validBefore ? `Até ${validBefore}` : null

  return <section aria-labelledby="usage-overview-title" className="space-y-3">
    <div className="space-y-3 rounded-xl border border-gray-200 bg-white p-4">
      <div className="flex items-center gap-2">
        <h3 className="font-semibold text-gray-900">Plano da conta</h3>
        <HelpPopover label="Plano da conta">
          Os valores abaixo vêm do plano efetivo retornado pela USAGI. Uso com uma credencial própria é acompanhado separadamente e não reduz a cota USAGI.
        </HelpPopover>
      </div>
      {planLoading && <p role="status" className="text-sm text-gray-600">Carregando dados do plano…</p>}
      {planError && <div role="alert" className="space-y-2 text-sm text-amber-900">
        <p>Não foi possível carregar os dados do plano.</p>
        <Button type="button" variant="outline" size="sm" onClick={() => setPlanRetry((value) => value + 1)}>Tentar novamente</Button>
      </div>}
      {!planLoading && !planError && plan && <>
        <p className="text-xs text-gray-500">Fonte: plano efetivo da conta, informado pela API da USAGI.</p>
        <p className="text-sm font-medium text-gray-900">Plano atual: {planName(plan.plan)}</p>
        {plan.plan === 'free' && !plan.local_processing_available && !plan.beta?.capabilities?.includes('transcription.platform') && <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
          A transcrição fornecida pela USAGI ainda não está disponível neste ambiente. Sua franquia não habilita esse serviço por si só.
        </p>}
        <p className="text-xs text-gray-600">
          Período: {formatTimestamp(plan.period_start)} · Renovação: {formatTimestamp(plan.renews_at)}
        </p>
        <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <PlanValue label="Cota USAGI" value={`${formatPlanDuration(plan.quota?.limit_seconds)} de áudio`} />
          <PlanValue label="Consumido pela USAGI" value={`${formatPlanDuration(plan.quota?.consumed_seconds)} de áudio`} />
          <PlanValue label="Reservado pela USAGI" value={`${formatPlanDuration(plan.quota?.reserved_seconds)} de áudio`} />
          <PlanValue label="Disponível na USAGI" value={`${formatPlanDuration(plan.quota?.available_seconds)} de áudio`} />
        </dl>
        <div className="rounded-lg bg-gray-50 p-3 text-sm">
          <p className="font-medium text-gray-900">Uso com credenciais próprias (BYOK)</p>
          <p className="mt-1 text-gray-700">Medido: {formatPlanDuration(plan.byok?.measured_seconds)} · Pendente: {formatPlanDuration(plan.byok?.pending_seconds)}</p>
          <p className="mt-1 text-xs text-gray-600">Cobrado pelo provedor da sua credencial; não é deduzido da cota USAGI.</p>
        </div>
        {plan.beta && <div className="rounded-lg bg-primary-50 p-3 text-sm text-primary-900">
          <p className="font-medium">Acesso beta até {formatTimestamp(plan.beta.expires_at)}</p>
          {plan.beta.capabilities?.length > 0 && <p className="mt-1">Recursos: {plan.beta.capabilities.map(capabilityName).join(', ')}</p>}
        </div>}
        <p className="text-sm text-gray-700">Processamento local: {plan.local_processing_available ? 'disponível' : 'indisponível'}.</p>
        <details className="text-sm text-gray-600">
          <summary className="cursor-pointer">Limites operacionais</summary>
          <ul className="mt-2 space-y-1">
            <li>Áudio por arquivo: {formatPlanDuration(plan.limits?.max_audio_seconds)}</li>
            <li>Armazenamento: {formatBytes(plan.limits?.max_stored_bytes)}</li>
            <li>Trabalhos na fila: {formatNumber(plan.limits?.max_queued_jobs)}</li>
            <li>Trabalhos em processamento: {formatNumber(plan.limits?.max_processing_jobs)}</li>
          </ul>
        </details>
      </>}
    </div>

    <div className="flex items-center gap-2">
      <h3 id="usage-overview-title" className="font-semibold text-gray-900">Consumo registrado</h3>
      <HelpPopover label="Consumo registrado">
        A duração é uma medida técnica do áudio nas tentativas, inclusive as que falharam. Ela não representa faturamento nem saldo de créditos.
      </HelpPopover>
    </div>

    {loading && <p role="status" className="text-sm text-gray-600">Carregando dados de uso…</p>}
    {error && <div role="alert" className="space-y-2 text-sm text-amber-900">
      <p>Não foi possível carregar os dados de uso.</p>
      <Button type="button" variant="outline" size="sm" onClick={() => setRetry((value) => value + 1)}>Tentar novamente</Button>
    </div>}
    {!loading && !error && period && <p className="text-xs text-gray-500">{period}</p>}
    {!loading && !error && !hasRecordedData && <p className="text-sm text-gray-600">Nenhum dado de uso registrado.</p>}
    {!loading && !error && hasRecordedData && <dl className="grid gap-3 text-sm sm:grid-cols-2">
      <div className="rounded-lg bg-gray-50 p-3">
        <dt className="text-gray-600">Áudio registrado</dt>
        <dd className="mt-1 font-medium text-gray-900">
          <MetricValue metric={audio} emptyLabel="Sem registros" format={(seconds) => `${formatNumber(seconds / 60, { maximumFractionDigits: 2 })} min`} />
        </dd>
      </div>
      <div className="rounded-lg bg-gray-50 p-3">
        <dt className="text-gray-600">Operações iniciadas</dt>
        <dd className="mt-1 font-medium text-gray-900">
          <MetricValue metric={attempts} emptyLabel="Sem registros" format={(count) => formatCount(count, 'operação iniciada', 'operações iniciadas')} />
        </dd>
      </div>
    </dl>}

    <p className="text-xs text-gray-600">Contratação de planos ainda não disponível.</p>
  </section>
}

function PlanValue({ label, value }) {
  return <div className="rounded-lg bg-gray-50 p-3">
    <dt className="text-gray-600">{label}</dt>
    <dd className="mt-1 font-medium text-gray-900">{value}</dd>
  </div>
}

function planName(plan) {
  return ({ free: 'Free', starter: 'Starter', business: 'Business' })[plan] || 'Não identificado'
}

function capabilityName(capability) {
  return ({
    'transcription.byok': 'Transcrição com sua conta',
    'transcription.local': 'Transcrição local',
    'transcription.platform': 'Transcrição fornecida pela USAGI',
    'intelligence.byok': 'Resumos com sua conta',
    'intelligence.platform': 'Resumos fornecidos pela USAGI',
  })[capability] || 'Permissão adicional'
}

function formatBytes(value) {
  const bytes = numberValue(value)
  if (bytes === null) return '—'
  if (bytes < 1024 ** 2) return `${formatNumber(bytes / 1024, { maximumFractionDigits: 1 })} KB`
  return `${formatNumber(bytes / (1024 ** 2), { maximumFractionDigits: 1 })} MB`
}

function formatPlanDuration(value) {
  const seconds = numberValue(value)
  if (seconds === null) return '—'
  if (seconds < 60) return `${formatNumber(seconds, { maximumFractionDigits: 2 })} s`
  return `${formatNumber(seconds / 60, { maximumFractionDigits: 2 })} min`
}
