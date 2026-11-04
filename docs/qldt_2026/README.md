# Kho QLĐT 2026

Đợt thu thập ngày 28/10/2026: 5 bài công khai có ngày đăng trong khoảng
01/01/2026–28/10/2026, trích thêm 2 PDF (19 trang). Kho chatbot được bổ sung
5 file `data/qldt_2026_*.md`; 5 tài liệu trước đó được giữ nguyên.

## Phân nhóm

| Nhóm hiện có | Bài mới |
|---|---:|
| Câu lạc bộ (CLB) | 0 |
| Quy chế chung | 5 |
| Ký túc xá | 0 |
| Thư viện | 0 |
| Thực tập / Việc làm | 0 |

Nhóm Quy chế chung bao gồm đăng ký học và hướng dẫn sử dụng QLĐT.
Đã kiểm tra tiêu đề của cả 5 bài. Không tự tạo bài hoặc chuyển nguồn để lấp
các nhóm không có bài phù hợp. Xem `report.json` để biết URL, ngày đăng,
nhóm, PDF và lỗi từng tài liệu. Tệp JSON theo ID là phản hồi chi tiết gốc;
PDF được giữ để kiểm tra lại văn bản trích xuất. PDF hướng dẫn có ảnh chụp
màn hình: chữ nằm trong ảnh chưa được OCR, chỉ trích lớp văn bản có sẵn.

## Phạm vi

- Nguồn: https://qldt.ptit.edu.vn, API bài đăng trang chủ công khai.
- Danh sách trả về 7 bài; loại 2 bài đăng năm 2025, kể cả tiêu đề nhắc 2026.
- API thông báo theo tài khoản trả 401; không thu thập phần đó, không dùng
  thông tin đăng nhập hoặc dữ liệu học tập cá nhân.
- Đây là toàn bộ bài phù hợp trong danh sách công khai trả về ở lần chạy,
  không phải cam kết toàn bộ thông báo QLĐT trong năm 2026.
- Ngày đăng không phải ngày hiệu lực. Ngày chỉnh sửa lưu riêng.
- Link ngoài QLĐT được giữ tham khảo, không được thu thập tiếp.
- Chạy lại ghi vào cùng tên theo ID, không sinh thêm bản trùng. Không có
  lịch chạy tự động; không tự xóa dữ liệu nếu nguồn gỡ bài.

## Thu thập lại

Từ thư mục gốc dự án:

```powershell
.\.venv\Scripts\python.exe -m pip install -r docs/requirements-scrape.txt
.\.venv\Scripts\python.exe docs/collect_qldt.py --year 2026 --until 2026-10-28
```

Đổi `--until` khi muốn cập nhật đến ngày khác; bộ lọc dựa trên ngày đăng.
Backend đọc `data/*.md` mỗi lần truy vấn, không cần tạo lại chỉ mục.
