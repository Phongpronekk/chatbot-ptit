const userInfo = document.querySelector("#admin-user-info");
const logoutBtn = document.querySelector("#admin-logout-btn");

export async function checkAdminSession() {
  try {
    const response = await fetch("/api/auth/me");
    const { user } = await response.json();
    if (response.status === 401 || (response.ok && user?.role !== "admin")) {
      window.location.replace("/");
      return false;
    }
    if (response.ok) {
      userInfo.textContent = `Quản trị viên · ${user.username}`;
      return true;
    }
  } catch {
    // Keep the current page available when the session check cannot reach the server.
  }
  userInfo.textContent = "Không thể xác thực phiên đăng nhập.";
  return false;
}

logoutBtn.addEventListener("click", async () => {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } finally {
    window.location.replace("/");
  }
});
