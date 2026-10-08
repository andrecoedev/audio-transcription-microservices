import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import HelpPopover from './HelpPopover'

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('supports mouse hover, keyboard focus and Escape without submitting forms', () => {
  render(<HelpPopover label="Preferências">Explicação útil</HelpPopover>)
  const button = screen.getByRole('button', { name: 'Ajuda: Preferências' })
  expect(button.type).toBe('button')
  fireEvent.mouseEnter(button.parentElement)
  expect(screen.getByRole('tooltip').textContent).toBe('Explicação útil')
  fireEvent.mouseLeave(button.parentElement)
  expect(screen.queryByRole('tooltip')).toBeNull()
  fireEvent.focus(button)
  expect(button.getAttribute('aria-describedby')).toBe(screen.getByRole('tooltip').id)
  fireEvent.keyDown(button, { key: 'Escape' })
  expect(screen.queryByRole('tooltip')).toBeNull()
})

it('supports tapping and dismisses the explanation on an outside interaction', () => {
  render(<HelpPopover label="Privacidade">Dados protegidos</HelpPopover>)
  fireEvent.click(screen.getByRole('button'))
  expect(screen.getByRole('tooltip')).toBeTruthy()
  fireEvent.pointerDown(document.body)
  expect(screen.queryByRole('tooltip')).toBeNull()
})

it('clamps help inside a narrow viewport and opens above when there is no space below', () => {
  vi.stubGlobal('innerWidth', 390)
  vi.stubGlobal('innerHeight', 600)
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function () {
    return this.getAttribute('role') === 'tooltip'
      ? { height: 150 }
      : { left: 360, top: 560, bottom: 584 }
  })
  render(<HelpPopover label="Serviço">Ajuda acessível</HelpPopover>)
  fireEvent.click(screen.getByRole('button'))
  const tip = screen.getByRole('tooltip')
  expect(tip.style.left).toBe('118px')
  expect(tip.style.top).toBe('402px')
  expect(tip.style.width).toBe('256px')
})
