import { afterEach, describe, expect, it } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import ChatInput from '../../src/features/chat/components/ChatInput.vue'

const wrappers: VueWrapper[] = []
function input(busy = false) {
  const wrapper = mount(ChatInput, { props: { busy, sentVersion: 0, draftToRestore: null,
    attachments: [], hasFileContext: false, sourceScope: 'auto' } })
  wrappers.push(wrapper)
  return wrapper
}
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()) })

describe('ChatInput keyboard and IME', () => {
  it('FE-INPUT-001 | Enter gửi đúng nội dung và ngăn xuống dòng', async () => {
    const wrapper = input()
    await wrapper.get('textarea').setValue('Câu hỏi fixture')
    const event = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })
    wrapper.get('textarea').element.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    expect(wrapper.emitted('send')).toEqual([['Câu hỏi fixture']])
  })
  it('FE-INPUT-002 | Shift+Enter giữ hành vi xuống dòng của trình duyệt', async () => {
    const wrapper = input()
    await wrapper.get('textarea').setValue('Câu hỏi fixture')
    const event = new KeyboardEvent('keydown', { key: 'Enter', shiftKey: true, bubbles: true, cancelable: true })
    wrapper.get('textarea').element.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(false)
    expect(wrapper.emitted('send')).toBeUndefined()
  })
  it('FE-INPUT-003 | Enter khi đang composition IME không gửi', async () => {
    const wrapper = input()
    await wrapper.get('textarea').setValue('tiếng Việt đang gõ')
    const event = new KeyboardEvent('keydown', { key: 'Enter', isComposing: true, bubbles: true, cancelable: true })
    wrapper.get('textarea').element.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(false)
    expect(wrapper.emitted('send')).toBeUndefined()
  })
  it('FE-INPUT-004 | Busy vô hiệu hóa textarea/button và chặn submit', async () => {
    const wrapper = input()
    await wrapper.get('textarea').setValue('Câu hỏi fixture')
    await wrapper.setProps({ busy: true })
    await wrapper.get('form').trigger('submit')
    expect(wrapper.get('textarea').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.emitted('send')).toBeUndefined()
  })
  it('FE-INPUT-005 | Khoảng trắng không gửi khi không có file', async () => {
    const wrapper = input()
    await wrapper.get('textarea').setValue(' \t\n ')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('send')).toBeUndefined()
  })
  it('FE-INPUT-006 | Xóa draft sau khi sentVersion đổi và phục hồi khi lỗi', async () => {
    const wrapper = input()
    await wrapper.get('textarea').setValue('Câu hỏi fixture')
    await wrapper.setProps({ sentVersion: 1 })
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('')
    await wrapper.setProps({ draftToRestore: { text: 'Nội dung khôi phục' } })
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('Nội dung khôi phục')
  })
})
