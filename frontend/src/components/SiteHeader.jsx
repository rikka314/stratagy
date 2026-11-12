import { NavLink } from 'react-router-dom'
import { useApp } from '../state/AppContext'
import { t } from '../i18n'

export function SiteHeader() {
  const { language, setLanguage } = useApp()
  const links = [
    ['/', 'home'], ['/stock-analysis', 'single'], ['/stocks-analysis', 'multi'],
    ['/final-report', 'report'],
  ]
  return <div className="header-dock"><header className="site-header">
    <NavLink to={{pathname:'/',search:preservedQuery(language)}} className="brand"><img src={`${import.meta.env.BASE_URL}yince-logo-white.png`} alt="YINCE" width="36" height="36"/><span>Strategy Lab</span></NavLink>
    <nav aria-label="Primary navigation">
      {links.map(([to, label]) => <NavLink key={to} to={{ pathname: to, search: preservedQuery(language) }} end={to === '/'}>{t(language, label)}</NavLink>)}
    </nav>
    <div className="header-tools">
      <NavLink to={{ pathname: '/model-evaluation', search: preservedQuery(language) }} className="text-button">{language === 'zh' ? '浏览研究证据' : 'Browse evidence'}</NavLink>
      <div className="header-tools" aria-label={language === 'zh' ? '语言切换' : 'Language'}>
        <button className="text-button" aria-pressed={language === 'zh'} onClick={() => setLanguage('zh')} lang="zh-CN" aria-label="切换为中文">中</button>
        <span>/</span>
        <button className="text-button" aria-pressed={language === 'en'} onClick={() => setLanguage('en')} lang="en" aria-label="Switch to English">EN</button>
      </div>
    </div>
  </header></div>
}

function preservedQuery(language) { const params=new URLSearchParams(window.location.search); params.set('lang',language); return `?${params}` }
