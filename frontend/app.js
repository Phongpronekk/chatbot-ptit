"use strict";

const form = document.querySelector("#chat-form");
const input = document.querySelector("#question");
const send = document.querySelector("#send");
const fileInput = document.querySelector("#upload-input");
const upload = document.querySelector("#upload");
const attachmentOptions = document.querySelector("#attachment-options");
const attachmentName = document.querySelector("#attachment-name");
const attachmentStatus = document.querySelector("#attachment-status");
const reuseFile = document.querySelector("#reuse-file");
const replaceFile = document.querySelector("#replace-file");
const skipFile = document.querySelector("#skip-file");
const status = document.querySelector("#status");
const viewport = document.querySelector("#viewport");
const welcome = document.querySelector("#welcome");
const messages = document.querySelector("#messages");
const conversationList = document.querySelector("#conversations");
const chatNotice = document.querySelector("#chat-notice");
const conversations = [];
let activeConversation = null;
let noticeTimer;
const contextTurns = [];
let contextUploadId = null;
let pending = false;
let uploading = false;
let latestFile = null;
let fileChoice = null;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function showNotice(text, kind = "success") {
  clearTimeout(noticeTimer);
  chatNotice.textContent = text;
  chatNotice.dataset.kind = kind;
  chatNotice.hidden = !text;
  if (text) noticeTimer = setTimeout(() => { chatNotice.hidden = true; }, kind === "error" ? 8000 : 4500);
}

function createConversation() {
  const conversation = {
    title: "Cuộc trò chuyện mới", firstQuestion: null, state: "new",
    nodes: [], turns: [], contextUploadId: null, latestFile: null,
    fileChoice: null, draft: "", attachmentStatus: "", scrollTop: 0,
  };
  conversations.unshift(conversation);
  return conversation;
}

function setConversationState(state) {
  activeConversation.state = state;
  renderConversations();
}

function loadingIndicator(text) {
  const indicator = element("div", "", "reply-loading");
  indicator.setAttribute("role", "status");
  const spinner = element("span", "", "spinner");
  spinner.setAttribute("aria-hidden", "true");
  indicator.append(spinner, element("span", text));
  return indicator;
}

function updateComposer() {
  const busy = pending || uploading;
  for (const button of [send, upload, reuseFile, replaceFile, skipFile]) button.disabled = busy;
  for (const button of document.querySelectorAll(".conversation-button, .conversation-delete, #new-chat, #mobile-new")) button.disabled = busy;
  send.classList.toggle("is-loading", pending);
  send.setAttribute("aria-label", pending ? "Đang nhận câu trả lời" : "Gửi câu hỏi");
  attachmentOptions.hidden = latestFile === null;
  attachmentName.textContent = latestFile?.name ?? "";
  attachmentName.title = attachmentName.textContent;
  reuseFile.setAttribute("aria-pressed", String(latestFile !== null && fileChoice === "use"));
  skipFile.setAttribute("aria-pressed", String(fileChoice === "skip"));
}

function chooseFile(choice) {
  fileChoice = choice;
  attachmentStatus.textContent = "";
  updateComposer();
  input.focus();
}

async function uploadFile(file) {
  if (!file || pending || uploading) return;
  if (file.size === 0 || file.size > 10 * 1024 * 1024) {
    attachmentStatus.textContent = "Tệp phải có nội dung và dung lượng không quá 10 MB.";
    return;
  }
  uploading = true;
  attachmentStatus.textContent = "Đang đọc và lập chỉ mục tệp…";
  updateComposer();
  try {
    const response = await fetch("/api/uploads", {
      method: "POST",
      headers: {
        "Content-Type": "application/octet-stream",
        "X-Upload-Name": encodeURIComponent(file.name),
      },
      body: file,
    });
    const result = await response.json();
    if (!response.ok) {
      attachmentStatus.textContent = result.error || "Không tải được tệp. Hãy thử lại.";
      return;
    }
    latestFile = result;
    fileChoice = "use";
    attachmentStatus.textContent = "Tệp đã sẵn sàng cho câu hỏi tiếp theo.";
    input.focus();
  } catch {
    attachmentStatus.textContent = "Không tải được tệp. Kiểm tra kết nối máy chủ rồi thử lại.";
  } finally {
    uploading = false;
    updateComposer();
  }
}

