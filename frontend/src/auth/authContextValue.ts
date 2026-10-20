import { createContext } from 'react'

import type { User } from '../api/types'

export interface AuthContextValue {
  user: User | null
  isAuthenticated: boolean
  /** True while the initial session restore is still in flight. */
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)
