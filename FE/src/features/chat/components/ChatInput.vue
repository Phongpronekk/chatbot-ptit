<script setup lang="ts">
import { ref, watch } from 'vue'
const props = defineProps<{ busy: boolean; sentVersion: number; draftToRestore: { text: string } | null }>()
const emit = defineEmits<{ send: [text: string] }>()
const draft = ref('')
function submit() {
  if (props.busy || !draft.value.trim()) return
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
    <div class="composer-row">
      <textarea v-model="draft" aria-label="Tin nhắn của bạn" aria-describedby="composer-help" placeholder="Nhập tin nhắn của bạn..."
        rows="1" maxlength="4000" :disabled="busy" @keydown="onKeydown" />
      <button class="send-button" type="submit" :disabled="busy || !draft.trim()" aria-label="Gửi tin nhắn">
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m4 3 17 9L4 21l3-8 8-1-8-1-3-8Z" fill="currentColor" /></svg>
      </button>
    </div>
    <p id="composer-help" class="composer-help">Enter để gửi · Shift + Enter để xuống dòng</p>
  </form>
</template>
