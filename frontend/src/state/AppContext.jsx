import { createContext, useContext, useEffect, useMemo, useState } from 'react'

const AppContext = createContext(null)
const STORAGE_KEY = 'strategy-lab-workspace-v1'

const initialWorkspace = { datasets: [], singleJobs: [], portfolio: null }

export function AppProvider({ children }) {
  const queryLang = new URLSearchParams(window.location.search).get('lang')
  const [language, setLanguage] = useState(() => queryLang === 'en' ? 'en' : 'zh')
  const [theme, setTheme] = useState(() => { try { return localStorage.getItem('strategy-theme') || 'light' } catch { return 'light' } })
  const [workspace, setWorkspace] = useState(() => {
    try { return { ...initialWorkspace, ...(JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}) } } catch { return initialWorkspace }
  })
  const [storageError,setStorageError]=useState(false)

  useEffect(() => { try { const compact={...workspace,datasets:(workspace.datasets||[]).map(({dataset_id,symbol,name,market,rows,date_range,adjust,source})=>({dataset_id,symbol,name,market,rows,date_range,adjust,source})),singleJobs:(workspace.singleJobs||[]).map(({job_id,status,progress,created_at,started_at,finished_at,error,symbol,family,display_label,dataset_id})=>({job_id,status,progress,created_at,started_at,finished_at,error,symbol,family,display_label,dataset_id})),portfolio:workspace.portfolio?.request?{request:workspace.portfolio.request,result_id:workspace.portfolio.result_id||workspace.portfolio.result?.result_id}:null}; localStorage.setItem(STORAGE_KEY, JSON.stringify(compact)); setStorageError(false) } catch { setStorageError(true) } }, [workspace])
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem('strategy-theme', theme) } catch { setStorageError(true) }
  }, [theme])
  useEffect(() => {
    document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en'
    const url = new URL(window.location.href)
    url.searchParams.set('lang', language)
    window.history.replaceState({}, '', url)
  }, [language])

  const value = useMemo(() => ({
    language, setLanguage, theme, setTheme, workspace, setWorkspace, storageError,
    addDataset: (dataset) => setWorkspace((state) => ({ ...state, datasets: [dataset, ...state.datasets.filter((item) => item.dataset_id !== dataset.dataset_id)] })),
    addSingleJob: (job) => setWorkspace((state) => ({ ...state, singleJobs: [job, ...state.singleJobs.filter((item) => item.job_id !== job.job_id)].filter((item,index)=>index<20||(state.savedSingleJobIds||[]).includes(item.job_id)) })),
    setPortfolio: (portfolio) => setWorkspace((state) => ({ ...state, portfolio })),
    clearWorkspace: () => setWorkspace(initialWorkspace),
  }), [language, theme, workspace, storageError])
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useApp() { return useContext(AppContext) }
