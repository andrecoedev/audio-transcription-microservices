import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, Clock3, RefreshCw, Search, Users } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import Card, { CardContent, CardHeader, CardTitle } from '../components/Card'
import Button from '../components/Button'
import HelpPopover from '../components/HelpPopover'
import { adminSettingsService } from '../services/adminSettingsService'

const sections = [
  { id: 'beta', title: 'Beta fechado', prefix: 'beta.' },
  { id: 'assemblyai', title: 'AssemblyAI', prefix: 'assemblyai.' },
  { id: 'limits', title: 'Limites', prefix: 'limits.' },
]

const fieldLabels = {
  'beta.enabled': 'Ativação da rodada',
  'beta.round_name': 'Nome da rodada',
  'beta.round_id': 'Identificador da rodada',
  'beta.max_participants': 'Limite de participantes (contas)',
  'beta.quota_minutes_per_participant': 'Cota por participante (minutos)',
  'assemblyai.platform_enabled': 'Uso da plataforma',
  'assemblyai.hard_stop_usd': 'Teto interno (US$)',
  'assemblyai.alert_usd': 'Alerta interno (US$)',
  'assemblyai.model': 'Modelo',
  'assemblyai.speaker_detection': 'Detecção de falantes',
  'assemblyai.price_version': 'Versão da tarifa conferida',
  'limits.max_audio_seconds': 'Duração máxima por arquivo (segundos)',
  'limits.max_upload_mb': 'Tamanho máximo por arquivo (MB)',
  'limits.max_stored_bytes': 'Armazenamento por conta (bytes)',
  'limits.max_queued_per_account': 'Transcrições aguardando por conta',
  'limits.max_processing_per_account': 'Processamentos simultâneos por conta',
  'limits.max_platform_queued': 'Chamadas da plataforma aguardando',
  'limits.max_platform_processing': 'Chamadas simultâneas da plataforma',
}

function message(error, fallback) {
  if (error?.status === 409 && error?.code === 'admin_settings_revision_conflict') return 'A configuração mudou em outra sessão. Seu rascunho foi mantido; recarregue os dados antes de decidir o que salvar.'
  return error?.message || fallback
}

function display(value) {
  if (value === true) return 'Sim'
  if (value === false) return 'Não'
  if (value == null || value === '') return '—'
  return String(value)
}

function formatUsd(value) {
  const match = /^(\d+)(?:\.(\d+))?$/.exec(String(value ?? '0'))
  if (!match) return 'US$ —'
  const integer = new Intl.NumberFormat('pt-BR').format(BigInt(match[1]))
  const fraction = (match[2] || '').replace(/0+$/, '')
  const currency = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).formatToParts(0)
  const prefix = currency.filter((part) => part.type === 'currency' || part.type === 'literal').map((part) => part.value).join('')
  return `${prefix}${integer}${fraction ? `${currency.find((part) => part.type === 'decimal')?.value || ','}${fraction}` : ''}`
}

function fieldValue(key, value) {
  if (key?.endsWith('_usd')) return formatUsd(value)
  if (key === 'assemblyai.model' && value === 'universal-3-5-pro') return 'Universal-3.5 Pro'
  if (key === 'assemblyai.speaker_detection') return value ? 'Ativada' : 'Desativada'
  return display(value)
}

function Field({ definition, value, onChange, disabled }) {
  const { key, type, description, minimum, maximum, editable, options } = definition
  const integer = type === 'int' || type === 'integer'
  const shownValue = fieldValue(key, value)
  const label = fieldLabels[key] || key
  return <label className="block min-w-0 space-y-1.5">
    <span className="flex flex-wrap items-center gap-2 text-sm font-medium capitalize text-gray-800">
      {label}
      {!editable && <span className="badge badge-info">Somente leitura</span>}
    </span>
    <span className="block text-xs leading-relaxed text-gray-500">{description}</span>
    {editable ? type === 'boolean' ? <select className="input max-w-sm" value={String(value)} disabled={disabled}
      onChange={(event) => onChange(event.target.value === 'true')} aria-label={label}>
      <option value="true">Ativada</option><option value="false">Desativada</option>
    </select> : type === 'enum' ? <select className="input max-w-sm" value={String(value)} disabled={disabled}
      onChange={(event) => onChange(event.target.value)} aria-label={label}>
      {(options || []).map((option) => <option key={option} value={option}>{option}</option>)}
    </select> : <input className="input max-w-sm" aria-label={label} type={type === 'string' ? 'text' : 'number'}
      min={minimum ?? undefined} max={maximum ?? undefined} step={type === 'decimal' ? '0.00000001' : '1'}
      value={value ?? ''} disabled={disabled} onChange={(event) => onChange(integer ? Number(event.target.value) : event.target.value)} />
      : <p className="max-w-sm rounded-lg bg-gray-50 px-3 py-2 text-sm text-gray-700">{shownValue}</p>}
    {definition.requires_confirmation && editable && <span className="block text-xs font-medium text-amber-700">Exige confirmação antes de salvar.</span>}
  </label>
}

