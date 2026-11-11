/** Display helpers: money and rate formatting, decimal-safe subtraction. */

export function formatMoney(value: string | null): string {
  if (value === null || value === undefined) return ''
  const n = Number(value)
  return n.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

export function formatRate(value: string | null): string {
  if (value === null || value === undefined) return '' // 分母为零 -> 留空
  const n = Number(value)
  return `${(n * 100).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}%`
}

/** Decimal-string subtraction without binary float artifacts. */
export function subtractMoney(a: string | null, b: string | null): string {
  const x = parseFloat(a ?? '0')
  const y = parseFloat(b ?? '0')
  return (x - y).toFixed(2)
}

export function isRateMetric(key: string): boolean {
  return key === 'refund_rate'
}

export function formatMetric(key: string, value: string | null): string {
  return isRateMetric(key) ? formatRate(value) : formatMoney(value)
}
