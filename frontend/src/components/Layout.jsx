import { NavLink, Outlet } from 'react-router'

import useAuth from '../auth/useAuth'

export default function Layout() {
  const { user, logout } = useAuth()

  return (
    <>
      <header className="topbar">
        <nav className="topbar-inner">
          <NavLink to="/" className="brand">Lineup</NavLink>
          <NavLink to="/" end>My orgs</NavLink>
          <NavLink to="/schedule">My schedule</NavLink>
          <NavLink to="/shifts">Browse shifts</NavLink>
          <span className="spacer" />
          <span className="muted">{user.username}</span>
          <button type="button" className="link-button" onClick={logout}>Log out</button>
        </nav>
      </header>
      <main className="page">
        <Outlet />
      </main>
    </>
  )
}
