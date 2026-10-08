import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import Button from '../components/Button'
import Card, { CardContent, CardHeader, CardTitle } from '../components/Card'
import ProcessingStatus from '../components/ProcessingStatus'
import NewTranscription from './NewTranscription'
import { formatCount, formatNumber } from '../utils/format'
import { guestService } from '../services/guestService'
import { useAuthStore } from '../stores/authStore'

const STORAGE_KEY = 'usagi-guest-session'

function storedSession() {
  try {
    return JSON.parse(sessionStorage.getItem(STORAGE_KEY))
  } catch {
    sessionStorage.removeItem(STORAGE_KEY)
    return null
  }
}

export default function Guest({ showUpload = true }) {
  const navigate = useNavigate()
  const authenticated = useAuthStore((state) => state.isAuthenticated)
  const [session, setSession] = useState(storedSession)
  const [policy, setPolicy] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [retry, setRetry] = useState(0)

  function saveSession(value) {
    setSession(value)
    if (value) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value))
    else sessionStorage.removeItem(STORAGE_KEY)
  }

  useEffect(() => {
    if (authenticated || !showUpload) return
    let active = true
    guestService.policy().then((value) => { if (active) { setPolicy(value); setError('') } })
      .catch(() => { if (active) setError('Não foi possível carregar os limites. Tente novamente.') })
    return () => { active = false }
  }, [retry, authenticated, showUpload])

  useEffect(() => {
    if (!session?.guest_token) return
    let active = true
    let timer
    async function load() {
      try {
        const value = session.resultId
          ? await guestService.result(session.guest_token, session.resultId)
          : await guestService.session(session.guest_token)
        if (!active) return
        if (session.resultId) setResult(value)
        setError('')
        if (['queued', 'processing'].includes(value.status)) timer = setTimeout(load, 3000)
      } catch (failure) {
        if (!active) return
        setError(failure.status === 401 ? 'Sessão de visitante expirada ou já salva em uma conta.' : failure.message)
        if (failure.status === 401) {
          sessionStorage.removeItem(STORAGE_KEY)
          setSession(null)
          setResult(null)
        }
      }
    }
    load()
    return () => { active = false; clearTimeout(timer) }
  }, [session, retry])

  async function createJob(file, options) {
    if (!policy?.can_create_job) throw new Error(policy?.unavailable_reason || 'Transcrição temporariamente indisponível')
    let current = session
    if (!current) {
      current = await guestService.createSession()
      saveSession(current)
    }
    const created = await guestService.createJob(current.guest_token, file, options)
    saveSession({ ...current, resultId: created.id })
    return created
  }

  async function claim() {
    try {
      setBusy(true)
      await guestService.claim(session.guest_token)
      const id = session.resultId
      saveSession(null)
      toast.success('Resultado salvo na sua conta')
      navigate(`/transcriptions/${id}`)
    } catch (failure) {
      setError(failure.message)
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    try {
      setBusy(true)
      await guestService.delete(session.guest_token, session.resultId)
      saveSession({ ...session, resultId: null, spent: true })
      setResult(null)
      toast.success('Resultado temporário excluído')
    } catch (failure) {
      setError(failure.message)
    } finally {
      setBusy(false)
    }
  }

  if ((authenticated || !showUpload) && !session?.resultId && !error) return null

  return <div className="max-w-6xl mx-auto space-y-6">
      {error && <Card><CardContent><div role="alert">{error}<Button variant="outline" onClick={() => setRetry((n) => n + 1)}>Tentar novamente</Button></div></CardContent></Card>}
      {showUpload && !authenticated && !policy && !error && <p role="status">Carregando limites...</p>}
      {session?.resultId ? <Card>
        <CardHeader><CardTitle>{authenticated ? 'Salve sua transcrição anterior' : 'Resultado da transcrição'}</CardTitle></CardHeader>
        <CardContent className="space-y-4">
        {!result ? <p role="status">Carregando resultado...</p> : <>
          <ProcessingStatus status={result.status} errorMessage={result.error_message} />
          {result.status === 'completed' && result.segments?.map((segment, index) => <p key={index}>
            [{segment.start}s–{segment.end}s] {segment.text}
          </p>)}
          <div className="flex gap-3">
            {authenticated && <Button onClick={claim} loading={busy}>Salvar na minha conta</Button>}
            <Button variant="outline" onClick={remove} disabled={busy || ['queued', 'processing'].includes(result.status)}>Excluir resultado temporário</Button>
          </div>
        </>}
      </CardContent></Card> : showUpload && !authenticated && policy && !session?.spent && <NewTranscription guestPolicy={policy} onCreate={createJob} onCreated={() => {}} />}
      {!authenticated && policy && <div className="text-sm text-gray-500 space-y-2">
        <p>Até {formatNumber(policy.max_upload_mb)} MB e {formatCount(Math.floor(policy.max_audio_seconds / 60), 'minuto', 'minutos')}. {formatCount(policy.jobs_per_session, 'transcrição', 'transcrições')} por sessão; o resultado fica nesta aba por {formatCount(policy.retention_hours, 'hora', 'horas')}.</p>
        <p><Link className="text-primary-700" to="/login?saveGuest=1">Entrar</Link> ou <Link className="text-primary-700" to="/signup?saveGuest=1">criar conta</Link> para salvar suas reuniões.</p>
      </div>}
      {session?.spent && <p>Resultado excluído. Crie uma conta para continuar; excluir não reinicia a cota de visitante.</p>}
  </div>
}
