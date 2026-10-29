import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { chatApi } from './chat.service'
import type { Conversation, ConversationSummary, DraftAttachment, Health, Message, RetrievalScope } from './chat.types'

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<ConversationSummary[]>([])
  const active = ref<Conversation | null>(null)
  const loading = ref(false)
  const sending = ref(false)
  const uploadingName = ref('')
  const draftFiles = ref<DraftAttachment[]>([])
  const sourceScope = ref<RetrievalScope>('auto')
  const error = ref('')
  const health = ref<Health | null>(null)
  const sentVersion = ref(0)
  const pendingMessage = ref<Message | null>(null)
  const draftToRestore = ref<{ text: string } | null>(null)
  const activeId = computed(() => active.value?.id ?? '')
  const busy = computed(() => loading.value || sending.value)
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
  let retry: { conversationId: string; text: string; requestId: string; documentIds: string[]; attachmentIds: string[]; scope: RetrievalScope } | null = null

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

  function receive(conversation: Conversation) {
    active.value = conversation
    conversations.value = [conversation, ...conversations.value.filter(item => item.id !== conversation.id)]
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
  }
  function report(cause: unknown) {
    error.value = cause instanceof Error ? cause.message : 'Có lỗi xảy ra. Vui lòng thử lại.'
  }
  function resetDraft() {
    draftFiles.value = []
    draftToRestore.value = null
    retry = null
    sourceScope.value = 'auto'
  }
  async function load() {
    if (busy.value) return
    loading.value = true
    error.value = ''
    try {
      conversations.value = await chatApi.list()
      const first = conversations.value.find(item => item.id === activeId.value) ?? conversations.value[0]
      active.value = first ? await chatApi.get(first.id) : null
      health.value = await chatApi.health()
    } catch (cause) { report(cause) }
    finally { loading.value = false }
  }
  async function select(id: string) {
    if (busy.value) return
    loading.value = true
    error.value = ''
    try { active.value = await chatApi.get(id); resetDraft() }
    catch (cause) { report(cause) }
    finally { loading.value = false }
  }
  async function newConversation() {
    if (busy.value) return
    loading.value = true
    error.value = ''
    try { receive(await chatApi.create()); resetDraft() }
    catch (cause) { report(cause) }
    finally { loading.value = false }
  }
  async function remove(id: string) {
    if (busy.value) return
    loading.value = true
    error.value = ''
    try {
      await chatApi.remove(id)
      conversations.value = conversations.value.filter(item => item.id !== id)
      if (activeId.value === id) {
        resetDraft()
        active.value = null
        const first = conversations.value[0]
        if (first) active.value = await chatApi.get(first.id)
      }
    } catch (cause) { report(cause) }
    finally { loading.value = false }
  }
  async function send(text: string) {
    if (busy.value || (!text.trim() && !draftFiles.value.length)) return
    sending.value = true
    error.value = ''
    const staged = draftFiles.value
    const requestedScope = staged.length ? 'documents' : sourceScope.value
    draftFiles.value = []
    const content = text.trim() || 'Tóm tắt nội dung chính của file đính kèm.'
    pendingMessage.value = {
      id: crypto.randomUUID(), role: 'user', text: content,
      created_at: new Date().toISOString(), mode: 'user', sources: [],
      attachments: staged.map(item => ({ id: item.id, filename: item.file.name, size: item.file.size })),
      pending: true,
    }
    sentVersion.value++
    try {
      if (!active.value) receive(await chatApi.create())
      const conversation = active.value!
      for (const item of staged) {
        if (!item.uploaded || Date.parse(item.uploaded.expires_at) <= Date.now()) {
          uploadingName.value = item.file.name
          item.uploaded = await chatApi.upload(conversation.id, item.file)
          conversation.documents.push(item.uploaded)
        }
      }
      uploadingName.value = ''
      const attachmentIds = staged.map(item => item.uploaded!.id)
      const documentIds = [...new Set([
        ...(!attachmentIds.length && requestedScope !== 'knowledge' ? contextDocuments.value.map(item => item.id) : []), ...attachmentIds,
      ])]
      if (retry?.conversationId !== conversation.id || retry.text !== content ||
          retry.documentIds.join() !== documentIds.join() || retry.attachmentIds.join() !== attachmentIds.join() ||
          retry.scope !== requestedScope) {
        retry = { conversationId: conversation.id, text: content, requestId: crypto.randomUUID(), documentIds, attachmentIds, scope: requestedScope }
      }
      receive(await chatApi.send(conversation.id, content, retry.requestId, retry.documentIds, retry.attachmentIds, retry.scope))
      retry = null
      sourceScope.value = 'auto'
    } catch (cause) {
      report(cause)
      draftFiles.value = staged
      draftToRestore.value = { text }
    }
    finally { pendingMessage.value = null; sending.value = false; uploadingName.value = '' }
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
      retry = null
    } catch (cause) { report(cause) }
    finally { loading.value = false }
  }
  return { conversations, active, activeId, groups, loading, sending, uploadingName, sourceScope, busy, error, health, sentVersion, pendingMessage, draftToRestore,
    draftAttachments, contextDocuments, load, select, newConversation, remove, send, queueFiles, removeDraftAttachment }
})
