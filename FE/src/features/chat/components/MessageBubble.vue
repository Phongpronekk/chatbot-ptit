<script setup lang="ts">
import { computed } from 'vue'
import type { Message, Source } from '../chat.types'
import { renderMarkdown } from '../chat.markdown'
const props = defineProps<{ message: Message }>()
const sourceGroups = computed(() => {
  const groups = new Map<string, { source: Source; refs: { source: Source; index: number }[] }>()
  props.message.sources.forEach((source, index) => {
    const key = source.document_id || source.source_url || source.source_file
    if (!groups.has(key)) groups.set(key, { source, refs: [] })
    groups.get(key)!.refs.push({ source, index: index + 1 })
  })
  return [...groups.values()]
})
const answerHtml = computed(() => renderMarkdown(props.message.text))
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
        <div v-if="message.attachments?.length" class="message-attachments" aria-label="File đã gửi cùng tin nhắn">
          <div v-for="file in message.attachments" :key="file.id" class="message-attachment">
            <span class="file-kind" aria-hidden="true">{{ file.filename.split('.').pop()?.toUpperCase() }}</span>
            <div class="attachment-info">
              <span class="attachment-name" :title="file.filename">{{ file.filename }}</span>
              <small>{{ Math.ceil(file.size / 1024) }} KB</small>
            </div>
          </div>
        </div>
        <div v-if="message.role === 'assistant' && message.text" class="markdown-body" v-html="answerHtml" />
        <p v-else-if="message.text">{{ message.text }}</p>
      </div>
      <div v-if="message.sources.length" class="sources">
        <p class="source-origin">{{ message.sources.some(source => source.document_id) ? 'Nguồn trả lời: File đã tải lên' : 'Nguồn trả lời: Kho dữ liệu PTIT' }}</p>
        <details v-for="group in sourceGroups" :key="group.source.document_id || group.source.source_url || group.source.source_file">
          <summary>[{{ group.refs.map(ref => ref.index).join(', ') }}] {{ group.source.document_id ? group.source.source_file : group.source.title || group.source.topic_group }}
            <small v-if="group.refs.length > 1"> · {{ group.refs.length }} đoạn trích</small>
          </summary>
          <p v-if="group.source.publish_date" class="source-note">Ngày đăng: {{ group.source.publish_date }}</p>
          <p v-if="!group.source.document_id" class="source-note">Ngày thu thập: {{ group.source.fetched_date }}</p>
          <p v-if="group.source.note" class="source-note">{{ group.source.note }}</p>
          <details v-for="ref in group.refs" :key="ref.index" class="source-excerpt">
            <summary>[{{ ref.index }}] {{ ref.source.location || 'Xem đoạn trích' }}</summary>
            <div class="source-content markdown-body" v-html="renderMarkdown(ref.source.content)" />
          </details>
          <a v-if="safeUrl(group.source.source_url)" :href="safeUrl(group.source.source_url)" target="_blank" rel="noopener noreferrer">Xem nguồn chính thức ↗</a>
        </details>
      </div>
      <span class="message-time">{{ message.pending ? 'Đang gửi…' : time(message.created_at) }}<template v-if="message.role === 'assistant'"> · {{ message.mode === 'llm' ? 'Trả lời từ tài liệu' : 'Trích xuất tài liệu' }}</template></span>
    </div>
  </article>
</template>
