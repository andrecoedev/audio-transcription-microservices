import { Link } from 'react-router-dom'
import { FileAudio } from 'lucide-react'
import Card, { CardContent } from '../components/Card'
import PageHeader from '../components/PageHeader'
import { useAuthStore } from '../stores/authStore'
import Dashboard from './Dashboard'
import Guest from './Guest'

export default function Home() {
  const authenticated = useAuthStore((state) => state.isAuthenticated)
  return <div className="mx-auto max-w-6xl space-y-6">
    <PageHeader title="Início" description="Seu espaço para transcrever áudios e revisar reuniões." />
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-6">
        <div className="flex min-w-0 items-start gap-4">
          <FileAudio aria-hidden="true" className="h-10 w-10 shrink-0 rounded-lg bg-primary-50 p-2 text-primary-700" />
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Transforme seu áudio em texto</h2>
            <p className="mt-1 max-w-xl text-sm text-gray-600">Envie um arquivo em Nova Transcrição e acompanhe o processamento.</p>
            {!authenticated && <p className="mt-2 text-sm text-gray-500">Experimente como visitante. Entre ou crie uma conta quando quiser salvar seu trabalho.</p>}
          </div>
        </div>
        <Link to="/new-transcription" className="btn btn-primary">Iniciar uma transcrição</Link>
      </CardContent>
    </Card>
    <Guest showUpload={false} />
    {authenticated && <Dashboard />}
  </div>
}
