import { useState } from 'react'

import * as api from '../api'
import useAuth from '../auth/useAuth'
import ErrorMessage from '../components/ErrorMessage'
import GoogleButton from '../components/GoogleButton'
import GoogleCalendarSync from '../components/GoogleCalendarSync'
import useApi from '../hooks/useApi'

export default function AccountPage() {
  const { user } = useAuth()
  // Google sections only appear once the server has Google credentials.
  const config = useApi(() => api.auth.googleConfig())
  const googleEnabled = Boolean(config.data?.enabled)

  return (
    <div className="stack tab-panel">
      <h1>Account</h1>
      <ProfileForm user={user} />
      <SignInMethods user={user} showGoogle={googleEnabled || user.google_linked} />
      {googleEnabled && (
        <section className="card">
          <GoogleCalendarSync />
        </section>
      )}
    </div>
  )
}

function ProfileForm({ user }) {
  const { refreshUser } = useAuth()
  const [fields, setFields] = useState({
    first_name: user.first_name, last_name: user.last_name, email: user.email,
  })
  const [error, setError] = useState(null)
  const [saved, setSaved] = useState(false)

  const update = (e) => {
    const { name, value } = e.target
    setFields((f) => ({ ...f, [name]: value }))
  }

  async function submit(event) {
    event.preventDefault()
    setError(null)
    try {
      await api.auth.updateMe(fields)
      await refreshUser()
      setSaved(true)
      setTimeout(() => setSaved(false), 1500)
    } catch (err) {
      setError(err)
    }
  }

  return (
    <form className="card form" onSubmit={submit}>
      <h3>Profile</h3>
      <p className="muted small">Signed in as <strong>{user.username}</strong></p>
      <div className="row">
        <label>First name
          <input name="first_name" value={fields.first_name} onChange={update} autoComplete="given-name" />
        </label>
        <label>Last name
          <input name="last_name" value={fields.last_name} onChange={update} autoComplete="family-name" />
        </label>
      </div>
      <label>Email
        <input type="email" name="email" value={fields.email} onChange={update} required autoComplete="email" />
      </label>
      <ErrorMessage error={error} />
      <div className="actions">
        <button type="submit">{saved ? 'Saved' : 'Save profile'}</button>
      </div>
    </form>
  )
}

function SignInMethods({ user, showGoogle }) {
  const { refreshUser } = useAuth()
  const [error, setError] = useState(null)

  async function act(action) {
    setError(null)
    try {
      await action()
      await refreshUser()
    } catch (err) {
      setError(err)
    }
  }

  return (
    <section className="card stack">
      <h3>How you sign in</h3>
      <div className="method-row">
        <div>
          <strong>Password</strong>
          <div className="muted small">{user.has_password ? 'Set' : 'Not set: you sign in with Google'}</div>
        </div>
      </div>
      {showGoogle && (
        <div className="method-row">
          <div>
            <strong>Google</strong>
            <div className="muted small">{user.google_linked ? 'Linked' : 'Not linked'}</div>
          </div>
          {user.google_linked ? (
            <button
              type="button"
              className="secondary"
              disabled={!user.has_password}
              title={user.has_password ? '' : 'Google is your only way to sign in'}
              onClick={() => act(() => api.auth.unlinkGoogle())}
            >
              Unlink
            </button>
          ) : (
            <GoogleButton text="signin_with" onCredential={(credential) => act(() => api.auth.linkGoogle(credential))} />
          )}
        </div>
      )}
      <ErrorMessage error={error} />
    </section>
  )
}
