"use strict";

const userInfo = document.querySelector("#admin-user-info");
const logoutBtn = document.querySelector("#admin-logout-btn");
const statDocCount = document.querySelector("#stat-doc-count");
const statMode = document.querySelector("#stat-mode");
const statEmbeddingModel = document.querySelector("#stat-embedding-model");
const statLlm = document.querySelector("#stat-llm");
const adminAlert = document.querySelector("#admin-alert");

const fileInput = document.querySelector("#admin-file-input");
const dropArea = document.querySelector("#drop-area");
const chooseFileBtn = document.querySelector("#choose-file-btn");
const selectedFileName = document.querySelector("#selected-file-name");
const submitUploadBtn = document.querySelector("#submit-upload-btn");
const uploadForm = document.querySelector("#admin-upload-form");

const reindexAllBtn = document.querySelector("#reindex-all-btn");
const reindexStatus = document.querySelector("#reindex-status");

const quickTestInput = document.querySelector("#quick-test-input");
const quickTestBtn = document.querySelector("#quick-test-btn");
const quickTestResults = document.querySelector("#quick-test-results");

const docTableBody = document.querySelector("#doc-table-body");
const docTableCount = document.querySelector("#doc-table-count");
const docSearchFilter = document.querySelector("#doc-search-filter");

let allDocuments = [];
let selectedFile = null;

function showAlert(message, type = "success") {
  adminAlert.textContent = message;
  adminAlert.className = `admin-alert ${type}`;
  adminAlert.hidden = false;
  setTimeout(() => {
    adminAlert.hidden = true;
  }, 7000);
}