function sourceLink(label, url) {
  const anchor = element("a", label);
  anchor.href = url;
  anchor.target = "_blank";
  anchor.rel = "noopener noreferrer";
  return anchor;
}

function appendInline(parent, text) {
  const markup = /\*\*([^*]+)\*\*|\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|\x60([^\x60]+)\x60/g;
  let offset = 0;
  for (const match of text.matchAll(markup)) {
    parent.append(text.slice(offset, match.index));
    const [, bold, label, url, code] = match;
    parent.append(bold ? element("strong", bold) : url ? sourceLink(label, url) : element("code", code));
    offset = match.index + match[0].length;
  }
  parent.append(text.slice(offset));
}

function renderTable(lines) {
  const wrapper = element("div", "", "table-scroll");
  const table = element("table");
  const head = table.createTHead();
  const body = table.createTBody();
  lines.forEach((line, index) => {
    if (index === 1) return;
    const row = (index === 0 ? head : body).insertRow();
    for (const cell of line.trim().slice(1, -1).split(/(?<!\\)\|/)) {
      const node = element(index === 0 ? "th" : "td");
      if (index === 0) node.scope = "col";
      appendInline(node, cell.trim().replaceAll("\\|", "|"));
      row.append(node);
    }
  });
  wrapper.append(table);
  return wrapper;
}

function renderExcerpt(parent, text) {
  const lines = text.split("\n");
  let index = 0;
  while (index < lines.length) {
    const line = lines[index].trim();
    if (line.startsWith("|") && /^\s*\|\s*:?-{3}/.test(lines[index + 1] ?? "")) {
      const start = index;
      while (index < lines.length && lines[index].trim().startsWith("|")) index++;
      parent.append(renderTable(lines.slice(start, index)));
      continue;
    }
    if (line) {
      const paragraph = element("p");
      appendInline(paragraph, line.replace(/^[-*]\s/, "• "));
      parent.append(paragraph);
    }
    index++;
  }
}

