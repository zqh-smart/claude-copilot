import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'

interface ApiErrorPayload {
  detail?: string | { message?: string }
  message?: string
  trace_id?: string
}

export class ApiError extends Error {
  readonly status?: number
  readonly traceId?: string
  readonly code?: string

  constructor(
    message: string,
    options: { status?: number; traceId?: string; code?: string; cause?: unknown } = {},
  ) {
    super(message, { cause: options.cause })
    this.name = 'ApiError'
    this.status = options.status
    this.traceId = options.traceId
    this.code = options.code
  }
}

function requestId() {
  return globalThis.crypto?.randomUUID?.() || `cc-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function accessToken() {
  if (typeof window === 'undefined') return ''
  return window.sessionStorage.getItem('cc_access_token') || ''
}

function attachRequestContext(config: InternalAxiosRequestConfig) {
  config.headers.set('X-Request-ID', requestId())
  const token = accessToken()
  if (token) config.headers.set('Authorization', `Bearer ${token}`)
  return config
}

function normalizeError(reason: AxiosError<ApiErrorPayload>) {
  const payload = reason.response?.data
  const detail = typeof payload?.detail === 'string' ? payload.detail : payload?.detail?.message
  const traceId =
    String(reason.response?.headers?.['x-trace-id'] || reason.response?.headers?.['x-request-id'] || payload?.trace_id || '') ||
    undefined

  if (reason.code === AxiosError.ECONNABORTED) {
    return new ApiError('服务响应超时，请检查后端依赖后重试', {
      code: reason.code,
      traceId,
      cause: reason,
    })
  }

  if (!reason.response) {
    return new ApiError('无法连接业务服务，请确认 FastAPI 已启动', {
      code: reason.code,
      cause: reason,
    })
  }

  const status = reason.response.status
  const fallback = status === 401 ? '登录状态已失效' : status === 403 ? '没有访问该资源的权限' : `请求失败（${status}）`
  if (status === 401 && typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('cc:auth-required'))
  }
  return new ApiError(detail || payload?.message || fallback, {
    status,
    traceId,
    code: reason.code,
    cause: reason,
  })
}

export const fastApi = axios.create({
  baseURL: '/api/fastapi',
  timeout: 8_000,
})

fastApi.interceptors.request.use(attachRequestContext)
fastApi.interceptors.response.use(
  (response) => response,
  (reason: AxiosError<ApiErrorPayload>) => Promise.reject(normalizeError(reason)),
)
