import { useContext } from 'react'

import { AuthContext, type AuthContextValue } from './authContextValue'

/** Access the current authentication state. */
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (context === null) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
