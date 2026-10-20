import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import { Loading } from './Primitives'

/**
 * Gate for authenticated routes.
 *
 * This is a user-experience control only. The backend independently enforces
 * authorization on every request; hiding a route in the client is never a
 * security boundary.
 */
export function ProtectedRoute() {
  const { isAuthenticated, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return <Loading label="Restoring session…" />
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return <Outlet />
}
