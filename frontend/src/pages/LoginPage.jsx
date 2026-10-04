import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router'

import useAuth from '../auth/useAuth'
import ErrorMessage from '../components/ErrorMessage'
import GoogleButton from '../components/GoogleButton'

const demoEnabled = import.meta.env.VITE_DEMO_MODE === 'true'

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

  async function signIn(loginUsername, loginPassword) {
    setSubmitting(true)
    setError(null)
    try {
      await login(loginUsername, loginPassword)
      // Send them back to the page they originally tried to open.
      navigate(location.state?.from ?? '/', { replace: true })
    } catch (err) {
      setError(err)
      setSubmitting(false)
    }
  }

  function submit(event) {
    event.preventDefault()
    return signIn(username, password)
  }

  return (
    <main className="auth-page">
      <form className="card form auth-card" onSubmit={submit}>
        <h1 className="brand-title">Lineup</h1>
        <p className="muted">Shift sign-ups for student organizations.</p>
        {demoEnabled && (
          <section className="stack" aria-label="Try the demo">
            <p className="muted small">
              Explore sample classes, organizations, and shifts. Demo accounts are shared.
            </p>
            <div className="actions">
              <button
                type="button"
                disabled={submitting}
                onClick={() => signIn('demo_student', 'Lineup-demo-2026')}
              >
                Try student demo
              </button>
              <button
                type="button"
                className="secondary"
                disabled={submitting}
                onClick={() => signIn('demo_admin', 'Lineup-demo-2026')}
              >
                Try organizer demo
              </button>
            </div>
            <p className="muted small">Or log in with your own account:</p>
          </section>
        )}
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
