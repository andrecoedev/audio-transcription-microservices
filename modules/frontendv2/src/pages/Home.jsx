import { Link } from 'react-router-dom'
import { FileAudio, Play } from 'lucide-react'
import Card, { CardContent } from '../components/Card'
import PageHeader from '../components/PageHeader'
import { useAuthStore } from '../stores/authStore'
import Dashboard from './Dashboard'
import Guest from './Guest'

export default function Home() {
  const authenticated = useAuthStore((state) => state.isAuthenticated)
  return <div className="mx-auto max-w-6xl space-y-6">
    <PageHeader title="Início" description="Acesse suas transcrições e reuniões ou comece uma nova." />
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-6">
        <div className="flex min-w-0 items-start gap-4">
          <FileAudio aria-hidden="true" className="h-10 w-10 shrink-0 rounded-lg bg-primary-50 p-2 text-primary-700" />
          <div>
            <h2 className="text-lg font-semibold text-gray-900">{authenticated ? 'Transforme seu áudio em texto' : 'Conheça a experiência de transcrição'}</h2>
            <p className="mt-1 max-w-xl text-sm text-gray-600">{authenticated ? 'Envie um áudio para criar uma transcrição e revisar o conteúdo.' : 'Explore uma reunião com dados de exemplo. Ela não foi criada a partir de um áudio seu.'}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link to="/new-transcription" className="btn-primary inline-flex items-center gap-2">{authenticated ? 'Nova transcrição' : <><Play aria-hidden="true" className="h-4 w-4" />Ver demonstração</>}</Link>
          {!authenticated && <Link to="/login?returnTo=%2Fnew-transcription" className="btn-secondary">Entrar</Link>}
        </div>
      </CardContent>
    </Card>
    <Guest />
    {authenticated && <>
      <nav aria-label="Suas áreas" className="flex flex-wrap gap-x-5 gap-y-2 text-sm font-medium">
        <Link className="text-primary-700 hover:underline" to="/transcriptions">Ver minhas transcrições</Link>
        <Link className="text-primary-700 hover:underline" to="/meetings">Ver minhas reuniões</Link>
      </nav>
      <Dashboard />
    </>}
  </div>
}
