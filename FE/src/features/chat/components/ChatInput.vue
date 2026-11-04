<script setup lang="ts">
import { ref, watch } from 'vue'
import type { MessageAttachment, RetrievalScope } from '../chat.types'
const props = defineProps<{
  busy: boolean; sentVersion: number; draftToRestore: { text: string } | null
  attachments: MessageAttachment[]; hasFileContext: boolean
  sourceScope: RetrievalScope
}>()
const emit = defineEmits<{
  send: [text: string]; attach: [files: File[]]; removeAttachment: [id: string]
  changeScope: [scope: RetrievalScope]
}>()
const draft = ref('')
const fileInput = ref<HTMLInputElement>()
function chooseFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  if (files.length) emit('attach', files)
}
function submit() {
  if (props.busy || (!draft.value.trim() && !props.attachments.length)) return
  emit('send', draft.value)
}
watch(() => props.sentVersion, () => { draft.value = '' })
watch(() => props.draftToRestore, value => { if (value) draft.value = value.text })
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    submit()
  }
}
</script>
<template>
  <form class="composer" @submit.prevent="submit">
    <label v-if="hasFileContext || attachments.length" class="source-picker">
      Nguồn cho câu hỏi này:
      <select :value="attachments.length ? 'documents' : sourceScope" :disabled="busy || attachments.length > 0"
        aria-label="Nguồn trả lời cho câu hỏi này" @change="emit('changeScope', ($event.target as HTMLSelectElement).value as RetrievalScope)">
        <option value="auto">Tự động</option>
        <option value="knowledge">Kho dữ liệu PTIT</option>
        <option value="documents">File đã tải lên</option>
      </select>
    </label>
    <div v-if="attachments.length" class="attachment-panel" aria-label="File đính kèm chờ gửi">
      <div class="attachment-list">
        <div v-for="file in attachments" :key="file.id" class="attachment-chip">
          <span class="attachment-icon" aria-hidden="true">▤</span>
          <div class="attachment-info">
            <span class="attachment-name" :title="file.filename">{{ file.filename }}</span>
            <small>{{ Math.ceil(file.size / 1024) }} KB · Chờ gửi</small>
          </div>
          <button type="button" :disabled="busy" :aria-label="`Bỏ file ${file.filename} khỏi tin nhắn`"
            class="remove-attachment" @click="emit('removeAttachment', file.id)">×</button>
        </div>
      </div>
    </div>
    <div class="composer-row">
      <input ref="fileInput" type="file" hidden multiple accept=".pdf,.docx,.xlsx,.xls"
        aria-label="Chọn file PDF, Word hoặc Excel" :disabled="busy" @change="chooseFiles" />
      <button class="attach-button" type="button" :disabled="busy || attachments.length >= 5"
        aria-label="Tải lên file PDF, Word hoặc Excel" title="Tải lên PDF, Word, Excel"
        @click="fileInput?.click()">+</button>
      <textarea v-model="draft" aria-label="Tin nhắn của bạn" aria-describedby="composer-help"
        :placeholder="attachments.length ? 'Nhập câu hỏi kèm file...' : sourceScope === 'documents' ? 'Đặt câu hỏi về file...' : 'Nhập tin nhắn của bạn...'"
        rows="1" maxlength="4000" :disabled="busy" @keydown="onKeydown" />
      <button class="send-button" type="submit" :disabled="busy || (!draft.trim() && !attachments.length)" aria-label="Gửi tin nhắn">
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m4 3 17 9L4 21l3-8 8-1-8-1-3-8Z" fill="currentColor" /></svg>
      </button>
    </div>
    <p id="composer-help" class="composer-help">Enter để gửi · Shift + Enter để xuống dòng
      <span class="upload-help">PDF, DOCX, XLSX, XLS · Tối đa 5 file, 10 MB/file · Lưu tạm 2 giờ</span>
    </p>
  </form>
</template>
