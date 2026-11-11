import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useChatStore } from '../../src/features/chat/chat.store'
import { chatApi } from '../../src/features/chat/chat.service'

vi.mock('../../src/features/chat/chat.service', () => ({ chatApi: {
  list: vi.fn(), get: vi.fn(), create: vi.fn(), send: vi.fn(), remove: vi.fn(), health: vi.fn(),
  upload: vi.fn(), removeDocument: vi.fn(), feedback: vi.fn(),
} }))

const timestamp = '2026-11-10T17:10:00.000Z'
function conversation(id = 'qa-conversation') {
  return { id, title: 'Fixture', created_at: timestamp, updated_at: timestamp, messages: [], documents: [] }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(yes => { resolve = yes })
  return { promise, resolve }
}

describe('Chat store offline QA', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(chatApi.create).mockResolvedValue(conversation())
    vi.mocked(chatApi.send).mockResolvedValue(conversation())
    vi.mocked(chatApi.get).mockImplementation(async id => conversation(id))
    vi.mocked(chatApi.list).mockResolvedValue([])
  })
  afterEach(() => { vi.useRealTimers(); vi.resetAllMocks() })

  it('FE-STORE-001 | Nhóm lịch sử theo ranh giới nửa đêm Asia/Ho_Chi_Minh', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(timestamp))
    const store = useChatStore()
    store.conversations = [
      { ...conversation('today'), updated_at: '2026-11-10T17:00:00.000Z' },
      { ...conversation('yesterday'), updated_at: '2026-11-10T16:59:59.000Z' },
      { ...conversation('older'), updated_at: '2026-11-09T16:59:59.000Z' },
    ]
    expect(store.groups.map(g => [g.label, g.items.map(c => c.id)])).toEqual([
      ['Hôm nay', ['today']], ['Hôm qua', ['yesterday']], ['Trước đó', ['older']],
    ])
  })

  it('FE-STORE-002 | Tự tạo hội thoại rồi gửi nội dung đã trim', async () => {
    const store = useChatStore()
    await store.send('  câu hỏi fixture  ')
    expect(chatApi.create).toHaveBeenCalledTimes(1)
    expect(chatApi.send).toHaveBeenCalledTimes(1)
    expect(vi.mocked(chatApi.send).mock.calls[0]?.slice(0, 2)).toEqual(['qa-conversation', 'câu hỏi fixture'])
    expect(store.busy).toBe(false)
    expect(store.pendingMessage).toBeNull()
  })

  it('FE-STORE-003 | Retry văn bản sau lỗi dùng lại request_id; đổi câu dùng UUID mới', async () => {
    const store = useChatStore()
    store.active = conversation()
    vi.mocked(chatApi.send).mockRejectedValue(new Error('mock outage'))
    await store.send('câu hỏi fixture')
    await store.send('câu hỏi fixture')
    await store.send('câu khác fixture')
    const calls = vi.mocked(chatApi.send).mock.calls
    expect(calls[0]?.[2]).toBe(calls[1]?.[2])
    expect(calls[2]?.[2]).not.toBe(calls[1]?.[2])
  })

  it('FE-STORE-004 | Gửi thành công rồi lặp nội dung là một lượt mới', async () => {
    const store = useChatStore()
    store.active = conversation()
    await store.send('câu hỏi fixture')
    await store.send('câu hỏi fixture')
    const calls = vi.mocked(chatApi.send).mock.calls
    expect(calls[0]?.[2]).not.toBe(calls[1]?.[2])
  })

  it('FE-STORE-005 | Đang tải thì chặn gửi, chọn và tạo hội thoại', async () => {
    const store = useChatStore()
    store.loading = true
    await store.send('hỏi')
    await store.select('other')
    await store.newConversation()
    expect(chatApi.send).not.toHaveBeenCalled()
    expect(chatApi.get).not.toHaveBeenCalled()
    expect(chatApi.create).not.toHaveBeenCalled()
  })

  it('FE-STORE-006 | Đang gửi thì chặn gửi trùng và xóa cùng hội thoại', async () => {
    const store = useChatStore()
    store.active = conversation()
    const pending = deferred<ReturnType<typeof conversation>>()
    vi.mocked(chatApi.send).mockReturnValue(pending.promise)
    const first = store.send('câu hỏi fixture')
    expect(store.busy).toBe(true)
    await store.send('gửi trùng')
    await store.remove('qa-conversation')
    expect(chatApi.send).toHaveBeenCalledTimes(1)
    expect(chatApi.remove).not.toHaveBeenCalled()
    pending.resolve(conversation())
    await first
    expect(store.busy).toBe(false)
  })

  it('FE-STORE-007 | Nội dung rỗng hoặc toàn khoảng trắng không tạo hội thoại', async () => {
    const store = useChatStore()
    await store.send('')
    await store.send(' \t\n ')
    expect(chatApi.create).not.toHaveBeenCalled()
    expect(chatApi.send).not.toHaveBeenCalled()
  })

  it('FE-STORE-008 | Hai lần gửi khi chưa có hội thoại phải chỉ tạo một hội thoại', async () => {
    const store = useChatStore()
    const pending = deferred<ReturnType<typeof conversation>>()
    vi.mocked(chatApi.create).mockReturnValue(pending.promise)
    const first = store.send('câu hỏi thứ nhất')
    const second = store.send('câu hỏi thứ hai')
    const creates = vi.mocked(chatApi.create).mock.calls.length
    pending.resolve(conversation())
    await Promise.all([first, second])
    expect(creates).toBe(1)
    expect(chatApi.send).toHaveBeenCalledTimes(1)
  })
})
