const copy = {
  zh: {
    brand: 'Strategy Lab', home: '首页', single: '单股分析', multi: '多股分析', evidence: '研究证据', report: '报告', monitor: '实验监控',
    theme: '切换主题', language: 'Switch to English', loading: '正在加载', retry: '重试', noData: '暂无数据', error: '暂时无法加载数据',
  },
  en: {
    brand: 'Strategy Lab', home: 'Home', single: 'Single stock', multi: 'Portfolio', evidence: 'Research', report: 'Report', monitor: 'Monitor',
    theme: 'Toggle theme', language: '切换至中文', loading: 'Loading', retry: 'Retry', noData: 'No data available', error: 'Unable to load data',
  },
}
export const t = (language, key) => copy[language]?.[key] || key
