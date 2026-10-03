import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router'

import useAuth from '../auth/useAuth'
import ErrorMessage from '../components/ErrorMessage'
import GoogleButton from '../components/GoogleButton'

export default function LoginPage() {
  const { user, login, loginWithGoogle } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  if (user) return <Navigate to="/" replace />

  async function googleCredential(credential) {
    setError(null)
    try {
      await loginWithGoogle(credential)
      navigate(location.state?.from ?? '/', { replace: true })
    } catch (err) {
      // e.g. 409: an account with this email exists, so log in with the password first
      setError(err)
    }
  }

  async function submit(event) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await login(username, password)
      // Send them back to the page they originally tried to open.
      navigate(location.state?.from ?? '/', { replace: true })
    } catch (err) {
      setError(err)
      setSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <form className="card form auth-card" onSubmit={submit}>
        <h1 className="brand-title">Lineup</h1>
        <p className="muted">Shift sign-ups for student organizations.</p>
        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required autoFocus />
        </label>
        <label>
          Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
        </label>
        <ErrorMessage error={error} />
        <button type="submit" disabled={submitting}>{submitting ? 'Logging in…' : 'Log in'}</button>
        <GoogleButton onCredential={googleCredential} />
        <p className="muted small">No account? <Link to="/register">Sign up</Link></p>
      </form>
    </main>
  )
}
