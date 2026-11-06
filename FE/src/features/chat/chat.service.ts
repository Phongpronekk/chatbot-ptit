import type { Attachment, Conversation, ConversationSummary, Health, RetrievalScope } from './chat.types'

const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 120_000)
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...options,
      credentials: 'include',
      headers: { ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...options.headers },
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
  upload: (id: string, file: File) => {
    const body = new FormData()
    body.append('file', file)
    return request<Attachment>(`/conversations/${encodeURIComponent(id)}/documents`, { method: 'POST', body })
  },
  removeDocument: (id: string, documentId: string) => request<void>(
    `/conversations/${encodeURIComponent(id)}/documents/${encodeURIComponent(documentId)}`, { method: 'DELETE' }),
  send: (
    id: string,
    message: string,
    requestId: string,
    documentIds: string[],
    attachmentIds: string[],
    scope: RetrievalScope,
    onDelta?: (text: string) => void,
  ): Promise<Conversation> => {
    if (onDelta) {
      return chatApi.sendStream(id, message, requestId, documentIds, attachmentIds, scope, onDelta)
    }
    return request<Conversation>(`/conversations/${encodeURIComponent(id)}/messages`, {
      method: 'POST',
      body: JSON.stringify({ message, request_id: requestId, document_ids: documentIds, attachment_ids: attachmentIds, retrieval_scope: scope }),
    })
  },
  sendStream: async (
    id: string,
    message: string,
    requestId: string,
    documentIds: string[],
    attachmentIds: string[],
    scope: RetrievalScope,
    onDelta?: (text: string) => void,
  ): Promise<Conversation> => {
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 120_000)
    try {
      const response = await fetch(`${baseUrl}/conversations/${encodeURIComponent(id)}/messages/stream`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          request_id: requestId,
          document_ids: documentIds,
          attachment_ids: attachmentIds,
          retrieval_scope: scope,
        }),
        signal: controller.signal,
      })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(typeof body?.detail === 'string' ? body.detail : `Yêu cầu thất bại (${response.status}). Vui lòng thử lại.`)
      }
      if (!response.body) {
        return await request<Conversation>(`/conversations/${encodeURIComponent(id)}/messages`, {
          method: 'POST',
          body: JSON.stringify({ message, request_id: requestId, document_ids: documentIds, attachment_ids: attachmentIds, retrieval_scope: scope }),
        })
      }
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let doneConversation: Conversation | null = null

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const blocks = buffer.split('\n\n')
        buffer = blocks.pop() ?? ''
        for (const block of blocks) {
          const lines = block.split('\n')
          let eventType = 'message'
          const dataLines: string[] = []
          for (const line of lines) {
            if (line.startsWith('event:')) {
              eventType = line.slice(6).trim()
            } else if (line.startsWith('data:')) {
              dataLines.push(line.slice(5).trim())
            }
          }
          if (!dataLines.length) continue
          const payload = JSON.parse(dataLines.join('\n'))
          if (eventType === 'delta' && typeof payload?.text === 'string') {
            onDelta?.(payload.text)
          } else if (eventType === 'done') {
            doneConversation = payload as Conversation
          } else if (eventType === 'error') {
            throw new Error(typeof payload?.detail === 'string' ? payload.detail : 'Dịch vụ trả lời chưa sẵn sàng.')
          }
        }
      }
      if (!doneConversation) {
        throw new Error('Luồng trả lời kết thúc bất ngờ. Vui lòng thử lại.')
      }
      return doneConversation
    } catch (error) {
      if (error instanceof TypeError || (error instanceof DOMException && error.name === 'AbortError')) {
        throw new Error('Không kết nối được backend hoặc yêu cầu đã quá thời gian chờ. Vui lòng thử lại.')
      }
      throw error
    } finally {
      window.clearTimeout(timeout)
    }
  },
  feedback: (messageId: string, rating: 1 | -1, comment?: string) => request<void>(
    `/messages/${encodeURIComponent(messageId)}/feedback`,
    { method: 'PUT', body: JSON.stringify({ rating, comment: comment ?? null }) },
  ),
}
