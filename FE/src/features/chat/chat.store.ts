import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { chatApi } from './chat.service'
import type { Conversation, ConversationSummary, DraftAttachment, Health, Message, RetrievalScope } from './chat.types'

interface RetryInfo {
  conversationId: string
  text: string
  requestId: string
  documentIds: string[]
  attachmentIds: string[]
  scope: RetrievalScope
}

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<ConversationSummary[]>([])
  const active = ref<Conversation | null>(null)
  const loading = ref(false)
  const sendingConvs = ref<Set<string>>(new Set())
  const unreadConvs = ref<Set<string>>(new Set())
  const replyNotification = ref<{ conversationId: string; title: string } | null>(null)
  let notificationTimer: ReturnType<typeof setTimeout> | null = null
  const uploadingNames = ref<Map<string, string>>(new Map())
  const pendingMessages = ref<Map<string, Message>>(new Map())
  const streamingTexts = ref<Map<string, string>>(new Map())
  const conversationCache = new Map<string, Conversation>()
  const retries = new Map<string, RetryInfo>()

  const draftFiles = ref<DraftAttachment[]>([])
  const sourceScope = ref<RetrievalScope>('auto')
  const error = ref('')
  const health = ref<Health | null>(null)
  const sentVersion = ref(0)
  const draftToRestore = ref<{ text: string } | null>(null)

  const activeId = computed(() => active.value?.id ?? '')
  const sending = computed(() => (activeId.value ? sendingConvs.value.has(activeId.value) : false))
  const uploadingName = computed(() => (activeId.value ? uploadingNames.value.get(activeId.value) ?? '' : ''))
  const pendingMessage = computed(() => (activeId.value ? pendingMessages.value.get(activeId.value) ?? null : null))
  const streamingText = computed(() => (activeId.value ? streamingTexts.value.get(activeId.value) ?? '' : ''))
  const busy = computed(() => loading.value || sending.value)

  function isSending(id?: string): boolean {
    if (!id) return sendingConvs.value.size > 0
    return sendingConvs.value.has(id)
  }

  function isUnread(id: string): boolean {
    return unreadConvs.value.has(id)
  }

  function clearUnread(id: string) {
    if (!unreadConvs.value.has(id)) return
    const next = new Set(unreadConvs.value)
    next.delete(id)
    unreadConvs.value = next
    if (replyNotification.value?.conversationId === id) {
      replyNotification.value = null
    }
  }

  function dismissNotification() {
    if (notificationTimer) {
      clearTimeout(notificationTimer)
      notificationTimer = null
    }
    replyNotification.value = null
  }

  function notifyReplyReady(conversationId: string, title: string) {
    const isAwayFromConv = activeId.value !== conversationId
    const isTabHidden = typeof document !== 'undefined' && document.hidden

    if (isAwayFromConv) {
      const nextUnread = new Set(unreadConvs.value)
      nextUnread.add(conversationId)
      unreadConvs.value = nextUnread

      replyNotification.value = { conversationId, title }
      if (notificationTimer) clearTimeout(notificationTimer)
      notificationTimer = setTimeout(() => {
        if (replyNotification.value?.conversationId === conversationId) {
          replyNotification.value = null
        }
      }, 6000)
    }

    if ((isAwayFromConv || isTabHidden) && typeof window !== 'undefined' && 'Notification' in window) {
      if (Notification.permission === 'granted') {
        try {
          new Notification('Trợ lý sinh viên PTIT', {
            body: `Bot đã trả lời xong trong "${title}"`,
          })
        } catch {
          // Ignore notification errors in restricted environments
        }
      }
    }
  }

  const draftAttachments = computed(() => draftFiles.value.map(item => ({
    id: item.id, filename: item.file.name, size: item.file.size,
  })))

  const contextDocuments = computed(() => {
    const messages = [...(active.value?.messages ?? [])].reverse()
    const latestUpload = messages.find(message => message.attachments?.length)
    const legacyAnswer = messages.find(message => message.sources.some(source => source.document_id))
    const sentIds = new Set(latestUpload
      ? latestUpload.attachments.map(file => file.id)
      : legacyAnswer?.sources.flatMap(source => source.document_id ? [source.document_id] : []) ?? [])
    return active.value?.documents.filter(file => sentIds.has(file.id)) ?? []
  })

  const groups = computed(() => {
    const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' })
    const yesterday = new Date(Date.now() - 86_400_000).toLocaleDateString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' })
    const result = new Map<string, ConversationSummary[]>()
    for (const conversation of conversations.value) {
      const date = new Date(conversation.updated_at).toLocaleDateString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' })
      const label = date === today ? 'Hôm nay' : date === yesterday ? 'Hôm qua' : 'Trước đó'
      if (!result.has(label)) result.set(label, [])
      result.get(label)!.push(conversation)
    }
    return Array.from(result, ([label, items]) => ({ label, items }))
  })

  function receive(conversation: Conversation, setActive = true) {
    conversationCache.set(conversation.id, conversation)
    if (setActive || activeId.value === conversation.id || !active.value) {
      active.value = conversation
    }
    conversations.value = [
      { id: conversation.id, title: conversation.title, created_at: conversation.created_at, updated_at: conversation.updated_at },
      ...conversations.value.filter(item => item.id !== conversation.id),
    ].sort((a, b) => b.updated_at.localeCompare(a.updated_at))
  }

  function report(cause: unknown) {
    error.value = cause instanceof Error ? cause.message : 'Có lỗi xảy ra. Vui lòng thử lại.'
  }

  function resetDraft() {
    draftFiles.value = []
    draftToRestore.value = null
    sourceScope.value = 'auto'
  }

  async function load() {
    if (loading.value) return
    loading.value = true
    error.value = ''
    try {
      conversations.value = await chatApi.list()
      const first = conversations.value.find(item => item.id === activeId.value) ?? conversations.value[0]
      if (first) {
        const data = await chatApi.get(first.id)
        conversationCache.set(first.id, data)
        active.value = data
      } else {
        active.value = null
      }
      health.value = await chatApi.health()
    } catch (cause) { report(cause) }
    finally { loading.value = false }
  }

  async function select(id: string) {
    clearUnread(id)
    if (loading.value || activeId.value === id) return
    error.value = ''
    const cached = conversationCache.get(id)
    if (cached) {
      active.value = cached
      resetDraft()
      return
    }
    loading.value = true
    try {
      const data = await chatApi.get(id)
      conversationCache.set(id, data)
      active.value = data
      clearUnread(id)
      resetDraft()
    } catch (cause) { report(cause) }
    finally { loading.value = false }
  }

  async function newConversation() {
    if (loading.value) return
    loading.value = true
    error.value = ''
    try {
      const created = await chatApi.create()
      receive(created, true)
      resetDraft()
    } catch (cause) { report(cause) }
    finally { loading.value = false }
  }

  async function remove(id: string) {
    if (sendingConvs.value.has(id)) return
    error.value = ''
    const previousConversations = [...conversations.value]
    const previousActive = active.value
    const cachedRemoved = conversationCache.get(id)
    const wasActive = activeId.value === id

    clearUnread(id)
    conversations.value = conversations.value.filter(item => item.id !== id)
    conversationCache.delete(id)
    retries.delete(id)

    if (wasActive) {
      resetDraft()
      const first = conversations.value[0]
      if (first) {
        const cached = conversationCache.get(first.id)
        active.value = cached ?? null
      } else {
        active.value = null
      }
    }

    try {
      await chatApi.remove(id)
      if (wasActive && !active.value && conversations.value[0]) {
        const firstId = conversations.value[0].id
        const data = await chatApi.get(firstId)
        conversationCache.set(firstId, data)
        if (!active.value || activeId.value === firstId) {
          active.value = data
        }
      }
    } catch (cause) {
      conversations.value = previousConversations
      if (cachedRemoved) conversationCache.set(id, cachedRemoved)
      if (wasActive) active.value = previousActive
      report(cause)
    }
  }

  async function send(text: string) {
    if (busy.value || (!text.trim() && !draftFiles.value.length)) return
    error.value = ''
    const staged = draftFiles.value
    const requestedScope = staged.length ? 'documents' : sourceScope.value
    draftFiles.value = []
    const content = text.trim() || 'Tóm tắt nội dung chính của file đính kèm.'

    if (!active.value) {
      const created = await chatApi.create()
      receive(created, true)
    }
    const conversation = active.value!
    const targetId = conversation.id
    clearUnread(targetId)
    conversationCache.set(targetId, conversation)

    if (typeof window !== 'undefined' && 'Notification' in window && Notification.permission === 'default') {
      void Notification.requestPermission().catch(() => undefined)
    }

    const nextSending = new Set(sendingConvs.value)
    nextSending.add(targetId)
    sendingConvs.value = nextSending

    const pending: Message = {
      id: crypto.randomUUID(), role: 'user', text: content,
      created_at: new Date().toISOString(), mode: 'user', sources: [],
      attachments: staged.map(item => ({ id: item.id, filename: item.file.name, size: item.file.size })),
      pending: true,
    }
    const nextPending = new Map(pendingMessages.value)
    nextPending.set(targetId, pending)
    pendingMessages.value = nextPending
    sentVersion.value++

    try {
      for (const item of staged) {
        if (!item.uploaded || Date.parse(item.uploaded.expires_at) <= Date.now()) {
          const nextUploading = new Map(uploadingNames.value)
          nextUploading.set(targetId, item.file.name)
          uploadingNames.value = nextUploading
          item.uploaded = await chatApi.upload(targetId, item.file)
          conversation.documents.push(item.uploaded)
        }
      }
      const nextUploading = new Map(uploadingNames.value)
      nextUploading.delete(targetId)
      uploadingNames.value = nextUploading

      const attachmentIds = staged.map(item => item.uploaded!.id)
      const documentIds = [...new Set([
        ...(!attachmentIds.length && requestedScope !== 'knowledge' ? contextDocuments.value.map(item => item.id) : []), ...attachmentIds,
      ])]

      let convRetry = retries.get(targetId)
      if (convRetry?.conversationId !== targetId || convRetry.text !== content ||
          convRetry.documentIds.join() !== documentIds.join() || convRetry.attachmentIds.join() !== attachmentIds.join() ||
          convRetry.scope !== requestedScope) {
        convRetry = { conversationId: targetId, text: content, requestId: crypto.randomUUID(), documentIds, attachmentIds, scope: requestedScope }
        retries.set(targetId, convRetry)
      }

      const updated = await chatApi.send(
        targetId,
        content,
        convRetry.requestId,
        convRetry.documentIds,
        convRetry.attachmentIds,
        convRetry.scope,
        (delta: string) => {
          const nextStream = new Map(streamingTexts.value)
          nextStream.set(targetId, (nextStream.get(targetId) ?? '') + delta)
          streamingTexts.value = nextStream
        },
      )
      retries.delete(targetId)
      sourceScope.value = 'auto'
      const wasInTarget = activeId.value === targetId
      receive(updated, wasInTarget)
      notifyReplyReady(targetId, updated.title || conversation.title)
    } catch (cause) {
      const errorText = cause instanceof Error ? cause.message : 'Có lỗi xảy ra khi xử lý tin nhắn.'
      if (staged.length) {
        report(cause)
        if (activeId.value === targetId) {
          draftFiles.value = staged
          draftToRestore.value = { text }
        }
      } else {
        error.value = ''
        const userMsg: Message = {
          id: crypto.randomUUID(),
          role: 'user',
          text: content,
          created_at: new Date().toISOString(),
          mode: 'user',
          sources: [],
          attachments: [],
        }
        const assistantMsg: Message = {
          id: crypto.randomUUID(),
          role: 'assistant',
          text: errorText,
          created_at: new Date().toISOString(),
          mode: 'retrieval_only',
          sources: [],
          attachments: [],
        }
        conversation.messages.push(userMsg, assistantMsg)
        conversationCache.set(targetId, conversation)
        if (activeId.value === targetId) {
          active.value = { ...conversation }
        } else {
          notifyReplyReady(targetId, conversation.title)
        }
      }
    } finally {
      const clearPending = new Map(pendingMessages.value)
      clearPending.delete(targetId)
      pendingMessages.value = clearPending

      const clearStream = new Map(streamingTexts.value)
      clearStream.delete(targetId)
      streamingTexts.value = clearStream

      const clearUploading = new Map(uploadingNames.value)
      clearUploading.delete(targetId)
      uploadingNames.value = clearUploading

      const clearSending = new Set(sendingConvs.value)
      clearSending.delete(targetId)
      sendingConvs.value = clearSending
    }
  }

  async function sendFeedback(messageId: string, rating: 1 | -1) {
    const conv = active.value
    if (!conv) return
    const msg = conv.messages.find(m => m.id === messageId)
    const previous = msg?.feedback ?? null
    if (msg) msg.feedback = rating
    try {
      await chatApi.feedback(messageId, rating)
    } catch {
      if (msg) msg.feedback = previous
    }
  }

  function queueFiles(files: File[]) {
    if (busy.value || !files.length) return
    error.value = ''
    const uploadedDraftIds = new Set(draftFiles.value.flatMap(item => item.uploaded ? [item.uploaded.id] : []))
    const existing = active.value?.documents.filter(item => !uploadedDraftIds.has(item.id)).length ?? 0
    if (files.length + draftFiles.value.length + existing > 5) {
      error.value = 'Mỗi cuộc trò chuyện tối đa 5 file. Hãy bỏ bớt file hoặc tạo cuộc trò chuyện mới.'
      return
    }
    for (const file of files) {
      if (!/\.(pdf|docx|xlsx|xls)$/i.test(file.name)) {
        error.value = 'Chỉ hỗ trợ PDF, Word (.docx), Excel (.xlsx, .xls).'
        return
      }
      if (file.size > 10 * 1024 * 1024 || !file.size) {
        error.value = 'File phải có nội dung và không vượt 10 MB.'
        return
      }
    }
    draftFiles.value.push(...files.map(file => ({ id: crypto.randomUUID(), file })))
  }

  async function removeDraftAttachment(id: string) {
    if (busy.value) return
    const item = draftFiles.value.find(file => file.id === id)
    if (!item) return
    loading.value = true
    error.value = ''
    try {
      if (item.uploaded && active.value && Date.parse(item.uploaded.expires_at) > Date.now()) {
        await chatApi.removeDocument(active.value.id, item.uploaded.id)
        active.value.documents = active.value.documents.filter(file => file.id !== item.uploaded!.id)
      }
      draftFiles.value = draftFiles.value.filter(file => file.id !== id)
      if (activeId.value) retries.delete(activeId.value)
    } catch (cause) { report(cause) }
    finally { loading.value = false }
  }

  return {
    conversations, active, activeId, groups, loading, sending, uploadingName, sourceScope, busy, error, health, sentVersion,
    pendingMessage, streamingText, draftToRestore, draftAttachments, contextDocuments,
    replyNotification,
    isSending, isUnread, clearUnread, dismissNotification,
    load, select, newConversation, remove, send, sendFeedback, queueFiles, removeDraftAttachment,
  }
})
