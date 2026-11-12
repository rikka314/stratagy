export function toSeries(value, valueKey) {
  if (!value) return { x: [], y: [] }
  if (!Array.isArray(value)) return { x: Object.keys(value), y: Object.values(value).map(finite) }
  return {
    x: value.map((row, i) => row && typeof row === 'object' ? row.date ?? row.month ?? row.datetime ?? row.timestamp ?? i : i),
    y: value.map(row => row && typeof row === 'object'
      ? finite(valueKey ? row[valueKey] : row.value ?? row.equity ?? row.strategy_equity ?? row.return ?? row.strategy_return ?? row.close)
      : finite(row)),
  }
}

export function finite(value) {
  if (value == null || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

export function monthlyMatrix(rows) {
  const years = [...new Set(rows.map(row => String(row.month).slice(0, 4)))].sort()
  const values = new Map(rows.map(row => [row.month, finite(row.strategy_return)]))
  return { years, z: years.map(year => Array.from({ length: 12 }, (_, month) => values.get(`${year}-${String(month + 1).padStart(2, '0')}`) ?? null)) }
}
