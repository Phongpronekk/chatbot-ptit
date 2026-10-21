import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { chatApi } from './chat.service'
import type { Conversation, ConversationSummary, Health } from './chat.types'

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<ConversationSummary[]>([])
  const active = ref<Conversation | null>(null)
  const loading = ref(false)
  const sending = ref(false)
  const error = ref('')
  const health = ref<Health | null>(null)
  const sentVersion = ref(0)
  const activeId = computed(() => active.value?.id ?? '')
  const busy = computed(() => loading.value || sending.value)
  let retry: { conversationId: string; text: string; requestId: string } | null = null

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
    try { active.value = await chatApi.get(id) }
    catch (cause) { report(cause) }
    finally { loading.value = false }
  }
  async function newConversation() {
    if (busy.value) return
    loading.value = true
    error.value = ''
    try { receive(await chatApi.create()) }
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
        active.value = null
        const first = conversations.value[0]
        if (first) active.value = await chatApi.get(first.id)
      }
    } catch (cause) { report(cause) }
    finally { loading.value = false }
  }
  async function send(text: string) {
    if (busy.value || !text.trim()) return
    sending.value = true
    error.value = ''
    try {
      if (!active.value) receive(await chatApi.create())
      const conversation = active.value!
      const content = text.trim()
      if (retry?.conversationId !== conversation.id || retry.text !== content) {
        retry = { conversationId: conversation.id, text: content, requestId: crypto.randomUUID() }
      }
      receive(await chatApi.send(conversation.id, content, retry.requestId))
      retry = null
      sentVersion.value++
    } catch (cause) { report(cause) }
    finally { sending.value = false }
  }
  return { conversations, active, activeId, groups, loading, sending, busy, error, health, sentVersion,
    load, select, newConversation, remove, send }
})
