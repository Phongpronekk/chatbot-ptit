import { checkAdminSession } from "./admin-session.js";

const accountStatus = document.querySelector("#account-status");
const accountList = document.querySelector("#account-list");
const accountTableBody = document.querySelector("#account-table-body");
const editor = document.querySelector("#account-editor");
const editForm = document.querySelector("#account-edit-form");
const usernameInput = document.querySelector("#account-username");
const passwordInput = document.querySelector("#account-password");
const editError = document.querySelector("#account-edit-error");
const dateFormat = new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" });
let editingUser;
let saving = false;

function actionButton(text, className, action) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `admin-btn ${className}`;
  button.textContent = text;
  button.addEventListener("click", action);
  return button;
}

async function changeAccount(user, method, changes) {
  const response = await fetch(`/api/admin/users/${user.id}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: changes === undefined ? undefined : JSON.stringify(changes),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Không thể cập nhật tài khoản.");
}

async function changeStatus(user) {
  if (saving) return;
  if (user.is_active && !confirm(`Ngừng hoạt động tài khoản "${user.username}"? Các phiên đăng nhập sẽ bị thu hồi.`)) return;
  await performAction(async () => {
    await changeAccount(user, "PATCH", { is_active: !user.is_active });
  }, user.is_active ? "Đã ngừng hoạt động tài khoản." : "Đã kích hoạt lại tài khoản.");
}

async function removeAccount(user) {
  if (saving) return;
  if (!confirm(`Xóa vĩnh viễn tài khoản "${user.username}" cùng lịch sử trò chuyện? Thao tác này không thể hoàn tác.`)) return;
  await performAction(() => changeAccount(user, "DELETE"), "Đã xóa tài khoản.");
}

async function performAction(action, message) {
  saving = true;
  for (const button of accountTableBody.querySelectorAll("button")) button.disabled = true;
  try {
    await action();
    await loadAccounts();
    accountStatus.textContent = message;
  } catch (error) {
    accountStatus.textContent = error.message || "Không thể kết nối máy chủ.";
  } finally {
    saving = false;
    for (const button of accountTableBody.querySelectorAll("button")) button.disabled = false;
  }
}

function openEditor(user) {
  if (saving) return;
  editingUser = user;
  usernameInput.value = user.username;
  passwordInput.value = "";
  editError.textContent = "";
  editor.showModal();
}

editForm.addEventListener("submit", async event => {
  event.preventDefault();
  if (saving) return;
  const changes = { username: usernameInput.value.trim() };
  if (passwordInput.value) changes.password = passwordInput.value;
  saving = true;
  const submitButton = editForm.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  editError.textContent = "";
  try {
    await changeAccount(editingUser, "PATCH", changes);
    passwordInput.value = "";
    editor.close();
    await loadAccounts();
    accountStatus.textContent = "Đã cập nhật tài khoản. Người dùng cần đăng nhập lại.";
  } catch (error) {
    editError.textContent = error.message || "Không thể kết nối máy chủ.";
  } finally {
    saving = false;
    submitButton.disabled = false;
  }
});

document.querySelector("#cancel-account-edit").addEventListener("click", () => {
  if (!saving) editor.close();
});
editor.addEventListener("cancel", event => {
  if (saving) event.preventDefault();
});
editor.addEventListener("close", () => { passwordInput.value = ""; });

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value.replace(" ", "T") + "Z");
  return Number.isNaN(date.getTime()) ? value : dateFormat.format(date);
}

async function loadAccounts() {
  try {
    const response = await fetch("/api/admin/users");
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);

    accountTableBody.replaceChildren();
    for (const user of data.users) {
      const row = accountTableBody.insertRow();
      row.insertCell().textContent = user.username;
      row.insertCell().textContent = user.role === "admin" ? "Quản trị viên" : "Người dùng";
      row.insertCell().textContent = user.is_active ? "Đang hoạt động" : "Ngừng hoạt động";
      row.insertCell().textContent = formatDate(user.created_at);
      const actions = row.insertCell();
      if (user.role !== "admin") {
        const buttons = document.createElement("div");
        buttons.className = "account-actions";
        buttons.append(
          actionButton("Sửa", "secondary", () => openEditor(user)),
          actionButton(user.is_active ? "Ngừng hoạt động" : "Kích hoạt lại", "secondary", () => changeStatus(user)),
          actionButton("Xóa", "danger-sm", () => removeAccount(user)),
        );
        actions.append(buttons);
      }
    }
    accountList.hidden = data.users.length === 0;
    accountStatus.textContent = data.users.length ? "" : "Chưa có tài khoản.";
  } catch (error) {
    accountStatus.textContent = error.message || "Không thể tải danh sách tài khoản.";
    throw error;
  }
}

if (await checkAdminSession()) {
  await loadAccounts().catch(() => {});
} else {
  accountStatus.textContent = "Không thể tải danh sách tài khoản.";
}
