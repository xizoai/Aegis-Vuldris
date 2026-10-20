import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, setUnauthorizedHandler } from '../api/client'
import { LoginPage, RegisterPage } from '../pages/AuthPages'

function renderWithRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

/**
 * The auth pages consume `useAuth`, which needs the provider. Rather than
 * exercising the real network path here, mock the context module so the tests
 * focus on form behaviour and error surfacing.
 */
const authState = {
  login: vi.fn(),
  register: vi.fn(),
}

vi.mock('../auth/useAuth', () => ({
  useAuth: () => ({
    user: null,
    isAuthenticated: false,
    isLoading: false,
    login: authState.login,
    register: authState.register,
    logout: vi.fn(),
  }),
}))

describe('LoginPage', () => {
  beforeEach(() => {
    authState.login.mockReset()
    setUnauthorizedHandler(() => {})
  })

  it('renders accessible labelled fields', () => {
    renderWithRouter(<LoginPage />)
    expect(screen.getByLabelText('Email')).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
  })

  it('submits credentials to the auth context', async () => {
    const user = userEvent.setup()
    authState.login.mockResolvedValue(undefined)
    renderWithRouter(<LoginPage />)

    await user.type(screen.getByLabelText('Email'), 'aegis@example.com')
    await user.type(screen.getByLabelText('Password'), 'a-very-strong-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => {
      expect(authState.login).toHaveBeenCalledWith(
        'aegis@example.com',
        'a-very-strong-password',
      )
    })
  })

  it('surfaces the backend error message on failure', async () => {
    const user = userEvent.setup()
    authState.login.mockRejectedValue(new ApiError(401, 'INVALID_CREDENTIALS', 'Incorrect email or password.'))
    renderWithRouter(<LoginPage />)

    await user.type(screen.getByLabelText('Email'), 'aegis@example.com')
    await user.type(screen.getByLabelText('Password'), 'wrong-password-value')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Incorrect email or password.')
    })
  })

  it('uses a password input so the secret is not echoed on screen', () => {
    renderWithRouter(<LoginPage />)
    const password = screen.getByLabelText('Password')
    expect(password).toHaveAttribute('type', 'password')
  })
})

describe('RegisterPage', () => {
  beforeEach(() => {
    authState.register.mockReset()
    setUnauthorizedHandler(() => {})
  })

  it('enforces the minimum password length before submitting', async () => {
    const user = userEvent.setup()
    renderWithRouter(<RegisterPage />)

    await user.type(screen.getByLabelText('Email'), 'new@example.com')
    await user.type(screen.getByLabelText('Password'), 'short')
    await user.type(screen.getByLabelText('Confirm password'), 'short')

    expect(screen.getByRole('button', { name: 'Create account' })).toBeDisabled()
    expect(authState.register).not.toHaveBeenCalled()
  })

  it('rejects mismatched confirmation', async () => {
    const user = userEvent.setup()
    renderWithRouter(<RegisterPage />)

    await user.type(screen.getByLabelText('Email'), 'new@example.com')
    await user.type(screen.getByLabelText('Password'), 'a-very-strong-password')
    await user.type(screen.getByLabelText('Confirm password'), 'a-different-password')

    expect(await screen.findByText('Passwords do not match.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create account' })).toBeDisabled()
  })

  it('registers with matching, sufficiently long passwords', async () => {
    const user = userEvent.setup()
    authState.register.mockResolvedValue(undefined)
    renderWithRouter(<RegisterPage />)

    await user.type(screen.getByLabelText('Email'), 'new@example.com')
    await user.type(screen.getByLabelText('Password'), 'a-very-strong-password')
    await user.type(screen.getByLabelText('Confirm password'), 'a-very-strong-password')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    await waitFor(() => {
      expect(authState.register).toHaveBeenCalledWith(
        'new@example.com',
        'a-very-strong-password',
      )
    })
  })
})
