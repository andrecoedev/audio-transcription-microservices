const STATUS = {
  queued: { label: 'Na fila', current: 0 },
  processing: { label: 'Processando', current: 1 },
  completed: { label: 'Concluída', current: 2 },
  failed: { label: 'Falhou', current: -1 },
}

const STEPS = ['Na fila', 'Transcrição em andamento', 'Transcrição concluída']

export default function ProcessingStatus({ status, errorMessage, uploadProgress }) {
  if (status === 'uploading') return <section aria-label="Status do envio" className="mt-4 rounded-lg bg-gray-50 p-4">
    <div className="mb-2 flex justify-between text-sm"><span className="text-gray-700">Enviando arquivo</span><span className="font-medium text-gray-900">{uploadProgress}%</span></div>
    <progress className="h-2 w-full accent-primary-700" max="100" value={uploadProgress} aria-label="Progresso do envio" />
  </section>
  const state = STATUS[status]
  if (!state) return <p role="status">Status: {status || 'indisponível'}</p>

  if (status === 'failed') return <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
    <p className="font-medium">O processamento falhou.</p>
    <p className="mt-1">{errorMessage || 'Tente enviar o áudio novamente.'}</p>
  </div>

  return <section aria-label="Status do processamento" className="rounded-lg border border-gray-200 bg-white p-5">
    <h2 className="mb-4 text-sm font-semibold text-gray-900">{state.label}</h2>
    <ol className="space-y-3">
      {STEPS.map((step, index) => {
        const complete = state.current > index
        const active = state.current === index
        return <li key={step} aria-current={active ? 'step' : undefined} className={`flex items-center gap-3 text-sm ${active ? 'font-medium text-gray-900' : complete ? 'text-primary-800' : 'text-gray-500'}`}>
          <span aria-hidden="true" className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs ${complete ? 'bg-primary-100 text-primary-800' : active ? 'bg-primary-700 text-white' : 'bg-gray-100 text-gray-500'}`}>{complete ? '✓' : index + 1}</span>
          {step}
        </li>
      })}
    </ol>
    <p className="mt-4 text-sm text-gray-600">O status é atualizado pelo serviço de transcrição. Você pode sair desta página.</p>
  </section>
}
