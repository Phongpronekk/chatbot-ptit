import type { Conversation, ConversationSummary, Health } from './chat.types'

const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 120_000)
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...options,
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...options.headers },
      signal: controller.signal,
    })
    if (!response.ok) {
      const body = await response.json().catch(() => null)
      throw new Error(typeof body?.detail === 'string' ? body.detail : `Yêu cầu thất bại (${response.status}). Vui lòng thử lại.`)
    }
    return response.status === 204 ? undefined as T : await response.json() as T
  } catch (error) {
    if (error instanceof TypeError || (error instanceof DOMException && error.name === 'AbortError')) {
      throw new Error('Không kết nối được backend hoặc yêu cầu đã quá thời gian chờ. Vui lòng thử lại.')
    }
    throw error
  } finally {
    window.clearTimeout(timeout)
  }
}

export const chatApi = {
  health: () => request<Health>('/health'),
  list: () => request<ConversationSummary[]>('/conversations'),
  get: (id: string) => request<Conversation>(`/conversations/${encodeURIComponent(id)}`),
  create: () => request<Conversation>('/conversations', { method: 'POST' }),
  remove: (id: string) => request<void>(`/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  send: (id: string, message: string, requestId: string) => request<Conversation>(`/conversations/${encodeURIComponent(id)}/messages`, {
    method: 'POST', body: JSON.stringify({ message, request_id: requestId }),
  }),
}
