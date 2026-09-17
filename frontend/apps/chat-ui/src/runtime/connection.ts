import { toast } from 'sonner'

const INITIALIZE_TIMEOUT_MS = 8_000

type ErrorListener = (message: string | null) => void

let lastMessage: string | null = null
let lastNotifiedAt = 0
const listeners = new Set<ErrorListener>()

export function subscribeLangGraphError(listener: ErrorListener) {
  listeners.add(listener)
  listener(lastMessage)
  return () => {
    listeners.delete(listener)
  }
}

export function clearLangGraphError() {
  if (lastMessage == null) return
  lastMessage = null
  listeners.forEach((listener) => listener(null))
}

export function notifyLangGraphFailure(reason: unknown) {
  const message = describeLangGraphFailure(reason)
  const now = Date.now()
  const duplicate = lastMessage === message && now - lastNotifiedAt < 1500
  lastMessage = message
  lastNotifiedAt = now
  listeners.forEach((listener) => listener(message))
  if (!duplicate) toast.error(message)
}

export function describeLangGraphFailure(reason: unknown): string {
  const text =
    reason instanceof Error
      ? reason.message
      : typeof reason === 'string'
        ? reason
        : ''

  if (/timeout|timed out|aborted/i.test(text)) {
    return 'LangGraph 响应超时。请确认 :2025 已启动后重试。'
  }
  if (
    /failed to fetch|networkerror|econnrefused|load failed|network request failed/i.test(
      text,
    ) ||
    !text
  ) {
    return '无法连接 LangGraph 服务（:2025）。请确认 Agent 后端已启动后重试。'
  }
  return text
}

export async function withTimeout<T>(
  task: Promise<T>,
  ms = INITIALIZE_TIMEOUT_MS,
  label = 'LangGraph 初始化超时',
): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    return await Promise.race([
      task,
      new Promise<T>((_, reject) => {
        timer = setTimeout(() => reject(new Error(label)), ms)
      }),
    ])
  } finally {
    if (timer) clearTimeout(timer)
  }
}
