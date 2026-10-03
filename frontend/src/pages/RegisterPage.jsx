import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router'

import useAuth from '../auth/useAuth'
import ErrorMessage from '../components/ErrorMessage'

export default function RegisterPage() {
  const { user, register } = useAuth()
  const navigate = useNavigate()
  const [fields, setFields] = useState({ username: '', email: '', password: '' })
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  if (user) return <Navigate to="/" replace />

  const update = (event) => setFields({ ...fields, [event.target.name]: event.target.value })

  async function submit(event) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await register(fields)
      navigate('/', { replace: true })
    } catch (err) {
      // e.g. "password: This password is too common." straight from Django's validators
      setError(err)
      setSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <form className="card form auth-card" onSubmit={submit}>
        <h1 className="brand-title">Create your account</h1>
        <label>
          Username
          <input name="username" value={fields.username} onChange={update} autoComplete="username" required autoFocus />
        </label>
        <label>
          Email
          <input type="email" name="email" value={fields.email} onChange={update} autoComplete="email" required />
        </label>
        <label>
          Password
          <input type="password" name="password" value={fields.password} onChange={update} autoComplete="new-password" required minLength={8} />
        </label>
        <ErrorMessage error={error} />
        <button type="submit" disabled={submitting}>{submitting ? 'Creating account…' : 'Sign up'}</button>
        <p className="muted small">Already have an account? <Link to="/login">Log in</Link></p>
      </form>
    </main>
  )
}
