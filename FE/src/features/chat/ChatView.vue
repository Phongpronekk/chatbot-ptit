<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { useChatStore } from './chat.store'
import { renderMarkdown } from './chat.markdown'
import MessageBubble from './components/MessageBubble.vue'
import ChatInput from './components/ChatInput.vue'
const chat = useChatStore()
const sidebarOpen = ref(false)
const messageList = ref<HTMLElement>()
const suggestions = [
  'Có những câu lạc bộ nào?',
  'KTX B2 mức thu bao nhiêu?',
  'Điều kiện đăng ký thực tập tốt nghiệp?',
  'Mức học phí và chính sách hỗ trợ sinh viên?',
]
onMounted(() => { void chat.load() })
function select(id: string) { void chat.select(id); sidebarOpen.value = false }
function create() { void chat.newConversation(); sidebarOpen.value = false }
watch(() => [chat.activeId, chat.active?.messages.length, chat.sending, chat.streamingText], async () => {
  await nextTick()
  messageList.value?.scrollTo({ top: messageList.value.scrollHeight, behavior: 'smooth' })
})
</script>
<template>
  <div class="chat-shell" @keydown.esc="sidebarOpen = false">
    <button v-if="sidebarOpen" class="sidebar-backdrop" aria-label="Đóng lịch sử trò chuyện" @click="sidebarOpen = false" />
    <aside id="chat-sidebar" class="sidebar" :class="{ 'is-open': sidebarOpen }" aria-label="Lịch sử trò chuyện">
      <div class="brand"><span class="ptit-mark" aria-hidden="true">P</span><span>PTIT Chat</span>
        <button class="close-sidebar icon-button" aria-label="Đóng lịch sử" @click="sidebarOpen = false">×</button>
      </div>
      <button class="new-chat" :disabled="chat.loading" @click="create"><span aria-hidden="true">＋</span>Cuộc trò chuyện mới</button>
      <nav class="history" aria-label="Cuộc trò chuyện">
        <p v-if="!chat.loading && !chat.conversations.length" class="empty-history">Chưa có cuộc trò chuyện.</p>
        <section v-for="group in chat.groups" :key="group.label" class="history-group">
          <h2>{{ group.label }}</h2>
          <div v-for="item in group.items" :key="item.id" class="history-entry">
          <button
            class="history-item" :class="{ active: item.id === chat.activeId, unread: chat.isUnread(item.id) }"
            :aria-current="item.id === chat.activeId ? 'page' : undefined" :title="item.title" @click="select(item.id)">
            <span class="history-title">{{ item.title }}</span>
            <span v-if="chat.isSending(item.id)" class="history-spinner" title="Đang trả lời..." aria-label="Đang trả lời" />
            <span v-else-if="chat.isUnread(item.id)" class="history-unread-badge" title="Đã có câu trả lời mới">Mới</span>
          </button>
          <button class="delete-chat" :disabled="chat.isSending(item.id)" :aria-label="`Xóa cuộc trò chuyện ${item.title}`" @click="chat.remove(item.id)">×</button>
          </div>
        </section>
      </nav>
    </aside>
    <main class="chat-main">
      <header class="chat-header">
        <button class="menu-button icon-button" aria-label="Mở lịch sử trò chuyện" aria-controls="chat-sidebar" :aria-expanded="sidebarOpen" @click="sidebarOpen = !sidebarOpen">☰</button>
        <div><h1>Trợ lý sinh viên PTIT</h1><p>Hỗ trợ thông tin học tập</p>
          <span v-if="chat.health" class="connection-status">{{ chat.health.source_count }} nguồn dữ liệu · {{ chat.health.llm_configured ? `${chat.health.llm_provider === 'ollama' ? 'Ollama local' : (chat.health.llm_provider || 'LLM')} · ${chat.health.llm_model || 'Đã cấu hình'}` : 'Chế độ tra cứu tài liệu' }}</span>
          <span v-if="chat.health?.retrieval === 'vector'" class="connection-status"> · RAG Chroma + embedding local</span>
          <span v-if="chat.health?.retrieval_warning" class="connection-status"> · {{ chat.health.retrieval_warning }}</span>
        </div>
      </header>
      <div v-if="chat.replyNotification" class="reply-toast" role="status" aria-live="polite">
        <button type="button" class="reply-toast-body" @click="select(chat.replyNotification.conversationId)">
          <span class="reply-toast-dot" aria-hidden="true" />
          <span>Bot đã trả lời xong trong <strong>{{ chat.replyNotification.title }}</strong> — Nhấn để mở</span>
        </button>
        <button type="button" class="reply-toast-close" aria-label="Đóng thông báo" @click="chat.dismissNotification">×</button>
      </div>
      <div v-if="chat.error" class="api-error" role="alert">{{ chat.error }} <button :disabled="chat.loading" @click="chat.load">Tải lại</button></div>
      <div ref="messageList" class="message-list" role="log" aria-label="Nội dung trò chuyện" aria-live="polite" tabindex="0">
        <p v-if="chat.loading" class="chat-notice" role="status">Đang tải cuộc trò chuyện…</p>
        <div v-else-if="!chat.active?.messages.length && !chat.sending" class="empty-chat">
          <span class="ptit-mark" aria-hidden="true">P</span>
          <h2>Bắt đầu cuộc trò chuyện</h2>
          <p>Nhập câu hỏi về PTIT hoặc nhấn + để hỏi đáp theo file PDF, Word, Excel.</p>
          <div class="suggestion-chips" aria-label="Gợi ý câu hỏi nhanh">
            <button
              v-for="question in suggestions"
              :key="question"
              type="button"
              class="suggestion-chip"
              @click="chat.send(question)"
            >
              {{ question }}
            </button>
          </div>
        </div>
        <MessageBubble v-for="message in chat.active?.messages" :key="message.id" :message="message" @feedback="chat.sendFeedback" />
        <MessageBubble v-if="chat.pendingMessage" :message="chat.pendingMessage" />
        <article v-if="chat.sending" class="message assistant" role="status" aria-label="Chatbot đang suy nghĩ">
          <span class="ptit-mark message-avatar" aria-hidden="true">P</span>
          <div class="message-content">
            <div class="bubble">
              <div v-if="chat.streamingText" class="markdown-body" v-html="renderMarkdown(chat.streamingText)" />
              <p v-else>{{ chat.uploadingName ? `Đang tải và đọc ${chat.uploadingName}…` : 'Đang trả lời…' }}</p>
            </div>
          </div>
        </article>
      </div>
      <ChatInput :key="chat.activeId" :busy="chat.busy" :sent-version="chat.sentVersion" :draft-to-restore="chat.draftToRestore"
        :attachments="chat.draftAttachments" :has-file-context="chat.contextDocuments.length > 0" :source-scope="chat.sourceScope"
        @send="chat.send" @attach="chat.queueFiles" @remove-attachment="chat.removeDraftAttachment"
        @change-scope="chat.sourceScope = $event" />
    </main>
  </div>
</template>
