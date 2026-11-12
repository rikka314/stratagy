import { useState } from 'react'
import { api } from '../api/client'
import { Button, DataTable, Field, PageIntro, Section, Status } from '../components/Primitives'
import { useAsync } from '../hooks/useAsync'
import { useApp } from '../state/AppContext'

export function MonitorPage() {
  const { language } = useApp()
  const zh = language === 'zh'
  const runs = useAsync(() => api.monitor(), [], true)
  const [campaignId, setCampaignId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const items = runs.data?.campaigns || []
  const enabled = runs.data?.enabled === true
  const control = async (action, id) => {
    setBusy(true); setError('')
    try { await api.controlExperiment(action, id); await runs.run() }
    catch (cause) { setError(cause.message) } finally { setBusy(false) }
  }
  const rows = items.map(item => ({
    id: item.campaign?.campaign_id || item.campaign?.id,
    status: item.campaign?.status || 'unknown',
    phase: item.phase || '—',
    process: item.process?.pid || '—',
    error: item.error?.message || (item.error ? JSON.stringify(item.error) : '—'),
  }))
  return <main id="main" className="page">
    <PageIntro index="05" eyebrow={zh ? '本地实验' : 'Local experiments'} title={zh ? '让实验有迹可循' : 'Follow every experiment'} text={zh ? '查看研究任务状态，并在本地管理运行过程。' : 'Inspect research campaigns and manage their execution locally.'} />
    <Section index="05.1" title={zh ? '运行状态' : 'Run status'}>
      {runs.status === 'loading' && <Status state="loading">{zh ? '正在读取实验状态' : 'Loading experiment state'}</Status>}
      {runs.status === 'error' && <Status state="error" onRetry={runs.run}>{runs.error?.message}</Status>}
      {runs.status === 'success' && !enabled && <Status>{zh ? '当前环境未启用本地实验控制。' : 'Local experiment control is not enabled in this environment.'}</Status>}
      {enabled && <><Button variant="secondary" disabled={busy} onClick={runs.run}>{zh ? '刷新状态' : 'Refresh status'}</Button>
        <DataTable rows={rows} columns={[{ key: 'id', label: zh ? '实验' : 'Campaign' }, { key: 'status', label: zh ? '状态' : 'Status' }, { key: 'phase', label: zh ? '阶段' : 'Phase' }, { key: 'error', label: zh ? '错误' : 'Error' }, { key: 'controls', label: zh ? '操作' : 'Actions', render: (_, row) => <div className="inline-actions"><Button variant="secondary" disabled={busy || !row.id || !['running', 'starting'].includes(row.status)} onClick={() => control('pause', row.id)}>{zh ? '暂停' : 'Pause'}</Button><Button variant="secondary" disabled={busy || !row.id || !['paused', 'failed', 'interrupted'].includes(row.status)} onClick={() => control('resume', row.id)}>{zh ? '继续' : 'Resume'}</Button></div> }]} empty={zh ? '暂无运行记录' : 'No experiment runs'} />
        <details><summary>{zh ? '启动新的研究实验' : 'Start a research campaign'}</summary><Field label={zh ? '实验名称（可选）' : 'Campaign ID (optional)'}><input value={campaignId} maxLength="80" pattern="[A-Za-z0-9_-]*" onChange={event => setCampaignId(event.target.value)} /></Field><Button disabled={busy} onClick={() => control('start', campaignId || null)}>{busy ? (zh ? '处理中' : 'Processing') : (zh ? '启动实验' : 'Start campaign')}</Button></details>
      </>}
      {error && <Status state="error">{error}</Status>}
    </Section>
  </main>
}