function ConfirmDialog({ confirmation, onCancel, onConfirm, busy }) {
  const dialogRef = useRef(null)
  const cancelRef = useRef(null)
  const cancelAction = useRef(onCancel)
  const busyAction = useRef(busy)
  const isOpen = Boolean(confirmation)
  cancelAction.current = onCancel
  busyAction.current = busy
  useEffect(() => {
    if (!isOpen) return undefined
    const previousFocus = document.activeElement
    cancelRef.current?.focus()
    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && !busyAction.current) { event.preventDefault(); cancelAction.current(); return }
      if (event.key !== 'Tab') return
      const focusable = dialogRef.current?.querySelectorAll('button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])')
      if (!focusable?.length) { event.preventDefault(); dialogRef.current?.focus(); return }
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && (document.activeElement === first || !dialogRef.current.contains(document.activeElement))) {
        event.preventDefault(); last.focus()
      } else if (!event.shiftKey && (document.activeElement === last || !dialogRef.current.contains(document.activeElement))) {
        event.preventDefault(); first.focus()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      if (previousFocus?.isConnected) previousFocus.focus()
    }
  }, [isOpen])
  if (!confirmation) return null
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-950/40 p-4" role="presentation">
    <section ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="admin-confirm-title" tabIndex={-1} className="max-h-[calc(100dvh-2rem)] w-full max-w-lg overflow-y-auto rounded-xl bg-white p-6 shadow-xl">
      <h2 id="admin-confirm-title" className="text-lg font-semibold text-gray-900">Confirme a alteração</h2>
      <p className="mt-2 text-sm text-gray-600">{confirmation.text}</p>
      {confirmation.changes?.length > 0 && <ul className="mt-4 space-y-2 rounded-lg bg-gray-50 p-3 text-sm">
        {confirmation.changes.map(({ label, before, after, key }) => <li key={label} className="break-words"><strong>{label}:</strong> {fieldValue(key, before)} → {fieldValue(key, after)}</li>)}
      </ul>}
      <div className="mt-6 flex flex-wrap justify-end gap-2">
        <button ref={cancelRef} type="button" className="inline-flex items-center justify-center rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50" onClick={onCancel} disabled={busy}>Cancelar</button>
        <Button onClick={onConfirm} loading={busy}>Confirmar</Button>
      </div>
    </section>
  </div>
}