function renderAnswer(target, { passages, answer, model, document: filename, generation_error: generationError }) {
  const heading = element("strong", "PTIT Chat");
  target.replaceChildren(heading);
  if (!passages.length) {
    target.append(element("p", filename
      ? "Chưa tìm thấy đoạn phù hợp trong " + filename + ". Hãy thử cụm từ hoặc tên mục có trong tệp."
      : "Chưa tìm thấy đoạn phù hợp. Hãy thử tên học phần, mã môn hoặc thêm học kỳ và năm học."));
    return;
  }
  if (answer) {
    renderExcerpt(target, answer);
//    target.append(element("p", "Tài liệu đã dùng · " + model));
  } else {
    target.append(element("p", filename
      ? "Mình tìm được các đoạn sau trong " + filename + "."
      : "Mình tìm được các đoạn sau trong kho tài liệu."));
  }
  if (generationError) {
    const warning = element("p", generationError, "reply-error");
    warning.setAttribute("role", "alert");
    target.append(warning);
  }
  passages.forEach(({ title, section, text, url }, index) => {
    const details = element("details", "", "source-card");
    details.open = !answer && index === 0;
    details.append(element("summary", "[" + (index + 1) + "] " + (filename ? title + " · " : "") + section));
    renderExcerpt(details, text);
    if (/^https:\/\//.test(url)) details.append(sourceLink(title + " ↗", url));
    target.append(details);
  });
}

function renderConversations() {
  conversationList.replaceChildren(...conversations.map(conversation => {
    const entry = element("li", "", "conversation-item");
    entry.classList.toggle("active", conversation === activeConversation);
    const button = element("button", "", "conversation-button");
    button.dataset.state = conversation.state;
    button.append(element("span", conversation.title, "conversation-title"));
    button.type = "button";
    button.title = conversation.title;
    button.disabled = pending || uploading;
    if (conversation === activeConversation) button.setAttribute("aria-current", "true");
    button.addEventListener("click", () => openConversation(conversation));
    const remove = element("button", "×", "conversation-delete");
    remove.type = "button";
    remove.title = "Xóa cuộc trò chuyện";
    remove.setAttribute("aria-label", "Xóa cuộc trò chuyện: " + conversation.title);
    remove.disabled = pending || uploading;
    remove.addEventListener("click", () => deleteConversation(conversation));
    entry.append(button, remove);
    return entry;
  }));
}

function deleteConversation(conversation) {
  if (pending || uploading) return;
  const index = conversations.indexOf(conversation);
  if (index < 0) return;
  conversations.splice(index, 1);
  if (conversation === activeConversation) {
    activeConversation = null;
    const next = conversations[index] ?? conversations[index - 1];
    if (next) {
      openConversation(next);
    } else {
      resetChatView();
    }
  }
  renderConversations();
  updateComposer();
  showNotice("Đã xóa cuộc trò chuyện.");
}

function saveConversation() {
  if (!activeConversation) return;
  Object.assign(activeConversation, {
    nodes: Array.from(messages.childNodes),
    turns: [...contextTurns],
    contextUploadId,
    latestFile,
    fileChoice,
    draft: input.value,
    attachmentStatus: attachmentStatus.textContent,
    scrollTop: viewport.scrollTop,
  });
}

function openConversation(conversation) {
  if (pending || uploading || conversation === activeConversation) return;
  saveConversation();
  activeConversation = conversation;
  messages.replaceChildren(...conversation.nodes);
  messages.hidden = conversation.nodes.length === 0;
  welcome.hidden = !messages.hidden;
  contextTurns.splice(0, contextTurns.length, ...conversation.turns);
  contextUploadId = conversation.contextUploadId;
  latestFile = conversation.latestFile;
  fileChoice = conversation.fileChoice;
  input.value = conversation.draft;
  attachmentStatus.textContent = conversation.attachmentStatus;
  showNotice("");
  renderConversations();
  updateComposer();
  viewport.scrollTop = conversation.scrollTop;
  input.focus();
}

async function readAnswer(response, target) {
  if (!response.headers.get("Content-Type")?.startsWith("application/x-ndjson")) {
    const result = await response.json();
    if (!response.ok) {
      throw Object.assign(new Error("Tra cứu thất bại"), {
        code: result.code,
        userMessage: result.error,
      });
    }
    return result;
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const preview = element("p");
  preview.hidden = true;
  const loading = loadingIndicator("Đang soạn câu trả lời…");
  const result = { answer: "" };
  let buffer = "";
  let complete = false;
  target.replaceChildren(element("strong", "PTIT Chat"), loading, preview);
  preview.style.whiteSpace = "pre-wrap";
  try {
    while (!complete) {
      const { value, done } = await reader.read();
      if (done) break;
      const lines = (buffer + value).split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        const { delta, done: finished, ...metadata } = JSON.parse(line);
        Object.assign(result, metadata);
        if (delta) result.answer += delta;
        if (delta || typeof metadata.answer === "string") {
          if (preview.hidden) {
            preview.hidden = false;
            loading.remove();
            setConversationState("streaming");
          }
          preview.textContent = result.answer;
        }
        complete = finished || complete;
      }
    }
  } finally {
    await reader.cancel();
  }
  if (!result.passages) throw new Error("Missing passages");
  if (!complete) result.generation_error = "Kết nối bị gián đoạn khi nhận câu trả lời.";
  return result;
}

async function ask(value) {
  const question = value.trim();
  if (!question || pending || uploading) return;
  if (latestFile && fileChoice === null) {
    input.value = question;
    attachmentStatus.textContent = "Chọn cách dùng tệp cho câu hỏi này.";
    reuseFile.focus();
    return;
  }
  const attachedFile = fileChoice === "use" ? latestFile : null;
  const uploadId = attachedFile?.upload_id ?? null;
  if (contextUploadId !== uploadId) {
    contextTurns.length = 0;
    contextUploadId = uploadId;
  }
  pending = true;
  showNotice("");
  fileChoice = null;
  attachmentStatus.textContent = "";
  updateComposer();
  input.value = "";
  if (!activeConversation) {
    activeConversation = createConversation();
  }
  if (activeConversation.firstQuestion === null) {
    activeConversation.firstQuestion = question;
    activeConversation.title = question;
  }
  setConversationState("loading");
  welcome.hidden = true;
  messages.hidden = false;
  const userMessage = element("div", question, "message user-message");
  if (attachedFile) userMessage.append(element("span", attachedFile.name, "message-attachment"));
  const reply = element("article", "", "message answer");
  reply.setAttribute("aria-busy", "true");
  reply.append(element("strong", "PTIT Chat"), loadingIndicator(attachedFile
    ? "Đang tìm trong " + attachedFile.name + "…"
    : "Đang tìm trong kho tài liệu…"));
  messages.append(userMessage, reply);
  viewport.scrollTop = viewport.scrollHeight;
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/x-ndjson" },
      body: JSON.stringify({ question, upload_id: uploadId, history: contextTurns }),
    });
    const result = await readAnswer(response, reply);
    renderAnswer(reply, result);
    if (result.generation_error) {
      setConversationState("error");
      showNotice("Câu trả lời gặp sự cố. Xem thông báo trong cuộc trò chuyện.", "error");
    } else if (!result.passages.length) {
      setConversationState("empty");
      showNotice("Chưa tìm thấy tài liệu phù hợp. Bạn thử bổ sung thông tin cho câu hỏi nhé.", "info");
    } else {
      setConversationState("done");
      showNotice("Đã trả lời câu hỏi của bạn.");
    }
    const answer = result.generation_error ? "" : result.answer ?? "";
    contextTurns.push({
      question: result.resolved_question ?? question,
      answer: Array.from(answer).slice(0, 700).join(""),
      person: result.context_person,
    });
    if (contextTurns.length > 3) contextTurns.shift();
  } catch (error) {
    if (error.code === "upload_unavailable") {
      latestFile = null;
      if (!input.value) input.value = question;
      input.focus();
    }
    reply.textContent = error.userMessage
      || "Không thể tra cứu lúc này. Kiểm tra máy chủ Python rồi gửi lại câu hỏi.";
    reply.classList.add("reply-error");
    reply.setAttribute("role", "alert");
    setConversationState("error");
    showNotice("Không thể nhận câu trả lời. Bạn vui lòng thử lại.", "error");
  } finally {
    reply.setAttribute("aria-busy", "false");
    pending = false;
    updateComposer();
    reply.scrollIntoView({ block: "start" });
  }
}

