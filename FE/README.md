# PTIT Chat frontend

Vue 3, TypeScript và Pinia. Hội thoại, tin nhắn, thời gian, nguồn tham khảo đều
lấy từ backend; không có lịch sử, câu trả lời hay giờ mẫu trong frontend.

```powershell
cd D:\chatbot-ptit\FE
npm ci
npm run dev
```

Chạy backend ở terminal khác theo `BE/README.md`. Mặc định Vite proxy `/api`
tới `http://127.0.0.1:8000`. Đổi biến `API_PROXY_TARGET` nếu dùng cổng backend
khác và khởi động lại Vite. Trong production, reverse proxy `/api` tới backend
hoặc đặt `VITE_API_BASE_URL` trước khi build; không đưa API key LLM vào frontend.
Nếu dùng origin khác, backend phải cho phép origin FE cụ thể qua CORS_ORIGINS
và cấu hình cookie phù hợp. Cấu hình mặc định dùng chung origin qua proxy.

```text
src/features/chat/
├── ChatView.vue                # Sidebar, trạng thái tải/lỗi/rỗng, tin nhắn
├── chat.types.ts               # Kiểu dữ liệu API
├── chat.service.ts             # HTTP, cookie, timeout và lỗi
├── chat.store.ts               # Điều phối API, trạng thái và nhóm lịch sử
└── components/
    ├── MessageBubble.vue       # Tin nhắn và các nguồn mở rộng
    └── ChatInput.vue           # Enter gửi, Shift+Enter xuống dòng
```

Gửi thất bại giữ nội dung nhập; gửi lại dùng cùng request_id để tránh tin trùng.
Lịch sử lưu tại backend, tải lại trang vẫn lấy được dữ liệu với cùng cookie.
Nút × xóa cuộc trò chuyện. Chưa có đăng nhập, lịch sử hiện tách theo phiên trình
duyệt. Chế độ không có LLM hiển thị trích xuất từ tài liệu backend, có nhãn rõ ràng.

Kiểm tra TypeScript và build:

```powershell
npm run build
```
