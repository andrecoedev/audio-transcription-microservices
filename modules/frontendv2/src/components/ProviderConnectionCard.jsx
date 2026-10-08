import { useState } from 'react'

import Button from './Button'
import Card, { CardContent, CardHeader, CardTitle } from './Card'
import HelpPopover from './HelpPopover'

const providerNames = { assemblyai: 'AssemblyAI', gemini: 'Gemini' }

export default function ProviderConnectionCard({ provider, details, credential, storageAvailable, busy, saving, value, onChange, onSave, onRemove }) {
  const [editing, setEditing] = useState(false)
  const [confirmRemoval, setConfirmRemoval] = useState(false)
  const name = providerNames[provider] || provider
  const connected = Boolean(credential.configured)
  const supported = Boolean(details.available)
  const platformAccess = typeof details.platform_access === 'boolean'
    ? details.platform_access
    : details.credential_source === 'platform' && Boolean(details.allowed)
  const canSave = supported && storageAvailable && Boolean(value) && !busy
  const updatedAt = credential.updated_at ? new Date(credential.updated_at) : null

  const cancelEditing = () => {
    onChange('')
    setEditing(false)
  }

  const submit = async (event) => {
    event.preventDefault()
    if (!canSave) return
    if (await onSave()) {
      onChange('')
      setEditing(false)
    }
  }

  const remove = async () => {
    if (await onRemove()) {
      onChange('')
      setConfirmRemoval(false)
      setEditing(false)
    }
  }

  const helpText = provider === 'assemblyai'
    ? `Use sua chave ${name} para transcrever áudio. O uso é cobrado diretamente pela ${name}.`
    : `Use sua chave ${name} para gerar resumos, decisões e tarefas. O uso é cobrado diretamente pela ${name}.`

  return <Card>
    <CardHeader>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <CardTitle>{name}</CardTitle>
          <HelpPopover label={name}>{helpText} As chaves são criptografadas e nunca voltam à interface. Salvar não testa a conexão com o serviço.</HelpPopover>
        </div>
        <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${connected ? 'bg-primary-50 text-primary-800' : 'bg-gray-100 text-gray-600'}`}>
          {connected ? 'Credencial salva' : 'Sem credencial própria'}
        </span>
      </div>
    </CardHeader>

    <CardContent className="space-y-3">
      <p className="text-sm text-gray-600">Cobrança na sua conta {name}, fora da franquia USAGI.</p>

      <div className="space-y-1 text-sm" aria-label={`Disponibilidade ${name}`}>
        <p className="text-gray-700">USAGI: <span className="font-medium">{platformAccess ? 'habilitado' : 'não habilitado para esta conta'}</span></p>
        {!supported && <p className="text-amber-800">Esta integração não está disponível nesta versão.</p>}
      </div>

      {connected && updatedAt && !Number.isNaN(updatedAt.getTime()) && <p className="text-xs text-gray-500">Atualizada em {updatedAt.toLocaleString('pt-BR')}</p>}

      {!storageAvailable && <p role="status" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
        Não é possível conectar uma chave agora. Procure o suporte da USAGI.
      </p>}

      {storageAvailable && !supported && <p role="status" className="text-sm text-amber-800">Não é possível salvar uma chave para esta integração agora.</p>}

      {editing && supported && storageAvailable && <form onSubmit={submit} className="space-y-3">
        <label className="block text-sm font-medium text-gray-700" htmlFor={`credential-${provider}`}>
          {connected ? 'Nova chave de API' : 'Chave de API'}
          <input id={`credential-${provider}`} aria-label={`Credencial ${name}`} type="password" autoComplete="off" spellCheck={false}
            maxLength={4096} disabled={busy} className="input mt-2" value={value}
            onChange={(event) => onChange(event.target.value)} placeholder={`Cole sua chave ${name}`} />
        </label>
        {connected && <p className="text-sm text-amber-900">A chave anterior pode deixar de funcionar para trabalhos ainda não concluídos.</p>}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={!canSave} loading={saving}>{connected ? 'Salvar nova chave' : 'Salvar credencial'}</Button>
          <Button type="button" variant="ghost" disabled={busy} onClick={cancelEditing}>Cancelar</Button>
        </div>
      </form>}

      {!editing && !confirmRemoval && <div className="flex flex-wrap gap-2">
        {!connected && <Button type="button" aria-label={`Conectar minha API ${name}`} disabled={busy || !supported || !storageAvailable}
          onClick={() => setEditing(true)}>Conectar minha API</Button>}
        {connected && <>
          <Button type="button" variant="outline" disabled={busy || !supported || !storageAvailable}
            onClick={() => setEditing(true)}>Substituir chave {name}</Button>
          <Button type="button" variant="ghost" disabled={busy}
            onClick={() => { onChange(''); setConfirmRemoval(true) }}>Remover credencial {name}</Button>
        </>}
      </div>}

      {confirmRemoval && <div role="group" aria-label={`Confirmar remoção ${name}`} className="space-y-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950">
        <p className="font-medium">Remover a credencial {name} da USAGI?</p>
        <p>Trabalhos que ainda dependem dela podem falhar. Isso não revoga a chave no serviço externo nem interrompe chamadas já iniciadas.</p>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="danger" disabled={busy} loading={saving} onClick={remove}>Confirmar remoção {name}</Button>
          <Button type="button" variant="outline" disabled={busy} onClick={() => setConfirmRemoval(false)}>Cancelar remoção</Button>
        </div>
      </div>}
    </CardContent>
  </Card>
}
