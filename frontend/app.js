"use strict";

const form = document.querySelector("#chat-form");
const input = document.querySelector("#question");
const send = document.querySelector("#send");
const status = document.querySelector("#status");
const viewport = document.querySelector("#viewport");
const welcome = document.querySelector("#welcome");
const messages = document.querySelector("#messages");
const history = document.querySelector("#history");
const recent = [];
let pending = false;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
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

function renderAnswer(target, { passages, answer, model, generation_error: generationError }) {
  const heading = element("strong", "PTIT Chat");
  target.replaceChildren(heading);
  if (!passages.length) {
    target.append(element("p", "Chưa tìm thấy đoạn phù hợp. Hãy thử tên học phần, mã môn hoặc thêm học kỳ và năm học."));
    return;
  }
  if (answer) {
    renderExcerpt(target, answer);
    target.append(element("p", "Tài liệu đã dùng · " + model));
  } else {
    target.append(element("p", "Mình tìm được các đoạn sau trong kho tài liệu."));
  }
  if (generationError) target.append(element("p", generationError));
  passages.forEach(({ title, section, text, url }, index) => {
    const details = element("details", "", "source-card");
    details.open = !answer && index === 0;
    details.append(element("summary", "[" + (index + 1) + "] " + section));
    renderExcerpt(details, text);
    if (/^https:\/\//.test(url)) details.append(sourceLink(title + " ↗", url));
    target.append(details);
  });
}

function addHistory(question) {
  const previous = recent.indexOf(question);
  if (previous >= 0) recent.splice(previous, 1);
  recent.unshift(question);
  if (recent.length > 8) recent.pop();
  document.querySelector("#empty-history").hidden = true;
  history.replaceChildren(...recent.map(item => {
    const entry = element("li");
    const button = element("button", item, "history-button");
    button.type = "button";
    button.dataset.question = item;
    button.title = item;
    entry.append(button);
    return entry;
  }));
}

async function readAnswer(response, target) {
  if (!response.headers.get("Content-Type")?.startsWith("application/x-ndjson")) {
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Tra cứu thất bại.");
    return result;
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const preview = element("p");
  const result = { answer: "" };
  let buffer = "";
  let complete = false;
  target.replaceChildren(element("strong", "PTIT Chat"), preview);
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
  if (!question || pending) return;
  pending = true;
  send.disabled = true;
  input.value = "";
  addHistory(question);
  welcome.hidden = true;
  messages.hidden = false;
  const reply = element("article", "Đang tìm trong kho tài liệu…", "message answer");
  messages.append(element("div", question, "message user-message"), reply);
  viewport.scrollTop = viewport.scrollHeight;
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/x-ndjson" },
      body: JSON.stringify({ question }),
    });
    renderAnswer(reply, await readAnswer(response, reply));
  } catch (error) {
    reply.textContent = "Không thể tra cứu lúc này. Kiểm tra máy chủ Python rồi gửi lại câu hỏi.";
  } finally {
    send.disabled = false;
    pending = false;
    reply.scrollIntoView({ block: "start" });
  }
}

function newChat() {
  if (pending) return;
  messages.replaceChildren();
  messages.hidden = true;
  welcome.hidden = false;
  input.value = "";
  input.focus();
}

form.addEventListener("submit", event => {
  event.preventDefault();
  ask(input.value);
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
