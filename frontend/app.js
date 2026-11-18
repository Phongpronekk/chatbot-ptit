"use strict";

const form = document.querySelector("#chat-form");
const input = document.querySelector("#question");
const send = document.querySelector("#send");
const mic = document.querySelector("#mic");
const fileInput = document.querySelector("#upload-input");
const upload = document.querySelector("#upload");
const attachmentOptions = document.querySelector("#attachment-options");
const attachmentFile = document.querySelector("#attachment-file");
const attachmentStatus = document.querySelector("#attachment-status");
const replaceFile = document.querySelector("#replace-file");
const status = document.querySelector("#status");
const viewport = document.querySelector("#viewport");
const welcome = document.querySelector("#welcome");
const messages = document.querySelector("#messages");
const conversationList = document.querySelector("#conversations");
const chatNotice = document.querySelector("#chat-notice");
const defaultPlaceholder = input.getAttribute("placeholder") || "Nhập câu hỏi của bạn…";

// User and Auth Elements  (topbar – góc trên bên phải)
const userLoggedIn = document.querySelector("#user-logged-in");
const userLoggedOut = document.querySelector("#user-logged-out");
const userNameDisplay = document.querySelector("#user-name-display");
const userAvatar = document.querySelector("#user-avatar");
const logoutBtn = document.querySelector("#logout-btn");
const openAuthModal = document.querySelector("#open-auth-modal");

const authModal = document.querySelector("#auth-modal");
const closeAuthModal = document.querySelector("#close-auth-modal");
const tabLogin = document.querySelector("#tab-login");
const tabRegister = document.querySelector("#tab-register");
const authAlert = document.querySelector("#auth-alert");
const authForm = document.querySelector("#auth-form");
const authUsername = document.querySelector("#auth-username");
const authPassword = document.querySelector("#auth-password");
const authSubmitBtn = document.querySelector("#auth-submit-btn");

let currentUser = null;
let authMode = "login";

const conversations = [];
let activeConversation = null;
let noticeTimer;
const contextTurns = [];
const MAX_HISTORY_TURNS = 6;
const MAX_HISTORY_ANSWER_CHARS = 10000;
const MAX_HISTORY_CHARS = 24000;
let contextUploadId = null;
let pending = false;
let uploading = false;
let latestFile = null;
let uploadedFiles = [];
let fileChoice = null;
let mediaRecorder = null;
let audioChunks = [];
let mediaStream = null;
let isRecording = false;
let isTranscribing = false;
let transcriptPrefix = "";

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

function createConversation(id = null, title = "Cuộc trò chuyện mới") {
  const convId = id || "conv-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8);
  const conversation = {
    id: convId,
    title: title, firstQuestion: null, state: "new",
    nodes: [], turns: [], contextUploadId: null, latestFile: null,
    fileChoice: null, draft: "", attachmentStatus: "", scrollTop: 0,
    hasDbMessages: false,
  };
  conversations.unshift(conversation);
  if (currentUser) {
    fetch("/api/conversations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: convId, title: title }),
    }).catch(() => {});
  }
  return conversation;
}

function renderMessagesFromData(messagesList) {
  const nodes = [];
  messagesList.forEach((msg) => {
    if (msg.sender === "user") {
      const u = element("div", msg.text, "message user-message");
      nodes.push(u);
    } else {
      const r = element("article", "", "message answer");
      renderAnswer(r, {
        passages: msg.passages || [],
        answer: msg.text,
        model: msg.model,
      });
      nodes.push(r);
    }
  });
  return nodes;
}

async function fetchUserConversations() {
  if (!currentUser) return;
  try {
    const res = await fetch("/api/conversations");
    if (!res.ok) return;
    const data = await res.json();
    const dbConvs = data.conversations || [];
    conversations.splice(0, conversations.length);
    dbConvs.forEach((c) => {
      conversations.push({
        id: c.id,
        title: c.title,
        firstQuestion: c.title,
        state: "done",
        nodes: [],
        turns: [],
        contextUploadId: null,
        latestFile: null,
        fileChoice: null,
        draft: "",
        attachmentStatus: "",
        scrollTop: 0,
        hasDbMessages: true,
      });
    });
    if (conversations.length > 0) {
      await openConversation(conversations[0]);
    } else {
      resetChatView();
      renderConversations();
    }
  } catch (e) {
    console.error("Lỗi nạp cuộc trò chuyện:", e);
  }
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

function getSupportedAudioMimeType() {
  if (typeof MediaRecorder === "undefined") return "";
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
    "audio/wav",
  ];
  for (const candidate of candidates) {
    if (MediaRecorder.isTypeSupported(candidate)) return candidate;
  }
  return "";
}

