import { Navigate, Outlet, useLocation } from 'react-router'

import useAuth from './useAuth'

// Wraps every private page. This is a UX convenience, not security: the API
// rejects requests without a valid token no matter what the frontend does.
export default function RequireAuth() {
  const { user, checking } = useAuth()
  const location = useLocation()

  if (checking) return <p className="muted center">Loading…</p>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <Outlet />
}