function newChat() {
  if (pending || uploading) return;
  saveConversation();
  activeConversation = createConversation();
  resetChatView();
  renderConversations();
  updateComposer();
  showNotice("Đã tạo cuộc trò chuyện mới.");
  input.focus();
}

function resetChatView() {
  messages.replaceChildren();
  messages.hidden = true;
  welcome.hidden = false;
  input.value = "";
  latestFile = null;
  fileChoice = null;
  contextTurns.length = 0;
  contextUploadId = null;
  attachmentStatus.textContent = "";
  viewport.scrollTop = 0;
  input.focus();
}

form.addEventListener("submit", event => {
  event.preventDefault();
  ask(input.value);
});
upload.addEventListener("click", () => fileInput.click());
replaceFile.addEventListener("click", () => fileInput.click());
reuseFile.addEventListener("click", () => chooseFile("use"));
skipFile.addEventListener("click", () => chooseFile("skip"));
fileInput.addEventListener("change", () => {
  const [file] = fileInput.files;
  fileInput.value = "";
  uploadFile(file);
});
document.addEventListener("click", event => {
  const button = event.target.closest("button[data-question]");
  if (button) ask(button.dataset.question);
});
document.querySelector("#new-chat").addEventListener("click", newChat);
document.querySelector("#mobile-new").addEventListener("click", newChat);

fetch("/api/status")
  .then(response => {
    if (!response.ok) throw new Error("Status unavailable");
    return response.json();
  })
  .then(({ documents, model }) => {
    status.textContent = documents ? documents + " tài liệu sẵn sàng" : "Kho tài liệu đang trống";
    if (model) status.title = "Model đã cấu hình: " + model;
    status.classList.toggle("ready", documents > 0);
  })
  .catch(() => { status.textContent = "Mất kết nối máy chủ"; });
