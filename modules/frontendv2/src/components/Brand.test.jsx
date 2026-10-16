import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import Brand from './Brand.jsx'
import { applyBrowserTitle, brand, browserTitle } from '../brand.js'

afterEach(cleanup)

describe('Brand', () => {
  it('shows the company, Japanese name, and product on separate lines', () => {
    render(<Brand />)

    expect(screen.getByText(brand.company)).toBeTruthy()
    expect(screen.getByText(brand.jp).getAttribute('lang')).toBe('ja')
    expect(screen.getByText(brand.product)).toBeTruthy()
    expect(browserTitle).toBe('USAGI — Transcrição')
  })

  it('omits only the product in compact mode', () => {
    render(<Brand compact />)

    expect(screen.getByText(brand.company)).toBeTruthy()
    expect(screen.getByText(brand.jp)).toBeTruthy()
    expect(screen.queryByText(brand.product)).toBeNull()
  })

  it('applies the centralized browser title', () => {
    applyBrowserTitle(document)

    expect(document.title).toBe(browserTitle)
    expect(document.title).not.toMatch(/\p{Extended_Pictographic}/u)
  })
})
