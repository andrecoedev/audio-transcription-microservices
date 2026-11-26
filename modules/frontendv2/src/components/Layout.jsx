import { useCallback, useEffect, useRef, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import Navbar from './Navbar'
import Sidebar from './Sidebar'
import { useAuthStore } from '../stores/authStore'

const focusableSelector = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'

export default function Layout() {
  const [menuOpen, setMenuOpen] = useState(false)
  const { pathname } = useLocation()
  const authenticated = useAuthStore(state => state.isAuthenticated)
  const publicHome = pathname === '/' && !authenticated
  const menuButtonRef = useRef(null)
  const drawerRef = useRef(null)
  const mainRef = useRef(null)
  const navbarRef = useRef(null)
  const desktopSidebarRef = useRef(null)
  const skipLinkRef = useRef(null)

  const closeMenu = useCallback((returnFocus = true) => {
    setMenuOpen(false)
    if (returnFocus) requestAnimationFrame(() => menuButtonRef.current?.focus())
  }, [])

  const navigateFromMenu = () => {
    closeMenu(false)
    requestAnimationFrame(() => mainRef.current?.focus())
  }

  useEffect(() => { closeMenu(false) }, [pathname, closeMenu])

  useEffect(() => {
    if (!window.matchMedia) return undefined
    const media = window.matchMedia('(min-width: 861px)')
    const handleBreakpoint = (event) => { if (event.matches) closeMenu(false) }
    if (media.addEventListener) media.addEventListener('change', handleBreakpoint)
    else media.addListener?.(handleBreakpoint)
    return () => {
      if (media.removeEventListener) media.removeEventListener('change', handleBreakpoint)
      else media.removeListener?.(handleBreakpoint)
    }
  }, [closeMenu])

  useEffect(() => {
    if (!menuOpen) return
    const background = [mainRef.current, navbarRef.current, desktopSidebarRef.current, skipLinkRef.current]
    const previousInert = background.map((node) => node?.inert ?? false)
    const previousOverflow = document.body.style.overflow
    background.forEach((node) => { if (node) node.inert = true })
    document.body.style.overflow = 'hidden'
    const focusables = () => Array.from(drawerRef.current?.querySelectorAll(focusableSelector) || [])
    const focusFrame = requestAnimationFrame(() => focusables()[0]?.focus())
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        closeMenu()
        return
      }
      if (event.key !== 'Tab') return
      const items = focusables()
      if (!items.length) { event.preventDefault(); drawerRef.current?.focus(); return }
      const first = items[0]
      const last = items[items.length - 1]
      if (event.shiftKey && (document.activeElement === first || !drawerRef.current?.contains(document.activeElement))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && (document.activeElement === last || !drawerRef.current?.contains(document.activeElement))) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      cancelAnimationFrame(focusFrame)
      document.removeEventListener('keydown', handleKeyDown)
      background.forEach((node, index) => { if (node) node.inert = previousInert[index] })
      document.body.style.overflow = previousOverflow
    }
  }, [menuOpen, closeMenu])

  const skipLink = <a ref={skipLinkRef} href="#main-content" className="sr-only z-50 rounded-lg bg-surface p-3 focus:not-sr-only focus:absolute">Ir para o conteúdo</a>

  if (publicHome) return <>
    {skipLink}
    <main ref={mainRef} id="main-content" tabIndex={-1}><Outlet /></main>
  </>

  return <div className="flex min-h-screen flex-col bg-canvas min-[861px]:h-dvh min-[861px]:flex-row min-[861px]:overflow-hidden">
    {skipLink}
    <div ref={desktopSidebarRef} className="hidden overflow-y-auto min-[861px]:block"><Sidebar /></div>
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <Navbar ref={menuButtonRef} backgroundRef={navbarRef} expanded={menuOpen} onMenu={() => setMenuOpen(true)} />
      <main ref={mainRef} id="main-content" tabIndex={-1} className="app-main min-w-0 flex-1 min-[861px]:overflow-y-auto">
        <div className="mx-auto max-w-[1080px]"><Outlet /></div>
      </main>
    </div>
    {menuOpen && <div className="fixed inset-0 z-40 flex min-[861px]:hidden">
      <div id="mobile-navigation" ref={drawerRef} role="dialog" aria-modal="true" aria-label="Navegação principal" tabIndex={-1} className="relative z-10 h-full max-h-[100dvh] overflow-y-auto overscroll-contain shadow-xl">
        <Sidebar compact onNavigate={navigateFromMenu} onClose={() => closeMenu()} />
      </div>
      <button type="button" aria-label="Fechar navegação pelo fundo" aria-hidden="true" tabIndex={-1} onClick={() => closeMenu()} className="flex-1 bg-ink/40" />
    </div>}
  </div>
}
