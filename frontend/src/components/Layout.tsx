import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import { initials } from '../lib/format'
import { CrosshairIcon, FolderIcon, LogOutIcon, MenuIcon, ShieldIcon } from './icons'

/**
 * Authenticated application shell: sidebar navigation, mobile topbar, and the
 * routed content area.
 */
export function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)

  async function handleLogout() {
    // Revoke server-side first so the token cannot be reused, then navigate.
    await logout()
    navigate('/login', { replace: true })
  }

  const navLinks = (
    <nav aria-label="Main navigation">
      <p className="sidebar-section-label">Workspace</p>
      <NavLink to="/projects" onClick={() => setMenuOpen(false)}>
        <FolderIcon size={17} />
        Projects
      </NavLink>
      <NavLink to="/targets" onClick={() => setMenuOpen(false)}>
        <CrosshairIcon size={17} />
        Targets
      </NavLink>
    </nav>
  )

  const userCard = (
    <div className="sidebar-footer">
      <div className="user-menu">
        <span className="user-avatar" aria-hidden="true">
          {initials(user?.email)}
        </span>
        <span className="user-meta">
          <span className="user-email" title={user?.email}>
            {user?.email}
          </span>
          <span className="user-role">{user?.role}</span>
        </span>
        <button
          type="button"
          className="icon-ghost"
          aria-label="Sign out"
          title="Sign out"
          onClick={() => void handleLogout()}
        >
          <LogOutIcon size={16} />
        </button>
      </div>
    </div>
  )

  return (
    <div className="app-shell">
      {menuOpen && (
        <div
          className="app-sidebar-backdrop"
          aria-hidden="true"
          onClick={() => setMenuOpen(false)}
        />
      )}

      <aside className={menuOpen ? 'app-sidebar open' : 'app-sidebar'}>
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <ShieldIcon size={20} />
          </span>
          <span className="brand-text">
            <span className="brand-name">Aegis Vuldris</span>
            <span className="brand-tagline">AI model security assurance</span>
          </span>
        </div>

        {navLinks}
        {userCard}
      </aside>

      <div className="app-main-wrap">
        <header className="app-header">
          <button
            type="button"
            className="icon-ghost"
            aria-label="Open navigation menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <MenuIcon size={19} />
          </button>
          <div className="brand">
            <span className="brand-mark" aria-hidden="true">
              <ShieldIcon size={17} />
            </span>
            <span className="brand-name">Aegis Vuldris</span>
          </div>
        </header>

        <main className="app-main">
          <Outlet />
        </main>

        <footer className="app-footer">
          Aegis Vuldris · Authorized security testing only. Findings are graded evidence, not proof —
          each finding shows whether a judge or a reviewer confirmed it.
        </footer>
      </div>
    </div>
  )
}
