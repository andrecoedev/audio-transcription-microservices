import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import ProcessingStatus from './ProcessingStatus'

describe('ProcessingStatus', () => {
  it('shows queued work without inventing percentage or estimated time', () => {
    render(<ProcessingStatus status="queued" />)
    expect(screen.getByRole('heading', { name: 'Na fila' })).toBeTruthy()
    expect(screen.getByText('Transcrição em andamento')).toBeTruthy()
    expect(screen.queryByText(/%|minuto|segundo/i)).toBeNull()
    expect(screen.queryByText(/áudio processado/i)).toBeNull()
  })

  it('shows the actual processing and completed steps', () => {
    const { rerender } = render(<ProcessingStatus status="processing" />)
    expect(screen.getByText('Processando')).toBeTruthy()
    expect(document.querySelector('li[aria-current="step"]').textContent).toContain('Transcrição em andamento')
    rerender(<ProcessingStatus status="completed" />)
    expect(screen.getByText('Concluída')).toBeTruthy()
    expect(document.querySelector('li[aria-current="step"]').textContent).toContain('Transcrição concluída')
  })

  it('shows the API error message on failed status', () => {
    render(<ProcessingStatus status="failed" errorMessage="Job rejeitado" />)
    expect(screen.getByRole('alert').textContent).toContain('Job rejeitado')
  })

  it('uses upload progress only for the actual upload request', () => {
    render(<ProcessingStatus status="uploading" uploadProgress={37} />)
    expect(screen.getByRole('progressbar', { name: 'Progresso do envio' }).value).toBe(37)
  })
})

afterEach(cleanup)
