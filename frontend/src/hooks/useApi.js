import { useCallback, useEffect, useState } from 'react'

// Loads data when the component mounts and whenever `deps` change, tracking loading
// and error state so every page doesn't repeat the same boilerplate.
export default function useApi(fetcher, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const [reloadCount, setReloadCount] = useState(0)

  useEffect(() => {
    // If deps change before this request finishes, its result is stale. Without this,
    // typing "ab" fast could let the slow response for "a" arrive last and win.
    let ignore = false
    fetcher().then(
      (data) => { if (!ignore) setState({ data, error: null, loading: false }) },
      (error) => { if (!ignore) setState((s) => ({ ...s, error, loading: false })) },
    )
    return () => { ignore = true }
    // The caller declares what the fetch depends on, like useEffect itself.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, reloadCount])

  // Lets components patch the loaded data after a mutation (e.g. a signup) without refetching.
  const setData = useCallback((update) => setState((s) => ({
    ...s,
    data: typeof update === 'function' ? update(s.data) : update,
  })), [])

  const reload = useCallback(() => setReloadCount((n) => n + 1), [])

  return { ...state, setData, reload }
}
