const API_BASE = '/strategy/api'

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: options.body instanceof FormData ? options.headers : {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })
  if (!response.ok) {
    const raw = await response.text()
    let detail
    try { detail = JSON.parse(raw) } catch { detail = { message: raw } }
    const value = detail?.detail || detail?.message
    const message = typeof value === 'string' ? value : Array.isArray(value)
      ? value.map(item => `${(item.loc || []).join('.')}: ${item.msg}`).join('; ')
      : value ? JSON.stringify(value) : `Request failed (${response.status})`
    throw new ApiError(message, response.status, detail)
  }
  const type = response.headers.get('content-type') || ''
  return type.includes('application/json') ? response.json() : response.text()
}

export const api = {
  metadata: () => request('/metadata'),
  marketContext: (market, refresh=false) => request(`/market-context?market=${encodeURIComponent(market)}&force_refresh=${refresh}`),
  dataset: (id) => request(`/datasets/${encodeURIComponent(id)}`),
  sliceDataset: (id, payload) => request(`/datasets/${encodeURIComponent(id)}/slice`, { method:'POST', body:JSON.stringify(payload) }),
  datasetAnalysis: (id, options = {}) => request(`/datasets/${encodeURIComponent(id)}/analysis`,{ method:'POST', body:JSON.stringify(options) }),
  homeNews: (language) => request(`/home/news?lang=${language}`),
  homeMarket: () => request('/home/market'),
  homeRecommendations: (market) => request(`/home/recommendations?market=${market}`),
  homeCandles: (market, symbol) => request(`/home/candles?market=${market}&symbol=${encodeURIComponent(symbol)}`),
  stocks: (market, query = '', limit = 20) => request(`/stocks?market=${encodeURIComponent(market)}&query=${encodeURIComponent(query)}&limit=${limit}`),
  loadStock: (payload) => request('/stocks/load', { method: 'POST', body: JSON.stringify(payload) }),
  uploadStock: (file, fields = {}) => {
    const body = new FormData()
    body.append('file', file)
    Object.entries(fields).forEach(([key, value]) => value != null && body.append(key, value))
    return request('/stocks/upload', { method: 'POST', body })
  },
  createSingleJob: (payload) => request('/analysis/single/jobs', { method: 'POST', body: JSON.stringify(payload) }),
  singleJob: (id) => request(`/analysis/single/jobs/${id}`),
  singleResult: (id) => request(`/analysis/single/jobs/${id}/result`),
  walkForward: (id, trainWindow = 252, testWindow = 63) => request(`/analysis/single/jobs/${id}/walk-forward?train_window=${trainWindow}&test_window=${testWindow}`),
  portfolio: (payload) => request('/analysis/portfolio', { method: 'POST', body: JSON.stringify(payload) }),
  portfolioFactors: (payload) => request('/analysis/portfolio/factors', { method:'POST', body:JSON.stringify(payload) }),
  optimizePortfolio: (payload) => request('/analysis/portfolio/optimize', { method: 'POST', body: JSON.stringify(payload) }),
  portfolioResult: (id) => request(`/analysis/portfolio/results/${encodeURIComponent(id)}`),
  researchCatalog: () => request('/research/catalog'),
  researchReport: (id) => request(`/research/reports/${encodeURIComponent(id)}`),
  researchHtml: (id) => request(`/research/reports/${encodeURIComponent(id)}/html`),
  finalReport: (language) => request(`/reports/final?language=${language}`),
  monitor: () => request('/experiments'),
  controlExperiment: (action, id) => request(action === 'start' ? '/experiments/start' : `/experiments/${encodeURIComponent(id)}/${action}`, { method: 'POST', body: JSON.stringify(action === 'start' ? { campaign_id: id || null } : {}) }),
  singleExportUrl: (jobId) => `${API_BASE}/exports/single/${jobId}.html`,
  exportPortfolio: (payload, language = 'zh') => request(`/exports/portfolio?language=${language}`, { method: 'POST', body: JSON.stringify(payload) }),
}
