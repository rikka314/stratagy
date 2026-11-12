import { useCallback, useEffect, useRef, useState } from 'react'

export function useAsync(fn, deps = [], immediate = true) {
  const [state, setState] = useState({ status: immediate ? 'loading' : 'idle', data: null, error: null })
  const generation = useRef(0)
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; generation.current += 1 } }, [])
  const run = useCallback(async (...args) => {
    const requestGeneration = ++generation.current
    setState({ status: 'loading', data: null, error: null })
    try {
      const data = await fn(...args)
      if (mounted.current && generation.current === requestGeneration) setState({ status: 'success', data, error: null })
      return data
    } catch (error) {
      if (mounted.current && generation.current === requestGeneration) setState({ status: 'error', data: null, error })
      throw error
    }
  }, deps)
  useEffect(() => {
    generation.current += 1
    setState({ status: immediate ? 'loading' : 'idle', data: null, error: null })
    if (immediate) run().catch(() => {})
  }, [run, immediate])
  return { ...state, run }
}
