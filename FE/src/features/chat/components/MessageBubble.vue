<script setup lang="ts">
import type { Message } from '../chat.types'
defineProps<{ message: Message }>()
function safeUrl(value: string) {
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) ? url.href : undefined
  } catch { return undefined }
}
function time(value: string) {
  return new Intl.DateTimeFormat('vi-VN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date(value))
}
</script>
<template>
  <article class="message" :class="message.role" :aria-label="message.role === 'user' ? 'Bạn' : 'Trợ lý PTIT'">
    <span v-if="message.role === 'assistant'" class="ptit-mark message-avatar" aria-hidden="true">P</span>
    <div class="message-content">
      <div class="bubble">
        <p>{{ message.text }}</p>
      </div>
      <div v-if="message.sources.length" class="sources">
        <details v-for="(source, index) in message.sources" :key="`${source.source_file}-${index}`">
          <summary>[{{ index + 1 }}] {{ source.title || source.topic_group }}</summary>
          <p class="source-note">Ngày thu thập: {{ source.fetched_date }}</p>
          <p v-if="source.note" class="source-note">{{ source.note }}</p>
          <p class="source-content">{{ source.content }}</p>
          <a v-if="safeUrl(source.source_url)" :href="safeUrl(source.source_url)" target="_blank" rel="noopener noreferrer">Xem nguồn chính thức ↗</a>
        </details>
      </div>
      <span class="message-time">{{ time(message.created_at) }}<template v-if="message.role === 'assistant'"> · {{ message.mode === 'llm' ? 'Trả lời từ tài liệu' : 'Trích xuất tài liệu' }}</template></span>
    </div>
  </article>
</template>
