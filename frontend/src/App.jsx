import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { SiteHeader } from './components/SiteHeader'
import { Status } from './components/Primitives'
import { RouteSlide } from './components/RouteSlide'

const HomePage = lazy(() => import('./pages/HomePage').then((m) => ({ default: m.HomePage })))
const SingleStockPage = lazy(() => import('./pages/SingleStockPage').then((m) => ({ default: m.SingleStockPage })))
const MultiStockPage = lazy(() => import('./pages/MultiStockPage').then((m) => ({ default: m.MultiStockPage })))
const ResearchPage = lazy(() => import('./pages/ResearchPage').then((m) => ({ default: m.ResearchPage })))
const ReportPage = lazy(() => import('./pages/ReportPage').then((m) => ({ default: m.ReportPage })))
const MonitorPage = lazy(() => import('./pages/MonitorPage').then((m) => ({ default: m.MonitorPage })))

export default function App() {
  return <>
    <a className="skip-link" href="#main">Skip to content</a>
    <SiteHeader />
    <RouteSlide>{(location) => <Suspense fallback={<main className="page route-loading"><Status state="loading">Loading</Status></main>}><Routes location={location}>
      <Route path="/" element={<HomePage />} />
      <Route path="/stock-analysis" element={<SingleStockPage />} />
      <Route path="/stocks-analysis" element={<MultiStockPage />} />
      <Route path="/model-evaluation" element={<ResearchPage />} />
      <Route path="/final-report" element={<ReportPage />} />
      <Route path="/experiment-monitor" element={<MonitorPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes></Suspense>}</RouteSlide>
  </>
}
