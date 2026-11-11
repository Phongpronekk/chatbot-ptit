import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { chatApi } from '../../src/features/chat/chat.service'

const fetchMock = vi.fn()
const networkError = 'Không kết nối được backend hoặc yêu cầu đã quá thời gian chờ. Vui lòng thử lại.'
function response(status: number, body: unknown) {
  return { ok: status >= 200 && status < 300, status, json: vi.fn().mockResolvedValue(body) }
}

describe('Chat HTTP service (fetch mock)', () => {
  beforeEach(() => { vi.stubGlobal('fetch', fetchMock); fetchMock.mockReset() })
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

  it('FE-SVC-001 | Map TypeError mạng sang thông báo tiếng Việt', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(chatApi.health()).rejects.toThrow(networkError)
  })
  it('FE-SVC-002 | Map AbortError sang thông báo timeout', async () => {
    fetchMock.mockRejectedValue(new DOMException('aborted', 'AbortError'))
    await expect(chatApi.list()).rejects.toThrow(networkError)
  })
  it('FE-SVC-003 | Timeout thực sự abort sau 120000 ms và dọn timer', async () => {
    vi.useFakeTimers()
    fetchMock.mockImplementation((_url, init) => new Promise((_resolve, reject) => {
      init.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
    }))
    const expectation = expect(chatApi.health()).rejects.toThrow(networkError)
    await vi.advanceTimersByTimeAsync(120000)
    await expectation
    expect(fetchMock.mock.calls[0]?.[1].signal.aborted).toBe(true)
    expect(vi.getTimerCount()).toBe(0)
  })
  it('FE-SVC-004 | Giữ nguyên detail dạng chuỗi từ backend', async () => {
    fetchMock.mockResolvedValue(response(503, { detail: 'Dịch vụ chưa sẵn sàng fixture' }))
    await expect(chatApi.create()).rejects.toThrow('Dịch vụ chưa sẵn sàng fixture')
  })
  it('FE-SVC-005 | detail dạng list validation dùng lỗi HTTP mặc định', async () => {
    fetchMock.mockResolvedValue(response(422, { detail: [{ msg: 'fixture validation' }] }))
    await expect(chatApi.create()).rejects.toThrow('Yêu cầu thất bại (422). Vui lòng thử lại.')
  })
  it('FE-SVC-006 | Body lỗi không phải JSON vẫn giữ thông báo HTTP', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 502, json: vi.fn().mockRejectedValue(new SyntaxError('HTML')) })
    await expect(chatApi.list()).rejects.toThrow('Yêu cầu thất bại (502). Vui lòng thử lại.')
  })
  it('FE-SVC-007 | 204 không gọi json và trả undefined', async () => {
    const empty = response(204, null)
    fetchMock.mockResolvedValue(empty)
    await expect(chatApi.remove('id/unsafe')).resolves.toBeUndefined()
    expect(empty.json).not.toHaveBeenCalled()
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/conversations/id%2Funsafe')
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ method: 'DELETE', credentials: 'include' })
  })
  it('FE-SVC-008 | Gửi UUID request, JSON và cookie credentials', async () => {
    const result = { id: 'fixture' }
    fetchMock.mockResolvedValue(response(200, result))
    await expect(chatApi.send('conversation', 'câu hỏi', 'request-uuid', [], [], 'knowledge')).resolves.toEqual(result)
    const init = fetchMock.mock.calls[0]?.[1]
    expect(JSON.parse(init.body)).toEqual({ message: 'câu hỏi', request_id: 'request-uuid', document_ids: [], attachment_ids: [], retrieval_scope: 'knowledge' })
    expect(init).toMatchObject({ credentials: 'include', headers: { 'Content-Type': 'application/json' }, method: 'POST' })
  })
})
