import { useState } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

import ProviderConnectionCard from './ProviderConnectionCard'

afterEach(cleanup)

function setup({
  provider = 'assemblyai',
  details = { available: true, allowed: true, configured: true, credential_source: 'platform', platform_access: true, byok_allowed: true },
  credential = { configured: false },
  storageAvailable = true,
  busy = false,
  saving = false,
  onSave = vi.fn(async () => true),
  onRemove = vi.fn(async () => true),
} = {}) {
  const onChange = vi.fn()
  const result = render(<ProviderConnectionCard provider={provider} details={details} credential={credential}
    storageAvailable={storageAvailable} busy={busy} saving={saving} value="" onChange={onChange}
    onSave={onSave} onRemove={onRemove} />)
  return { ...result, onChange, onSave, onRemove }
}

it('shows a compact provider heading and opens the key form only after an explicit click', () => {
  setup()

  expect(screen.getByRole('heading', { name: 'AssemblyAI' })).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Conectar minha API AssemblyAI' })).toBeTruthy()
  expect(screen.queryByLabelText('Credencial AssemblyAI')).toBeNull()
  expect(screen.getByLabelText('Disponibilidade AssemblyAI').textContent).toBe('USAGI: habilitado')

  fireEvent.click(screen.getByRole('button', { name: 'Conectar minha API AssemblyAI' }))
  expect(screen.getByLabelText('Credencial AssemblyAI').type).toBe('password')
  expect(screen.getByRole('button', { name: 'Salvar credencial' }).disabled).toBe(true)
})

it('keeps platform entitlement separate from key storage and still offers own-key setup when platform access is off', () => {
  setup({ details: { available: true, allowed: false, configured: false, credential_source: null, platform_access: false, byok_allowed: true } })

  expect(screen.getByLabelText('Disponibilidade AssemblyAI').textContent).toBe('USAGI: não habilitado para esta conta')
  expect(screen.getByRole('button', { name: 'Conectar minha API AssemblyAI' }).disabled).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: 'Conectar minha API AssemblyAI' }))
  expect(screen.getByLabelText('Credencial AssemblyAI')).toBeTruthy()
})

it('disables own-key setup when secure storage is unavailable and gives a short actionable message', () => {
  setup({ storageAvailable: false })

  expect(screen.getByRole('button', { name: 'Conectar minha API AssemblyAI' }).disabled).toBe(true)
  expect(screen.getByRole('status').textContent).toMatch(/procure o suporte da USAGI/i)
  expect(screen.queryByText(/credential_storage_available|credential_storage/)).toBeNull()
})

it('does not treat missing platform entitlement as an unsupported integration', () => {
  setup({ details: { available: true, allowed: false, configured: false, credential_source: null, platform_access: false, byok_allowed: true } })

  expect(screen.getByRole('button', { name: 'Conectar minha API AssemblyAI' }).disabled).toBe(false)
  expect(screen.queryByText('Esta integração não está disponível nesta versão.')).toBeNull()
})

it('disables credential setup when the integration is unsupported', () => {
  setup({ details: { available: false, allowed: false, configured: false, credential_source: null, platform_access: false } })

  expect(screen.getByText('Esta integração não está disponível nesta versão.')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Conectar minha API AssemblyAI' }).disabled).toBe(true)
  expect(screen.queryByLabelText('Credencial AssemblyAI')).toBeNull()
})

it('clears the draft when a disconnected form is cancelled', () => {
  const { onChange } = setup()
  fireEvent.click(screen.getByRole('button', { name: 'Conectar minha API AssemblyAI' }))
  fireEvent.change(screen.getByLabelText('Credencial AssemblyAI'), { target: { value: 'temporary-secret' } })
  fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))

  expect(onChange).toHaveBeenLastCalledWith('')
  expect(screen.queryByLabelText('Credencial AssemblyAI')).toBeNull()
})

