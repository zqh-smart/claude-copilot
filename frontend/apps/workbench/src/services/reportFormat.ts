const TZ = 'Asia/Shanghai'

export function formatReportTime(value: string, now = new Date()): string {
  const date = new Date(value)
  if (Number.isNaN(+date)) return value
  const sameDay = date.toDateString() === now.toDateString()
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  const time = new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: TZ,
  }).format(date)
  if (sameDay) return `今天 ${time}`
  if (date.toDateString() === yesterday.toDateString()) return `昨天 ${time}`
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone: TZ,
  }).format(date)
}

export function formatClock(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(+date)) return ''
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: TZ,
  }).format(date)
}