export default function AdminSettings() {
  const [snapshot, setSnapshot] = useState(null)
  const [overview, setOverview] = useState(null)
  const [participants, setParticipants] = useState(null)
  const [history, setHistory] = useState([])
  const [draft, setDraft] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [savingSection, setSavingSection] = useState(null)
  const [confirmation, setConfirmation] = useState(null)
  const [search, setSearch] = useState('')
  const [accounts, setAccounts] = useState([])
  const [searchError, setSearchError] = useState('')
  const [expiresAt, setExpiresAt] = useState('')

  const load = useCallback(async () => {
    setLoading(true); setError(''); setNotice('')
    try {
      const [settings, status, roster, audit] = await Promise.all([
        adminSettingsService.getSettings(), adminSettingsService.getOverview(),
        adminSettingsService.getParticipants(), adminSettingsService.getHistory(),
      ])
      setSnapshot(settings); setOverview(status); setParticipants(roster); setHistory(audit.items || [])
      setDraft(settings.values || {})
    } catch (failure) { setError(message(failure, 'Não foi possível carregar as configurações administrativas.')) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const definitions = useMemo(() => snapshot?.definitions || [], [snapshot])
  const setValue = (key, value) => setDraft((current) => ({ ...current, [key]: value }))
  const changeList = (keys) => keys.map((key) => ({ key, label: fieldLabels[key] || key, before: snapshot.values[key], after: draft[key] }))
  const sectionFields = (section) => definitions.filter((item) => item.key.startsWith(section.prefix))

  async function runConfirmed(action, savedSection = null) {
    setBusy(true); setSavingSection(savedSection || 'participants'); setError(''); setNotice('')
    try {
      const result = await action()
      if (result?.values) {
        const previousValues = snapshot?.values || {}
        setSnapshot(result)
        setDraft((current) => {
          const next = { ...result.values }
          if (savedSection !== '*') Object.entries(current).forEach(([key, value]) => {
            const editedOutsideSavedSection = savedSection
              ? !key.startsWith(`${savedSection}.`) && String(value) !== String(previousValues[key])
              : String(value) !== String(previousValues[key])
            if (editedOutsideSavedSection) next[key] = value
          })
          return next
        })
      }
      setConfirmation(null)
      setNotice('Alteração salva.')
      try { await refreshOperational() }
      catch { setError('Alteração salva, mas não foi possível atualizar o resumo. Recarregue a página para conferir o estado atual.') }
    } catch (failure) {
      setConfirmation(null)
      setError(message(failure, 'Não foi possível salvar. Revise os dados e tente novamente.'))
    }
    finally { setBusy(false); setSavingSection(null) }
  }

  async function refreshOperational() {
    const [status, roster, audit] = await Promise.all([adminSettingsService.getOverview(), adminSettingsService.getParticipants(), adminSettingsService.getHistory()])
    setOverview(status); setParticipants(roster); setHistory(audit.items || [])
  }

  function saveSection(section) {
    const fields = sectionFields(section).filter((item) => item.editable && String(snapshot.values[item.key]) !== String(draft[item.key]))
    if (!fields.length) return
    const changes = Object.fromEntries(fields.map((item) => [item.key.slice(section.prefix.length), draft[item.key]]))
    const critical = fields.some((item) => item.requires_confirmation)
    const confirm = () => runConfirmed(() => adminSettingsService.save(section.id, snapshot.version, critical, changes), section.id)
    if (critical) setConfirmation({ text: 'Confira os valores anteriores e novos. A mudança pode autorizar convites, uso da plataforma ou alterar cotas.', changes: changeList(fields.map((item) => item.key)), onConfirm: confirm })
    else confirm()
  }

  function initialize() {
    setConfirmation({ text: 'Preparar a configuração cria uma política desativada e preserva a rodada, o orçamento e o histórico já existentes. Nenhuma chamada externa será feita.', onConfirm: () => runConfirmed(() => adminSettingsService.initialize(snapshot.version), '*') })
  }

  async function findAccounts(event) {
    event.preventDefault(); setSearchError(''); setAccounts([])
    const query = search.trim()
    if (query.length < 2) { setSearchError('Digite pelo menos dois caracteres.'); return }
    setBusy(true)
    try { setAccounts((await adminSettingsService.searchAccounts(query)).items || []) }
    catch (failure) { setSearchError(message(failure, 'Não foi possível buscar contas.')) }
    finally { setBusy(false) }
  }

  function grantAccount(account) {
    if (!snapshot?.values['beta.round_id']) { setSearchError('Defina e salve o identificador da rodada antes de convidar contas.'); return }
    if (!expiresAt) { setSearchError('Informe a data de expiração do convite.'); return }
    setConfirmation({ text: `Conceder acesso Beta para ${account.email || account.username}?`, changes: [
      { label: 'Conta', before: 'Sem convite', after: account.email || account.username },
      { label: 'Permissão', before: '—', after: 'transcription.platform' },
      { label: 'Expira em', before: '—', after: new Date(`${expiresAt}T23:59:59`).toLocaleString('pt-BR') },
    ], onConfirm: () => runConfirmed(async () => {
      await adminSettingsService.grant(account.user_id, snapshot.values['beta.round_id'], new Date(`${expiresAt}T23:59:59`).toISOString())
      return null
    }) })
  }

  function revokeAccount(person) {
    setConfirmation({ text: `Revogar o acesso Beta de ${person.email || person.username}? O histórico e o consumo registrados serão preservados.`, changes: [
      { label: 'Acesso', before: 'Ativo', after: 'Revogado' },
    ], onConfirm: () => runConfirmed(async () => {
      await adminSettingsService.revoke(person.user_id, person.grant_id)
      return null
    }) })
  }

  if (loading) return <div role="status" className="p-6 text-sm text-gray-600">Carregando painel administrativo…</div>
  return <div className="mx-auto w-full max-w-6xl min-w-0 space-y-6 px-1 pb-10">
    <PageHeader title="Administração" description="Configuração operacional da rodada Beta fechada. Alterações entram em vigor conforme a política do servidor.">
      <Button variant="outline" icon={RefreshCw} onClick={load} disabled={busy}>Recarregar</Button>
    </PageHeader>
    {error && <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800"><span>{error}</span>{error.includes('mudou') && <Button variant="outline" size="sm" onClick={load} disabled={busy}>Recarregar e descartar rascunho</Button>}</div>}
    {notice && <p role="status" className="flex items-center gap-2 text-sm text-green-700"><CheckCircle2 className="h-4 w-4" />{notice}</p>}

    <Card><CardHeader><CardTitle>Visão geral</CardTitle></CardHeader><CardContent>
      {overview && <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric icon={Users} label="Participantes" value={`${overview.participants_used} / ${overview.participants_maximum}`} />
        <Metric icon={Clock3} label="Áudio consumido" value={`${formatSeconds(overview.consumed_seconds)} min`} detail={`${formatSeconds(overview.reserved_seconds)} min reservados`} />
        <Metric label="Uso autorizado estimado" value={formatUsd(overview.financial.authorized_usd)} detail={`Disponível no teto: ${formatUsd(overview.financial.available_usd)}`} />
        <Metric label="Chamadas pendentes" value={overview.financial.queued_calls} detail={`Sem resolução: ${overview.financial.unresolved_calls}`} />
      </div>}
      {overview && (overview.financial.committed_above_limit || overview.financial.alert_reached || overview.financial.review_required) && <div role="alert" className="mt-4 flex gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900"><AlertTriangle className="h-5 w-5 shrink-0" /><div>{overview.financial.committed_above_limit ? 'O comprometimento ultrapassou o teto interno. Novas operações permanecem sujeitas aos controles do servidor.' : overview.financial.review_required ? 'A revisão operacional do orçamento está pendente.' : 'O alerta interno de gastos foi atingido.'}</div></div>}
      {overview && (!overview.financial.balance_review_valid || !overview.financial.price_review_valid) && <div role="alert" className="mt-4 flex gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900"><AlertTriangle className="h-5 w-5 shrink-0" /><div><strong>Revisão operacional necessária.</strong> Confira {[
        !overview.financial.balance_review_valid && 'a autorização operacional do orçamento',
        !overview.financial.price_review_valid && 'a tarifa registrada para esta rodada',
      ].filter(Boolean).join(' e ')} antes de ativar o uso da plataforma ou elevar o teto. Nenhum saldo externo é exibido.</div></div>}
      {overview && <div className="mt-5 border-t pt-4"><h3 className="mb-3 text-sm font-semibold">Sistema</h3><div className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
        <Status label="Banco de dados" value={overview.system.database} /><Status label="Credencial AssemblyAI" value={overview.system.assemblyai_credential_configured ? 'Configurada' : 'Não configurada'} />
        <Status label="Firebase" value={overview.system.firebase_configured ? 'Configurado' : 'Não configurado'} /><Status label="Redis" value={overview.system.redis || 'Estado indisponível'} />
        <Status label="Workers" value={overview.system.worker_available ? `${overview.system.worker_count ?? 0} registrado(s)` : 'Nenhum registrado'} /><Status label="Fila" value={overview.system.queue || 'Estado indisponível'} />
      </div><p className="mt-3 text-xs text-gray-500">O estado exibido não testa inferência nem consulta saldo externo.</p></div>}
    {history.length > 0 && <details className="mt-5 border-t pt-4"><summary className="cursor-pointer text-sm font-medium text-primary-700">Histórico de alterações ({history.length})</summary><ol className="mt-4 space-y-3">{history.map((entry) => <li key={entry.id} className="break-words border-l-2 border-gray-200 pl-3 text-sm"><p className="font-medium">{entry.event === 'admin.settings_initialized' ? 'Configuração preparada' : 'Configuração alterada'} · {new Date(entry.created_at).toLocaleString('pt-BR')}</p><p className="text-xs text-gray-500">Administrador {entry.actor_user_id ?? 'removido'} · versão {entry.changes?.version ?? '—'}</p>
      <ul className="mt-1 space-y-1">{Object.entries(entry.changes?.after || {}).filter(([key]) => fieldLabels[key]).map(([key, value]) => <li key={key} className="text-xs text-gray-700">{fieldLabels[key]}: {fieldValue(key, entry.changes.before?.[key])} → {fieldValue(key, value)}</li>)}</ul>
    </li>)}</ol></details>}
    </CardContent></Card>

    {sections.map((section) => <Card key={section.id}><CardHeader className="flex flex-wrap items-start justify-between gap-3"><div><CardTitle>{section.title}</CardTitle><p className="mt-1 text-xs text-gray-500">Versão {snapshot?.version ?? 0} · salvamento independente desta seção</p></div><HelpPopover label={`Ajuda: ${section.title}`}>Os limites efetivos podem ser menores por capacidade técnica do ambiente. Valores monetários são tetos internos em USD, não saldos do provedor.</HelpPopover></CardHeader>
      <CardContent>
        {section.id === 'beta' && <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-gray-50 p-3"><span className="text-sm font-medium">Estado da rodada Beta</span><span className={`badge ${!snapshot?.configured ? 'badge-warning' : snapshot.values['beta.enabled'] ? 'badge-success' : 'badge-info'}`}>{!snapshot?.configured ? 'Não preparada' : snapshot.values['beta.enabled'] ? 'Ativa' : 'Desativada'}</span></div>}
        {!snapshot?.configured && section.id === 'beta' && <div className="mb-5 flex flex-col gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4 sm:flex-row sm:items-center sm:justify-between"><div><h2 className="font-semibold text-gray-900">Configuração ainda não preparada</h2><p className="mt-1 max-w-2xl text-sm text-gray-600">Prepare uma política desativada. Valores existentes de rodada, orçamento e histórico serão preservados; nenhuma chamada externa será feita.</p></div><Button onClick={initialize} disabled={busy}>Preparar configuração</Button></div>}
        <div className="grid grid-cols-1 gap-x-6 gap-y-5 lg:grid-cols-2">{sectionFields(section).map((item) => <div key={item.key}>
          <Field definition={item} value={draft[item.key]} disabled={busy || !snapshot?.configured || !item.editable} onChange={(value) => setValue(item.key, value)} />
          {snapshot?.overrides?.[item.key] && <p className="mt-1 text-xs text-amber-700">{snapshot.overrides[item.key]} (valor salvo: {display(snapshot.saved_values[item.key])})</p>}
        </div>)}</div>
      {section.id === 'assemblyai' && <p className="mt-5 text-xs text-gray-500">Modelo e detecção de falantes são fixos. Nenhum saldo externo é consultado.</p>}
        {snapshot?.configured && <div className="mt-6 flex justify-end"><Button onClick={() => saveSection(section)} disabled={busy || !sectionFields(section).some((item) => item.editable && String(snapshot.values[item.key]) !== String(draft[item.key]))} loading={savingSection === section.id}>Salvar {section.title}</Button></div>}
        {section.id === 'beta' && <ParticipantsCard participants={participants} maximum={snapshot?.values['beta.max_participants']} search={search} setSearch={setSearch} accounts={accounts} searchError={searchError} busy={busy || !snapshot?.configured} findAccounts={findAccounts} grantAccount={grantAccount} revokeAccount={revokeAccount} expiresAt={expiresAt} setExpiresAt={setExpiresAt} />}
      </CardContent></Card>)}
    <ConfirmDialog confirmation={confirmation} busy={busy} onCancel={() => setConfirmation(null)} onConfirm={confirmation?.onConfirm} />
  </div>
}

function Metric({ icon: Icon, label, value, detail }) { return <div className="min-w-0 rounded-lg bg-gray-50 p-4"><p className="flex items-center gap-2 text-xs text-gray-500">{Icon && <Icon className="h-4 w-4" aria-hidden="true" />}{label}</p><p className="mt-2 break-words text-xl font-semibold text-gray-900">{value}</p>{detail && <p className="mt-1 break-words text-xs text-gray-500">{detail}</p>}</div> }
function Status({ label, value }) { const translated = value === 'connected' ? 'Conectado' : display(value); return <div className="flex min-w-0 justify-between gap-3 rounded-lg border p-3"><span className="text-gray-600">{label}</span><span className="break-words text-right font-medium">{translated}</span></div> }
function formatSeconds(value) { const seconds = Number(value || 0); return Number.isFinite(seconds) ? (seconds / 60).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) : '—' }

function ParticipantsCard({ participants, maximum, search, setSearch, accounts, searchError, busy, findAccounts, grantAccount, revokeAccount, expiresAt, setExpiresAt }) {
  return <section aria-labelledby="admin-participants-title" className="mt-6 border-t pt-5">
    <h3 id="admin-participants-title" className="text-base font-semibold text-gray-900">Participantes e convites</h3><p className="mt-1 text-sm text-gray-600">Vagas usadas não são repostas após revogação. Consumo e reservas permanecem no histórico.</p>
    <p className="mb-4 text-sm font-medium">Vagas usadas: {participants?.used_slots ?? '—'} / {maximum ?? participants?.maximum ?? '—'}</p>
    <form onSubmit={findAccounts} className="flex flex-col gap-2 sm:flex-row"><label className="sr-only" htmlFor="admin-account-search">Buscar contas</label><input id="admin-account-search" className="input min-w-0 flex-1" minLength={2} maxLength={100} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar por nome ou e-mail" /><Button type="submit" icon={Search} loading={busy}>Buscar contas</Button></form>
    {searchError && <p role="alert" className="mt-2 text-sm text-red-700">{searchError}</p>}
    {accounts.length > 0 && <div className="mt-4 space-y-2 rounded-lg border p-3"><label className="block max-w-sm text-sm">Expira em<input className="input mt-1" type="date" value={expiresAt} onChange={(event) => setExpiresAt(event.target.value)} /></label>{accounts.map((account) => <div key={account.user_id} className="flex flex-col justify-between gap-2 border-t pt-3 sm:flex-row sm:items-center"><div className="min-w-0"><p className="break-words text-sm font-medium">{account.username}</p><p className="break-all text-xs text-gray-500">{account.email}</p></div><Button size="sm" onClick={() => grantAccount(account)} disabled={busy}>Conceder acesso</Button></div>)}</div>}
    <div className="mt-5 space-y-3">{(participants?.items || []).length === 0 ? <p className="text-sm text-gray-500">Ainda não há contas convidadas.</p> : participants.items.map((person) => <div key={person.grant_id} className="rounded-lg border p-4"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start"><div className="min-w-0"><p className="break-words font-medium">{person.username}</p><p className="break-all text-sm text-gray-500">{person.email}</p><p className="mt-1 text-xs">{person.active ? <span className="badge badge-success">Ativo</span> : <span className="badge badge-warning">Inativo</span>}</p></div>{person.active && <Button size="sm" variant="danger" onClick={() => revokeAccount(person)} disabled={busy}>Revogar acesso</Button>}</div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-gray-600 sm:grid-cols-4"><span>Cota: {formatSeconds(person.quota_seconds)} min</span><span>Consumido: {formatSeconds(person.consumed_seconds)} min</span><span>Reservado: {formatSeconds(person.reserved_seconds)} min</span><span>Disponível: {formatSeconds(person.available_seconds)} min</span></div>
      {person.committed_above_limit && <p role="alert" className="mt-3 flex items-center gap-2 rounded bg-red-50 p-2 text-sm font-medium text-red-800"><AlertTriangle className="h-4 w-4" />Comprometimento acima da cota; disponível zero. Histórico preservado.</p>}
      {person.expires_at && <p className="mt-2 text-xs text-gray-500">Expira: {new Date(person.expires_at).toLocaleString('pt-BR')}</p>}</div>)}</div>
  </section>
}
