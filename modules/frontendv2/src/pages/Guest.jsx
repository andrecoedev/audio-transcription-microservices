import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import Navbar from '../components/Navbar'
import Button from '../components/Button'
import NewTranscription from './NewTranscription'
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

export default function Guest() {
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
    let active = true
    guestService.policy().then((value) => { if (active) { setPolicy(value); setError('') } })
      .catch(() => { if (active) setError('Não foi possível carregar os limites. Tente novamente.') })
    return () => { active = false }
  }, [retry])

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

  return <>
    <Navbar />
    <main className="max-w-5xl mx-auto p-6 space-y-6">
      <h1 className="text-3xl font-bold">Experimente o USAGI sem conta</h1>
      <p>Transcrição local temporária. Entre ou crie uma conta para salvar o resultado e acessar suas reuniões.</p>
      <div className="flex gap-4 text-primary-700">
        {authenticated ? <Link to="/">Minha conta</Link> : <>
          <Link to="/login?saveGuest=1">Entrar para salvar</Link>
          <Link to="/signup?saveGuest=1">Criar conta para salvar</Link>
        </>}
      </div>
      {policy && <p className="text-sm text-gray-600">
        Até {policy.max_upload_mb} MiB e {policy.max_audio_seconds}s; {policy.jobs_per_session} job(s) por sessão.
        Retenção temporária: {policy.retention_hours}h desde a criação da sessão. Sem diarização nem APIs externas.
        A sessão fica nesta aba; fechar a aba pode impedir a recuperação do resultado.
      </p>}
      {error && <div role="alert">{error}<Button variant="outline" onClick={() => setRetry((n) => n + 1)}>Tentar novamente</Button></div>}
      {!policy && !error && <p role="status">Carregando limites...</p>}
      {session?.resultId ? <section className="space-y-4">
        <h2 className="text-xl font-semibold">Resultado temporário</h2>
        {!result ? <p role="status">Carregando resultado...</p> : <>
          <p>Status: {result.status}</p>
          {result.status === 'failed' && <p role="alert">{result.error_message || 'Processamento falhou'}</p>}
          {result.segments?.map((segment, index) => <p key={index}>
            [{segment.start}s–{segment.end}s] {segment.text}
          </p>)}
          <div className="flex gap-3">
            {authenticated && <Button onClick={claim} loading={busy}>Salvar na minha conta</Button>}
            <Button variant="outline" onClick={remove} disabled={busy || ['queued', 'processing'].includes(result.status)}>Excluir resultado temporário</Button>
          </div>
        </>}
      </section> : policy && !session?.spent && <NewTranscription guestPolicy={policy} onCreate={createJob} onCreated={() => {}} />}
      {session?.spent && <p>Resultado excluído. Crie uma conta para continuar; excluir não reinicia a cota de visitante.</p>}
    </main>
  </>
}