it('allows connected credentials to be replaced, cancelled, saved write-only, or removed after confirmation', async () => {
  const onSave = vi.fn(async () => true)
  const onRemove = vi.fn(async () => true)
  const onChange = vi.fn()
  function ControlledCard() {
    const [value, setValue] = useState('')
    return <ProviderConnectionCard provider="gemini"
      details={{ available: true, allowed: false, configured: false, credential_source: null, platform_access: false, byok_allowed: true }}
      credential={{ configured: true, updated_at: '2026-01-02T03:04:00Z' }} storageAvailable busy={false} saving={false}
      value={value} onChange={(next) => { onChange(next); setValue(next) }} onSave={onSave} onRemove={onRemove} />
  }
  render(<ControlledCard />)

  expect(screen.getByRole('heading', { name: 'Gemini' })).toBeTruthy()
  expect(screen.getByText('Credencial salva')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Ajuda: Gemini' }))
  expect(screen.getByRole('tooltip').textContent).toMatch(/nunca voltam à interface/)
  expect(screen.getByRole('tooltip').textContent).toMatch(/Salvar não testa a conexão/)
  fireEvent.click(screen.getByRole('button', { name: 'Ajuda: Gemini' }))
  expect(screen.getByRole('button', { name: 'Substituir chave Gemini' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Substituir chave Gemini' }))
  fireEvent.change(screen.getByLabelText('Credencial Gemini'), { target: { value: 'replacement-secret' } })
  fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
  expect(onChange).toHaveBeenLastCalledWith('')
  expect(screen.queryByLabelText('Credencial Gemini')).toBeNull()

  fireEvent.click(screen.getByRole('button', { name: 'Substituir chave Gemini' }))
  fireEvent.change(screen.getByLabelText('Credencial Gemini'), { target: { value: 'replacement-secret' } })
  fireEvent.click(screen.getByRole('button', { name: 'Salvar nova chave' }))
  await screen.findByRole('button', { name: 'Substituir chave Gemini' })
  expect(onSave).toHaveBeenCalledTimes(1)
  expect(screen.queryByText('replacement-secret')).toBeNull()
  expect(screen.queryByLabelText('Credencial Gemini')).toBeNull()

  fireEvent.click(screen.getByRole('button', { name: 'Remover credencial Gemini' }))
  expect(screen.getByRole('group', { name: 'Confirmar remoção Gemini' }).textContent).toMatch(/não revoga a chave no serviço externo/)
  fireEvent.click(screen.getByRole('button', { name: 'Cancelar remoção' }))
  expect(onRemove).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Remover credencial Gemini' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirmar remoção Gemini' }))
  await waitFor(() => expect(screen.queryByRole('group', { name: 'Confirmar remoção Gemini' })).toBeNull())
  expect(onRemove).toHaveBeenCalledTimes(1)
})

it('keeps deletion available when secure storage is unavailable because deleting does not need decryption', async () => {
  const onRemove = vi.fn(async () => true)
  setup({ credential: { configured: true }, storageAvailable: false, onRemove })

  expect(screen.getByRole('button', { name: 'Remover credencial AssemblyAI' }).disabled).toBe(false)
  expect(screen.getByRole('button', { name: 'Substituir chave AssemblyAI' }).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Remover credencial AssemblyAI' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirmar remoção AssemblyAI' }))

  await waitFor(() => expect(onRemove).toHaveBeenCalledTimes(1))
  await waitFor(() => expect(screen.queryByRole('group', { name: 'Confirmar remoção AssemblyAI' })).toBeNull())
})

it('fails closed for Free when BYOK permission is false or missing but keeps removal available', async () => {
  const onSave = vi.fn(async () => true)
  const onRemove = vi.fn(async () => true)
  setup({ details: { available: true, allowed: false, configured: false, credential_source: 'user', platform_access: false, byok_allowed: false },
    credential: { configured: true }, onSave, onRemove })

  expect(screen.getByRole('status').textContent).toBe('Chave própria exige plano autorizado ou acesso beta.')
  expect(screen.getByRole('button', { name: 'Substituir chave AssemblyAI' }).disabled).toBe(true)
  expect(screen.getByRole('button', { name: 'Remover credencial AssemblyAI' }).disabled).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: 'Substituir chave AssemblyAI' }))
  expect(screen.queryByLabelText('Credencial AssemblyAI')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Remover credencial AssemblyAI' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirmar remoção AssemblyAI' }))
  await waitFor(() => expect(onRemove).toHaveBeenCalledOnce())
  expect(onSave).not.toHaveBeenCalled()

  cleanup()
  setup({ details: { available: true, allowed: true, configured: true, credential_source: 'platform' } })
  expect(screen.getByRole('button', { name: 'Conectar minha API AssemblyAI' }).disabled).toBe(true)
  expect(screen.getByText('Chave própria exige plano autorizado ou acesso beta.')).toBeTruthy()
})