function cleanupRecordingUI() {
  isRecording = false;
  mic.classList.remove("is-recording");
  if (!isTranscribing) {
    mic.classList.remove("is-transcribing");
    mic.setAttribute("aria-label", "Ghi âm câu hỏi");
    mic.title = "Ghi âm giọng nói (không cần nhập text)";
    input.placeholder = defaultPlaceholder;
  }
  updateComposer();
}

function cancelRecording() {
  if (mediaStream) {
    mediaStream.getTracks().forEach(track => track.stop());
    mediaStream = null;
  }
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.onstop = null;
    try { mediaRecorder.stop(); } catch {}
  }
  mediaRecorder = null;
  audioChunks = [];
  cleanupRecordingUI();
}

async function sendAudioForTranscription(audioBlob) {
  isTranscribing = true;
  cleanupRecordingUI();
  mic.classList.add("is-transcribing");
  mic.setAttribute("aria-label", "Đang chuyển giọng nói thành văn bản…");
  mic.title = "Đang chuyển giọng nói thành văn bản…";
  input.placeholder = "Đang chuyển giọng nói thành văn bản…";
  showNotice("Đang xử lý và chuyển giọng nói thành văn bản…", "info");

  try {
    const response = await fetch("/api/transcribe", {
      method: "POST",
      headers: {
        "Content-Type": audioBlob.type || "audio/webm",
      },
      body: audioBlob,
    });
    const result = await response.json();
    if (!response.ok) {
      showNotice(result.error || "Không thể nhận diện giọng nói lúc này.", "error");
      return;
    }
    const transcribed = (result.text || "").trim();
    if (transcribed) {
      input.value = (transcriptPrefix + transcribed).trimStart();
      input.scrollLeft = input.scrollWidth;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      showNotice("Đã nhận diện giọng nói xong.");
      input.focus();
    } else {
      showNotice("Không nghe rõ câu hỏi. Bạn hãy thử ghi âm lại nhé.", "info");
    }
  } catch (error) {
    console.error("Lỗi gửi dữ liệu âm thanh:", error);
    showNotice("Mất kết nối máy chủ khi chuyển giọng nói thành văn bản.", "error");
  } finally {
    isTranscribing = false;
    mic.classList.remove("is-transcribing");
    input.placeholder = defaultPlaceholder;
    updateComposer();
  }
}

function stopRecording() {
  if (!isRecording && !mediaRecorder) return;
  isRecording = false;
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    try {
      mediaRecorder.stop();
    } catch {
      cleanupRecordingUI();
    }
  } else {
    cleanupRecordingUI();
  }
}

async function startRecording() {
  if (pending || uploading || isTranscribing) return;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || typeof MediaRecorder === "undefined") {
    showNotice("Trình duyệt không hỗ trợ MediaRecorder hoặc trang chưa mở qua localhost/HTTPS.", "error");
    return;
  }

  transcriptPrefix = input.value ? (input.value.trim() + " ") : "";

  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];

    const mimeType = getSupportedAudioMimeType();
    const options = mimeType ? { mimeType } : {};
    mediaRecorder = new MediaRecorder(mediaStream, options);

    mediaRecorder.ondataavailable = event => {
      if (event.data && event.data.size > 0) {
        audioChunks.push(event.data);
      }
    };

    mediaRecorder.onstop = async () => {
      if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
        mediaStream = null;
      }

      if (audioChunks.length === 0) {
        cleanupRecordingUI();
        return;
      }

      const recordedType = mediaRecorder?.mimeType || mimeType || "audio/webm";
      const audioBlob = new Blob(audioChunks, { type: recordedType });
      audioChunks = [];

      if (audioBlob.size < 600) {
        cleanupRecordingUI();
        showNotice("Thời gian nói quá ngắn. Vui lòng thử nói lại câu hỏi.", "info");
        return;
      }

      await sendAudioForTranscription(audioBlob);
    };

    mediaRecorder.start(250);
    isRecording = true;
    mic.classList.add("is-recording");
    mic.setAttribute("aria-label", "Dừng ghi âm và nhận diện");
    mic.title = "Dừng ghi âm và nhận diện (nhấn vào đây khi nói xong)";
    input.placeholder = "Đang ghi âm… Nhấn lại vào mic khi bạn nói xong.";
    showNotice("Đang ghi âm… Hãy nói câu hỏi rồi nhấn lại vào mic.", "info");
  } catch (err) {
    console.error("Lỗi microphone:", err);
    if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
      showNotice("Vui lòng cho phép quyền truy cập micro trong trình duyệt để ghi âm.", "error");
    } else if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
      showNotice("Không tìm thấy micro trên thiết bị của bạn.", "error");
    } else {
      showNotice("Không thể bắt đầu ghi âm: " + (err.message || err.name), "error");
    }
    cancelRecording();
  }
}

