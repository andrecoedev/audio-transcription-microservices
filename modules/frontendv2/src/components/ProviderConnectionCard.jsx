import { useState } from 'react'
import Button from './Button'
import Card, { CardContent, CardHeader, CardTitle } from './Card'

export default function ProviderConnectionCard({ provider, details, credential, storageAvailable, busy, saving, value, onChange, onSave, onRemove }) {
  const [replacing, setReplacing] = useState(false)
  const [confirmRemoval, setConfirmRemoval] = useState(false)
  const name = provider === 'assemblyai' ? 'AssemblyAI' : 'Gemini'
  const connected = credential.configured
  const canUse = details.available && details.allowed && details.configured
  const editing = !connected || replacing
  const date = credential.updated_at ? new Date(credential.updated_at) : null
  const submit = async (event) => {
    event.preventDefault()
    if (await onSave()) setReplacing(false)
  }
  const remove = async () => {
    if (await onRemove()) {
      setConfirmRemoval(false)
      setReplacing(false)
    }
  }
  return <Card>
    <CardHeader><div className="flex flex-wrap items-center justify-between gap-2">
      <CardTitle>{provider === 'assemblyai' ? 'Transcrição de áudio' : 'Resumos inteligentes'}</CardTitle>
      <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${connected && canUse ? 'bg-primary-50 text-primary-800' : 'bg-gray-100 text-gray-600'}`}>{connected ? 'Conectado' : 'Não conectado'}</span>
    </div></CardHeader>
    <CardContent className="space-y-4">
      <div><h3 className="font-semibold text-gray-900">{connected ? `${name} · Sua própria conta` : name}</h3>
        <p className="mt-1 text-sm text-gray-600">{provider === 'assemblyai' ? 'Transforme seu áudio em texto, com detecção de falantes quando ativada.' : 'Gere resumos, tópicos, decisões e tarefas a partir da sua reunião.'}</p>
        <p className="mt-2 text-sm text-gray-600">Conecte uma chave da sua conta {name}. O consumo é cobrado pelo serviço diretamente na sua conta, não usa a franquia da USAGI.</p>
      </div>
      {details.credential_source === 'platform' && <div className="rounded-lg bg-primary-50 p-3 text-sm text-primary-900">Fornecido pela USAGI está disponível para esta conta. Conectar sua própria chave passa a usar sua conta {name}.</div>}
      {connected && <div className="rounded-lg border border-primary-100 bg-primary-50 p-3 text-sm text-primary-900">
        <p className="font-medium">Credencial própria salva</p>
        <p>Chave salva com segurança. A validade e o acesso serão verificados ao usar o serviço.</p>
        {date && !Number.isNaN(date.getTime()) && <p className="mt-1 text-xs">Atualizada em {date.toLocaleString('pt-BR')}</p>}
      </div>}
      {!canUse && <p role="status" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">Indisponível no momento. {!storageAvailable ? 'O armazenamento seguro está indisponível. Tente novamente mais tarde ou procure o suporte da USAGI.' : connected ? 'Atualize as configurações. Se continuar, procure o suporte da USAGI.' : `Conecte sua conta ${name} para habilitar este serviço.`}</p>}
      {storageAvailable && editing && <form onSubmit={submit} className="space-y-3">
        <label className="block text-sm font-medium text-gray-700" htmlFor={`credential-${provider}`}>{replacing ? 'Nova chave de API' : 'Chave de API'}
          <input id={`credential-${provider}`} aria-label={`Credencial ${name}`} type="password" autoComplete="off" spellCheck={false}
            maxLength={4096} disabled={busy} className="input mt-2" value={value} onChange={(event) => onChange(event.target.value)} placeholder={`Cole sua chave ${name}`} />
        </label>
        {replacing && <p className="text-sm text-amber-900">Substituir a chave pode impedir a conclusão de trabalhos que ainda aguardam processamento com a chave anterior.</p>}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={!value || busy} loading={saving}>{connected ? 'Salvar nova chave' : 'Salvar credencial'}</Button>
          {replacing && <Button type="button" variant="ghost" disabled={busy} onClick={() => { onChange(''); setReplacing(false) }}>Cancelar</Button>}
        </div>
      </form>}
      {connected && !confirmRemoval && <div className="flex flex-wrap gap-2">
        {!replacing && storageAvailable && <Button variant="outline" disabled={busy} onClick={() => setReplacing(true)}>Substituir chave {name}</Button>}
        <Button variant="ghost" disabled={busy} onClick={() => { onChange(''); setConfirmRemoval(true) }}>Remover credencial {name}</Button>
      </div>}
      {confirmRemoval && <div role="group" aria-label={`Confirmar remoção ${name}`} className="space-y-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950">
        <p className="font-medium">Remover a chave {name} da USAGI?</p>
        <p>Trabalhos aguardando essa chave poderão falhar. Isso não revoga a chave no serviço nem interrompe chamadas já iniciadas.</p>
        <div className="flex flex-wrap gap-2"><Button variant="danger" disabled={busy} loading={saving} onClick={remove}>Confirmar remoção {name}</Button>
          <Button variant="outline" disabled={busy} onClick={() => setConfirmRemoval(false)}>Cancelar remoção</Button></div>
      </div>}
      <p className="text-xs text-gray-500">A chave não será exibida novamente. Salvar não testa a chave no serviço externo.</p>
    </CardContent>
  </Card>
}
