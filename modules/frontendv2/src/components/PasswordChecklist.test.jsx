import { afterEach, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import PasswordChecklist from './PasswordChecklist'

afterEach(cleanup)

it('shows only the minimum returned by the service and neutral confirmation', () => {
  render(<PasswordChecklist status={{ passwordPolicy: { customStrengthOptions: { minPasswordLength: 8 } }, meetsMinPasswordLength: false }} password="" confirmation="" id="policy" />)
  expect(screen.getByText('Pelo menos 8 caracteres')).toBeTruthy()
  expect(screen.queryByText(/maiúscula|minúscula|número|especial/)).toBeNull()
  expect(screen.getByText('As senhas coincidem').textContent).toContain('Pendente:')
})

it('uses SDK status for optional criteria and updates confirmation without color-only feedback', () => {
  const status = { passwordPolicy: { customStrengthOptions: { minPasswordLength: 8, containsNumericCharacter: true } }, meetsMinPasswordLength: true, containsNumericCharacter: false }
  const view = render(<PasswordChecklist status={status} password="password" confirmation="" />)
  expect(screen.getByText('Pelo menos 8 caracteres').textContent).toContain('Atendido:')
  expect(screen.getByText('Contém número').textContent).toContain('Pendente:')
  view.rerender(<PasswordChecklist status={{ ...status, containsNumericCharacter: true }} password="password1" confirmation="password1" />)
  expect(screen.getByText('Contém número').textContent).toContain('Atendido:')
  expect(screen.getByText('As senhas coincidem').textContent).toContain('Atendido:')
  expect(screen.getByRole('list').getAttribute('aria-live')).toBe('polite')
})