function toggleRecording() {
  if (isTranscribing) return;
  if (isRecording) {
    stopRecording();
  } else {
    startRecording();
  }
}

function updateComposer() {
  const busy = pending || uploading || isTranscribing;
  if (busy && isRecording) cancelRecording();
  for (const button of [send, mic, upload, attachmentFile, replaceFile]) button.disabled = busy;
  for (const button of document.querySelectorAll(".conversation-button, .conversation-delete, #new-chat, #mobile-new")) button.disabled = busy;
  send.classList.toggle("is-loading", pending);
  send.setAttribute("aria-label", pending ? "Đang nhận câu trả lời" : "Gửi câu hỏi");
  if (latestFile && !uploadedFiles.some(file => file.upload_id === latestFile.upload_id)) {
    uploadedFiles.push(latestFile);
  }
  attachmentOptions.hidden = uploadedFiles.length === 0;
  const options = uploadedFiles.map(file => {
    const option = element("option", file.name);
    option.value = file.upload_id;
    return option;
  });
  const skipOption = element("option", "Không dùng tệp");
  skipOption.value = "skip";
  attachmentFile.replaceChildren(...options, skipOption);
  attachmentFile.value = fileChoice === "skip" ? "skip" : latestFile?.upload_id ?? "skip";
  attachmentFile.title = fileChoice === "skip" ? "Không dùng tệp" : latestFile?.name ?? "";
}

