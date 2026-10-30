import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { Save } from 'lucide-react'
import Button from './Button'
import StatusBadge from './StatusBadge'
import Card, { CardContent, CardHeader, CardTitle } from './Card'
import PageHeader from './PageHeader'

afterEach(cleanup)

it('names the action being performed while keeping a loading button disabled', () => {
  render(<Button loading loadingLabel="Salvando…">Salvar</Button>)
  const button = screen.getByRole('button', { name: 'Salvando…' })
  expect(button.disabled).toBe(true)
  expect(button.getAttribute('aria-busy')).toBe('true')
})

it('preserves disabled/loading buttons, accessible names and form submission', () => {
  const submit = vi.fn(event => event.preventDefault())
  const { rerender } = render(<form onSubmit={submit}><Button type="submit" icon={Save}>Salvar</Button></form>)
  fireEvent.click(screen.getByRole('button', { name: 'Salvar' }))
  expect(submit).toHaveBeenCalledOnce()
  rerender(<form onSubmit={submit}><Button type="submit" loading>Salvar</Button></form>)
  const busy = screen.getByRole('button', { name: 'Carregando...' })
  expect(busy.disabled).toBe(true)
  expect(busy.getAttribute('aria-busy')).toBe('true')
  fireEvent.click(busy)
  expect(submit).toHaveBeenCalledOnce()
})

it.each([
  ['queued', 'Na fila'], ['processing', 'Processando'],
  ['completed', 'Concluída'], ['failed', 'Falhou'], ['unknown', 'Status indisponível'],
])('communicates %s with text instead of color alone', (status, text) => {
  render(<StatusBadge status={status} />)
  expect(screen.getByText(text)).toBeTruthy()
})

it('keeps long headings and contextual actions in the shared page structure', () => {
  render(<><PageHeader title={'Reunião '.repeat(40)} description="Descrição curta">
    <Button>Atualizar</Button>
  </PageHeader><Card aria-label="Resultado"><CardHeader><CardTitle>Transcrição</CardTitle></CardHeader>
    <CardContent>Conteúdo preservado</CardContent></Card></>)
  expect(screen.getByRole('heading', { level: 1 }).textContent).toContain('Reunião')
  expect(screen.getByRole('button', { name: 'Atualizar' })).toBeTruthy()
  expect(screen.getByLabelText('Resultado').textContent).toContain('Conteúdo preservado')
})