function formatBytes(bytes) {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

async function checkAuth() {
  try {
    const res = await fetch("/api/auth/me");
    if (!res.ok) {
      window.location.href = "/";
      return;
    }
    const data = await res.json();
    if (data.user.role !== "admin") {
      alert("Bạn không có quyền quản trị viên. Chuyển về trang chat.");
      window.location.href = "/";
      return;
    }
    userInfo.textContent = `Quản trị viên: ${data.user.username}`;
  } catch (err) {
    window.location.href = "/";
  }
}

async function loadStatus() {
  try {
    const res = await fetch("/api/status");
    if (res.ok) {
      const data = await res.json();
      statDocCount.textContent = data.documents || 0;
      statMode.textContent = data.retrieval === "hybrid" ? "Hybrid (Vector + BM25)" : "Chỉ từ khóa (Keyword)";
      statEmbeddingModel.textContent = data.embedding_model || "sentence-transformers";
      statLlm.textContent = data.model || "Gemini";
    }
  } catch (err) {
    console.error("Lỗi khi tải trạng thái hệ thống:", err);
  }
}

async function loadDocuments() {
  try {
    const res = await fetch("/api/admin/documents");
    if (res.ok) {
      const data = await res.json();
      allDocuments = data.documents || [];
      renderDocuments(allDocuments);
    } else {
      const err = await res.json();
      showAlert(err.error || "Không thể tải danh sách tài liệu", "error");
    }
  } catch (err) {
    showAlert("Lỗi kết nối máy chủ khi nạp tài liệu", "error");
  }
}

function renderDocuments(docs) {
  docTableCount.textContent = docs.length;
  if (!docs.length) {
    docTableBody.innerHTML = `<tr><td colspan="6" class="text-center">Chưa có tài liệu nào trong kho.</td></tr>`;
    return;
  }

  docTableBody.innerHTML = "";
  docs.forEach((doc) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${escapeHtml(doc.title)}</strong></td>
      <td><code>${escapeHtml(doc.filename)}</code></td>
      <td><span class="badge">${doc.passages_count} chunks</span></td>
      <td>${formatBytes(doc.size)}</td>
      <td>${doc.modified_at}</td>
      <td class="text-right">
        <button class="admin-btn danger-sm delete-btn" data-file="${escapeHtml(doc.filename)}">Xóa</button>
      </td>
    `;
    docTableBody.appendChild(tr);
  });

  // Attach delete handlers
  docTableBody.querySelectorAll(".delete-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const filename = btn.dataset.file;
      if (!confirm(`Bạn có chắc chắn muốn xóa tài liệu "${filename}"? Hệ thống sẽ xóa các vector liên quan khỏi Chroma.`)) {
        return;
      }
      try {
        const res = await fetch(`/api/admin/documents/${encodeURIComponent(filename)}`, {
          method: "DELETE",
        });
        const result = await res.json();
        if (res.ok) {
          showAlert(`Đã xóa "${filename}" và cập nhật lại chỉ mục thành công.`);
          await loadDocuments();
          await loadStatus();
        } else {
          showAlert(result.error || "Lỗi khi xóa tài liệu", "error");
        }
      } catch (err) {
        showAlert("Lỗi kết nối khi xóa tài liệu", "error");
      }
    });
  });
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// File drop and selection
chooseFileBtn.addEventListener("click", () => fileInput.click());
dropArea.addEventListener("click", (e) => {
  if (e.target !== chooseFileBtn) fileInput.click();
});

fileInput.addEventListener("change", (e) => {
  if (e.target.files.length > 0) {
    setFile(e.target.files[0]);
  }
});

["dragenter", "dragover"].forEach((eventName) => {
  dropArea.addEventListener(eventName, (e) => {
    e.preventDefault();
    dropArea.classList.add("dragover");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  dropArea.addEventListener(eventName, (e) => {
    e.preventDefault();
    dropArea.classList.remove("dragover");
  });
});

dropArea.addEventListener("drop", (e) => {
  if (e.dataTransfer.files.length > 0) {
    setFile(e.dataTransfer.files[0]);
  }
});

function setFile(file) {
  selectedFile = file;
  selectedFileName.textContent = `Tệp đã chọn: ${file.name} (${formatBytes(file.size)})`;
  submitUploadBtn.disabled = false;
}

// Upload document
uploadForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!selectedFile) return;

  submitUploadBtn.disabled = true;
  submitUploadBtn.textContent = "Đang xử lý & nhúng Vector...";

  try {
    const res = await fetch("/api/admin/documents", {
      method: "POST",
      headers: {
        "Content-Type": "application/octet-stream",
        "X-File-Name": encodeURIComponent(selectedFile.name),
      },
      body: selectedFile,
    });

    const result = await res.json();
    if (res.ok) {
      showAlert(`Tải lên thành công! Đã tách thành ${result.passages_count} đoạn và nhúng vector vào ChromaDB.`);
      selectedFile = null;
      selectedFileName.textContent = "";
      fileInput.value = "";
      await loadDocuments();
      await loadStatus();
    } else {
      showAlert(result.error || "Không thể tải lên tài liệu", "error");
    }
  } catch (err) {
    showAlert("Lỗi kết nối khi tải lên tài liệu", "error");
  } finally {
    submitUploadBtn.disabled = !selectedFile;
    submitUploadBtn.textContent = "Tải lên và Lập chỉ mục Vector";
  }
});

// Reindex all
reindexAllBtn.addEventListener("click", async () => {
  if (!confirm("Hành động này sẽ lập lại toàn bộ vector embedding cho tất cả file trong knowledge_base. Bạn có muốn tiếp tục?")) {
    return;
  }
  reindexAllBtn.disabled = true;
  reindexStatus.textContent = "Đang tính toán lại vector cho toàn bộ tri thức...";
  try {
    const res = await fetch("/api/admin/reindex", { method: "POST" });
    const result = await res.json();
    if (res.ok) {
      reindexStatus.textContent = `Hoàn tất! Đã lập chỉ mục ${result.total_chunks} đoạn cho ${result.total_documents} tài liệu.`;
      showAlert(`Đã đồng bộ lại toàn bộ ${result.total_chunks} vector chunks.`);
      await loadDocuments();
      await loadStatus();
    } else {
      reindexStatus.textContent = result.error || "Lỗi khi lập lại chỉ mục.";
    }
  } catch (err) {
    reindexStatus.textContent = "Lỗi kết nối khi lập lại chỉ mục.";
  } finally {
    reindexAllBtn.disabled = false;
  }
});

// Search filter
docSearchFilter.addEventListener("input", (e) => {
  const query = e.target.value.toLowerCase().trim();
  if (!query) {
    renderDocuments(allDocuments);
    return;
  }
  const filtered = allDocuments.filter(
    (d) => d.title.toLowerCase().includes(query) || d.filename.toLowerCase().includes(query)
  );
  renderDocuments(filtered);
});

// Quick Test Search
quickTestBtn.addEventListener("click", async () => {
  const q = quickTestInput.value.trim();
  if (!q) return;

  quickTestBtn.disabled = true;
  quickTestBtn.textContent = "Đang tìm...";
  quickTestResults.hidden = false;
  quickTestResults.innerHTML = "Đang truy vấn vector và trích xuất ngữ cảnh...";

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: jsonBody({ question: q }),
    });
    const data = await res.json();
    if (res.ok) {
      if (!data.passages || data.passages.length === 0) {
        quickTestResults.innerHTML = `<em>Không tìm thấy đoạn văn nào phù hợp. Câu trả lời:</em><br><p>${escapeHtml(data.answer || "Không có câu trả lời.")}</p>`;
      } else {
        let html = `<strong>Tìm thấy ${data.passages.length} đoạn liên quan:</strong>`;
        data.passages.forEach((p, idx) => {
          html += `
            <div class="test-passage-item">
              <div class="test-passage-title">${idx + 1}. ${escapeHtml(p.title)} · ${escapeHtml(p.section)}</div>
              <div>${escapeHtml(p.text.slice(0, 160))}...</div>
            </div>
          `;
        });
        if (data.answer) {
          html += `<div style="margin-top: 10px; padding-top: 8px; border-top: 1px dashed #d1d5db;"><strong>Câu trả lời AI:</strong><br>${escapeHtml(data.answer)}</div>`;
        }
        quickTestResults.innerHTML = html;
      }
    } else {
      quickTestResults.innerHTML = `<span style="color: #dc2626;">Lỗi: ${escapeHtml(data.error || "Lỗi truy vấn")}</span>`;
    }
  } catch (err) {
    quickTestResults.innerHTML = `<span style="color: #dc2626;">Lỗi kết nối khi kiểm tra</span>`;
  } finally {
    quickTestBtn.disabled = false;
    quickTestBtn.textContent = "Thử tìm";
  }
});

function jsonBody(obj) {
  return JSON.stringify(obj);
}

// Logout
logoutBtn.addEventListener("click", async () => {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } finally {
    window.location.href = "/";
  }
});

// Initial boot
checkAuth();
loadStatus();
loadDocuments();
