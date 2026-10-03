import { useEffect, useRef, useState } from 'react'

import * as api from '../api'
import useApi from '../hooks/useApi'

// Google's "Sign in with Google" script, loaded once for the whole app.
let gisScript = null
function loadGoogleScript() {
  if (!gisScript) {
    gisScript = new Promise((resolve, reject) => {
      const script = document.createElement('script')
      script.src = 'https://accounts.google.com/gsi/client'
      script.async = true
      script.onload = resolve
      script.onerror = reject
      document.head.appendChild(script)
    })
  }
  return gisScript
}

/**
 * Google's official button. Clicking it opens Google's own sign-in window (Lineup
 * never sees the Google password) and hands us a signed ID token (`credential`),
 * which the backend verifies before trusting it.
 * Renders nothing when the server has no Google client ID configured.
 */
export default function GoogleButton({ onCredential, text = 'continue_with' }) {
  const config = useApi(() => api.auth.googleConfig())
  const container = useRef(null)
  const latestCallback = useRef(onCredential)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    latestCallback.current = onCredential
  })

  const clientId = config.data?.enabled ? config.data.client_id : null

  useEffect(() => {
    if (!clientId) return undefined
    let cancelled = false
    loadGoogleScript()
      .then(() => {
        if (cancelled || !container.current) return
        window.google.accounts.id.initialize({
          client_id: clientId,
          callback: (response) => latestCallback.current(response.credential),
        })
        window.google.accounts.id.renderButton(container.current, {
          theme: 'outline', size: 'large', text, width: 300,
        })
      })
      .catch(() => setFailed(true))
    return () => { cancelled = true }
  }, [clientId, text])

  if (!clientId) return null
  if (failed) return <p className="muted small">Google sign-in couldn't load. Check your connection.</p>
  return <div className="google-button" ref={container} />
}
