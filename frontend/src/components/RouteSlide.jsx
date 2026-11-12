import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'

const routeOrder = ['/', '/stock-analysis', '/stocks-analysis', '/final-report', '/model-evaluation', '/experiment-monitor']

export function RouteSlide({ children }) {
  const location = useLocation()
  const [displayed, setDisplayed] = useState(location)
  const [phase, setPhase] = useState('idle')
  const [direction, setDirection] = useState(1)

  useEffect(() => {
    if (location.pathname === displayed.pathname) {
      setPhase((current) => current === 'exit' ? 'idle' : current)
      return
    }
    setDirection(routeOrder.indexOf(location.pathname) >= routeOrder.indexOf(displayed.pathname) ? 1 : -1)
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setDisplayed(location)
      setPhase('idle')
      return
    }
    setPhase('exit')
    const timer = window.setTimeout(() => {
      setDisplayed(location)
      setPhase('enter')
      window.scrollTo({ top: 0, behavior: 'instant' })
    }, 140)
    return () => window.clearTimeout(timer)
  }, [location, displayed.pathname])

  // Query-only changes (language, workspace) keep the current page mounted.
  const routeLocation = location.pathname === displayed.pathname ? location : displayed
  return <div className="route-viewport">
    <div className="route-slide" data-phase={phase} style={{ '--slide-direction': direction }} inert={phase === 'exit' ? true : undefined}
      onAnimationEnd={(event) => {
        if (event.target === event.currentTarget && event.animationName === 'route-slide-in') setPhase('idle')
      }}>
      {children(routeLocation)}
    </div>
  </div>
}