function chooseFile(value) {
  if (pending || uploading || isTranscribing) return;
  if (value === "skip") {
    fileChoice = "skip";
  } else {
    const file = uploadedFiles.find(file => file.upload_id === value);
    if (!file) return;
    latestFile = file;
    fileChoice = "use";
  }
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
    uploadedFiles.push(result);
    if (uploadedFiles.length === 1) {
      latestFile = result;
      fileChoice = "use";
    }
    attachmentStatus.textContent = "Đã tải tệp. Tệp đang chọn sẽ được dùng cho các câu hỏi tiếp theo.";
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

function renderMathSpan(latex, isBlock = false) {
  const span = document.createElement(isBlock ? "div" : "span");
  span.className = isBlock ? "math-block" : "math-inline";
  if (typeof window.katex !== "undefined") {
    try {
      span.innerHTML = window.katex.renderToString(latex, {
        displayMode: isBlock,
        throwOnError: false,
      });
      return span;
    } catch (e) {
      console.warn("KaTeX render error:", e);
    }
  }
  span.textContent = (isBlock ? "$$" : "$") + latex + (isBlock ? "$$" : "$");
  return span;
}

function citationBadge(num) {
  const badge = element("span", "[" + num + "]", "citation-badge");
  badge.setAttribute("aria-label", "Nguồn " + num);
  return badge;
}

function appendInline(parent, text) {
  const markup = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\$([^\$\n]+?)\$|\\\(([\s\S]+?)\\\)|\*\*([^*]+)\*\*|\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|\[(\d+)\]|\x60([^\x60]+)\x60/g;
  let offset = 0;
  for (const match of text.matchAll(markup)) {
    parent.append(text.slice(offset, match.index));
    const [, disp1, disp2, in1, in2, bold, label, url, cite, code] = match;
    if (disp1 || disp2) {
      parent.append(renderMathSpan(disp1 || disp2, true));
    } else if (in1 || in2) {
      parent.append(renderMathSpan(in1 || in2, false));
    } else if (bold) {
      parent.append(element("strong", bold));
    } else if (url) {
      parent.append(sourceLink(label, url));
    } else if (cite) {
      parent.append(citationBadge(cite));
    } else if (code) {
      parent.append(element("code", code));
    }
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
    if (line.startsWith("$$") && line.endsWith("$$") && line.length > 4) {
      const mathContent = line.slice(2, -2).trim();
      parent.append(renderMathSpan(mathContent, true));
      index++;
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

function renderAnswer(target, { passages, answer, intent, model, document: filename, generation_error: generationError }) {
  const heading = element("strong", "PTIT Chat");
  target.replaceChildren(heading);
  if (intent === "greeting" || intent === "clarification") {
    target.append(element("p", answer));
    return;
  }
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
  if (pending || uploading || isTranscribing) return;
  cancelRecording();
  const index = conversations.indexOf(conversation);
  if (index < 0) return;
  if (currentUser && conversation.id) {
    fetch(`/api/conversations/${conversation.id}`, { method: "DELETE" }).catch(() => {});
  }
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
    uploadedFiles: [...uploadedFiles],
    fileChoice,
    draft: input.value,
    attachmentStatus: attachmentStatus.textContent,
    scrollTop: viewport.scrollTop,
  });
}

async function openConversation(conversation) {
  if (pending || uploading || isTranscribing || conversation === activeConversation) return;
  cancelRecording();
  saveConversation();
  activeConversation = conversation;

  if (currentUser && conversation.id && conversation.nodes.length === 0 && conversation.hasDbMessages) {
    try {
      const res = await fetch(`/api/conversations/${conversation.id}`);
      if (res.ok) {
        const data = await res.json();
        if (data.messages && data.messages.length > 0) {
          conversation.nodes = renderMessagesFromData(data.messages);
        }
      }
    } catch (e) {
      console.error("Lỗi khi tải tin nhắn:", e);
    }
  }

  messages.replaceChildren(...conversation.nodes);
  messages.hidden = conversation.nodes.length === 0;
  welcome.hidden = !messages.hidden;
  contextTurns.splice(0, contextTurns.length, ...conversation.turns);
  contextUploadId = conversation.contextUploadId;
  latestFile = conversation.latestFile;
  uploadedFiles = [...(conversation.uploadedFiles ?? (latestFile ? [latestFile] : []))];
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
  const loading = loadingIndicator("Đang tra cứu dữ liệu…");
  const result = { answer: "" };
  let buffer = "";
  let complete = false;
  let hasShownSources = false;
  target.replaceChildren(element("strong", "PTIT Chat"), loading, preview);
  preview.style.whiteSpace = "pre-wrap";
  try {
    while (!complete) {
      const { value, done } = await reader.read();
      if (done) break;
      const lines = (buffer + value).split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        const { delta, done: finished, ...metadata } = JSON.parse(line);
        Object.assign(result, metadata);
        if (metadata.passages && !hasShownSources) {
          hasShownSources = true;
          const statusSpan = loading.querySelector("span:last-child");
          if (statusSpan) {
            const count = metadata.passages.length;
            statusSpan.textContent = count > 0
              ? `Đã tìm thấy ${count} tài liệu liên quan · Đang tạo câu trả lời…`
              : "Đang phân tích và tạo câu trả lời…";
          }
        }
        if (delta) result.answer += delta;
        if (delta || typeof metadata.answer === "string") {
          if (preview.hidden) {
            preview.hidden = false;
            loading.remove();
            preview.classList.add("streaming-cursor");
            setConversationState("streaming");
          }
          preview.textContent = result.answer;
          viewport.scrollTop = viewport.scrollHeight;
        }
        complete = finished || complete;
      }
    }
  } finally {
    preview.classList.remove("streaming-cursor");
    await reader.cancel();
  }
  if (!result.passages) throw new Error("Missing passages");
  if (!complete) result.generation_error = "Kết nối bị gián đoạn khi nhận câu trả lời.";
  return result;
}

function isGreetingOnly(question) {
  // Keep this in sync with conversation.is_greeting_only; the backend routes the request.
  const text = question.toLowerCase().replaceAll("đ", "d").normalize("NFD")
    .replace(/\p{M}/gu, "").replace(/[^\p{L}\p{N}_\s]/gu, " ")
    .trim().replace(/\s+/g, " ");
  return /^(?:(?:xin )?chao|hello|hi|hey)(?: (?:ban|bot|chatbot|ptit(?: chat)?|ad|admin|anh|chi|thay|co))?(?: (?:a|nhe|nha))?$/.test(text);
}

function rememberTurn(question, result) {
  if (result.generation_error || result.intent === "greeting") return;
  const characters = Array.from(result.answer ?? "");
  contextTurns.push({
    question: result.resolved_question ?? question,
    answer: characters.slice(0, MAX_HISTORY_ANSWER_CHARS).join(""),
    source_ids: result.intent !== "clarification" && Array.isArray(result.source_ids)
      ? [...result.source_ids] : [],
    intent: result.intent ?? "question",
    person: result.context_person,
    ...(characters.length > MAX_HISTORY_ANSWER_CHARS ? { answer_truncated: true } : {}),
  });
  let size = contextTurns.reduce((total, turn) =>
    total + Array.from(turn.question).length + Array.from(turn.answer).length, 0);
  while (contextTurns.length > MAX_HISTORY_TURNS || size > MAX_HISTORY_CHARS) {
    const removed = contextTurns.shift();
    size -= Array.from(removed.question).length + Array.from(removed.answer).length;
  }
}

async function ask(value) {
  cancelRecording();
  const question = value.trim();
  if (!question || pending || uploading) return;
  const greetingOnly = isGreetingOnly(question);
  if (!greetingOnly && latestFile && fileChoice === null) {
    fileChoice = "use";
  }
  const attachedFile = !greetingOnly && fileChoice === "use" ? latestFile : null;
  const uploadId = attachedFile?.upload_id ?? null;
  if (!greetingOnly && contextUploadId !== uploadId) {
    contextTurns.length = 0;
    contextUploadId = uploadId;
  }
  pending = true;
  showNotice("");
  if (!greetingOnly) {
    attachmentStatus.textContent = "";
  }
  updateComposer();
  input.value = "";
  if (!activeConversation) {
    activeConversation = createConversation();
  }
  if (activeConversation.firstQuestion === null) {
    activeConversation.firstQuestion = question;
    activeConversation.title = question;
    if (currentUser && activeConversation.id) {
      fetch(`/api/conversations/${activeConversation.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: question }),
      }).catch(() => {});
    }
  }
  setConversationState("loading");
  welcome.hidden = true;
  messages.hidden = false;
  const userMessage = element("div", question, "message user-message");
  if (attachedFile) userMessage.append(element("span", attachedFile.name, "message-attachment"));
  const reply = element("article", "", "message answer");
  reply.setAttribute("aria-busy", "true");
  reply.append(element("strong", "PTIT Chat"), loadingIndicator(greetingOnly
    ? "Đang phản hồi…"
    : attachedFile
    ? "Đang tìm trong " + attachedFile.name + "…"
    : "Đang tìm trong kho tài liệu…"));
  messages.append(userMessage, reply);
  viewport.scrollTop = viewport.scrollHeight;
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/x-ndjson" },
      body: JSON.stringify({
        question,
        upload_id: uploadId,
        history: contextTurns,
        conversation_id: activeConversation ? activeConversation.id : undefined,
      }),
    });
    const result = await readAnswer(response, reply);
    renderAnswer(reply, result);
    if (result.intent === "greeting") {
      setConversationState("done");
      return;
    }
    if (result.generation_error) {
      setConversationState("error");
      showNotice("Câu trả lời gặp sự cố. Xem thông báo trong cuộc trò chuyện.", "error");
    } else if (result.intent === "clarification") {
      setConversationState("done");
      showNotice("Bạn bổ sung thông tin để mình hiểu đúng câu hỏi nhé.", "info");
    } else if (!result.passages.length) {
      setConversationState("empty");
      showNotice("Chưa tìm thấy tài liệu phù hợp. Bạn thử bổ sung thông tin cho câu hỏi nhé.", "info");
    } else {
      setConversationState("done");
      showNotice("Đã trả lời câu hỏi của bạn.");
    }
    rememberTurn(question, result);
  } catch (error) {
    if (error.code === "upload_unavailable") {
      uploadedFiles = uploadedFiles.filter(file => file.upload_id !== uploadId);
      latestFile = uploadedFiles[0] ?? null;
      fileChoice = latestFile ? "use" : null;
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
    viewport.scrollTop = viewport.scrollHeight;
  }
}

function newChat() {
  if (pending || uploading || isTranscribing) return;
  cancelRecording();
  saveConversation();
  activeConversation = createConversation();
  resetChatView();
  renderConversations();
  updateComposer();
  showNotice("Đã tạo cuộc trò chuyện mới.");
  input.focus();
}

function resetChatView() {
  cancelRecording();
  messages.replaceChildren();
  messages.hidden = true;
  welcome.hidden = false;
  input.value = "";
  latestFile = null;
  uploadedFiles = [];
  fileChoice = null;
  contextTurns.length = 0;
  contextUploadId = null;
  attachmentStatus.textContent = "";
  viewport.scrollTop = 0;
  input.focus();
}

form.addEventListener("submit", event => {
  event.preventDefault();
  if (isTranscribing) return;
  if (isRecording) {
    stopRecording();
    return;
  }
  ask(input.value);
});
mic.addEventListener("click", toggleRecording);
upload.addEventListener("click", () => fileInput.click());
replaceFile.addEventListener("click", () => fileInput.click());
attachmentFile.addEventListener("change", () => chooseFile(attachmentFile.value));
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

// --- User Auth & Modal Functions ---

function updateUserUI(user) {
  currentUser = user;
  if (user) {
    userLoggedIn.hidden = false;
    userLoggedOut.hidden = true;
    userNameDisplay.textContent = user.username;
    userAvatar.textContent = user.username.charAt(0).toUpperCase();
  } else {
    userLoggedIn.hidden = true;
    userLoggedOut.hidden = false;
  }
}

function openModal(mode = "login") {
  setAuthTab(mode);
  authAlert.hidden = true;
  authUsername.value = "";
  authPassword.value = "";
  authModal.hidden = false;
  authUsername.focus();
}

function setAuthTab(mode) {
  authMode = mode;
  tabLogin.classList.toggle("active", mode === "login");
  tabRegister.classList.toggle("active", mode === "register");
  authPassword.autocomplete = mode === "login" ? "current-password" : "new-password";
  authSubmitBtn.textContent = mode === "login" ? "Đăng nhập" : "Đăng ký";
  authAlert.hidden = true;
}

async function handleAuthSubmit(e) {
  e.preventDefault();
  const username = authUsername.value.trim();
  const password = authPassword.value;

  authAlert.hidden = true;
  authSubmitBtn.disabled = true;

  const url = authMode === "login" ? "/api/auth/login" : "/api/auth/register";

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      authAlert.textContent = data.error || "Thao tác thất bại.";
      authAlert.className = "auth-alert error";
      authAlert.hidden = false;
      return;
    }

    if (data.user.role === "admin") {
      window.location.replace("/admin");
      return;
    }
    updateUserUI(data.user);
    authModal.hidden = true;
    showNotice(authMode === "login" ? `Chào mừng trở lại, ${data.user.username}!` : `Đăng ký thành công tài khoản ${data.user.username}!`);
    await fetchUserConversations();
  } catch (err) {
    authAlert.textContent = "Không thể kết nối đến máy chủ.";
    authAlert.className = "auth-alert error";
    authAlert.hidden = false;
  } finally {
    authSubmitBtn.disabled = false;
  }
}

async function handleLogout() {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } finally {
    updateUserUI(null);
    conversations.splice(0, conversations.length);
    activeConversation = null;
    resetChatView();
    renderConversations();
    showNotice("Đã đăng xuất khỏi tài khoản.");
  }
}

async function checkCurrentUser() {
  try {
    const res = await fetch("/api/auth/me");
    if (res.ok) {
      const data = await res.json();
      if (data.user.role === "admin") {
        window.location.replace("/admin");
        return;
      }
      updateUserUI(data.user);
      await fetchUserConversations();
    } else {
      updateUserUI(null);
    }
  } catch (err) {
    updateUserUI(null);
  }
}

openAuthModal?.addEventListener("click", () => openModal("login"));
closeAuthModal?.addEventListener("click", () => { authModal.hidden = true; });
authModal?.addEventListener("click", (e) => { if (e.target === authModal) authModal.hidden = true; });
tabLogin?.addEventListener("click", () => setAuthTab("login"));
tabRegister?.addEventListener("click", () => setAuthTab("register"));
authForm?.addEventListener("submit", handleAuthSubmit);
logoutBtn?.addEventListener("click", handleLogout);

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

// Check login status on page boot
checkCurrentUser();

