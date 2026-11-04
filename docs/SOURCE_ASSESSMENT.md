# Chấm điểm hệ thống theo SOURCE_REQUIREMENTS.md

Lưu ý phiên bản: báo cáo này chấm snapshot trước đợt thu thập 160 bài năm 2026. Số liệu 69 chunk, hash dữ liệu, tình trạng metadata và điểm bên dưới là kết quả tại thời điểm đánh giá, chưa phải đánh giá lại bộ dữ liệu mới. Danh mục cập nhật nằm ở `docs/ptit_2026_five_files/README.md`.

Ngày đánh giá: 29/10/2026 (Asia/Saigon). Repository: `D:\chatbot-ptit`.
Nguồn yêu cầu: `C:\Users\Lenovo\Downloads\SOURCE_REQUIREMENTS.md`, nhất là mục 3, 10, 11 và phụ lục A.

## 1. Kết quả và cách chấm

**Điểm đề xuất: 6,7/10 về mức đáp ứng yêu cầu bắt buộc.** Đây là điểm đánh giá kỹ thuật do người rà soát xây dựng, không phải điểm chính thức của học phần. File nguồn nói rõ chưa có rubric điểm, ngưỡng nghiệm thu hoặc thời hạn nộp. Không lấy các ô đã đánh dấu trong checklist tài liệu làm bằng chứng phần mềm đã hoàn thành.

R001–R012 có trọng số bằng nhau: mỗi mục tối đa 1 điểm. Quy ước: 1 = đáp ứng với bằng chứng; 0,75 = phần chính đã có nhưng kiểm soát/xác minh còn thiếu; 0,5 = đáp ứng một phần; 0,25 = mới có nền tảng; 0 = chưa có. Tổng **8/12 × 10 = 6,67**, làm tròn 6,7. R013–R014 được báo riêng vì nguồn đánh dấu khuyến nghị, không trừ như yêu cầu bắt buộc. Điểm đánh giá trạng thái sau khi bổ sung báo cáo và phép đo trong đợt này; không phải tỷ lệ chính xác chatbot.

| ID | Điểm / 1 | Kết luận và bằng chứng |
| --- | ---: | --- |
| R001 Công nghệ và luồng | 1 | Có README và mã kiểm chứng: Vue/TS/Pinia/Vite ở `FE/package.json`; FastAPI, SQLite, E5/ONNX, Chroma, Gemini/Ollama ở BE. Chi tiết mục 3–4 dưới đây. |
| R002 Câu hỏi tự nhiên | 1 | FE gửi câu hỏi qua `chat.service.ts`; `SendMessage` kiểm tra rỗng/độ dài; endpoint gửi tin nhắn nhận và trả hội thoại. Các ca API kiểm chứng gửi–nhận. |
| R003 Ngữ cảnh hội thoại | 0 | `BE/main.py:send_message` chỉ gọi `knowledge.answer(payload.message)`. Hàm `answer(question)` không nhận lịch sử; chưa có reformulation. Lưu lịch sử không đồng nghĩa hiểu câu hỏi nối tiếp. |
| R004 Embedding và Vector DB | 0,75 | E5-small 384 chiều, prefix đúng hai phía, Chroma cosine và Top-K đã có, thử truy xuất thực đạt tập smoke. Chưa lọc năm học/học kỳ/đối tượng/hiệu lực bằng metadata. |
| R005 Sinh dựa context | 0,75 | Prompt có bằng chứng đánh số, chỉ dẫn dùng nguồn, không làm theo chỉ thị trong tài liệu. Chưa có bộ chấm câu trả lời đầy đủ hoặc kiểm chứng từng khẳng định sau sinh; prompt không bảo đảm chống hallucination. |
| R006 Hiển thị nguồn | 1 | URL lấy từ metadata và trả trong `Source`; `MessageBubble.vue` hiện nội dung và link HTTP(S), dùng `noopener noreferrer`. Chưa xác minh trực tuyến từng trang hoặc kiểm tra mã [n] model sinh; đây là giới hạn bổ sung, không phủ nhận chức năng hiển thị nguồn đã có. |
| R007 Cập nhật pipeline | 1 | Ingest, fingerprint, cache embedding và chuyển manifest đã có. Kiểm thử bổ sung T07 xác minh thêm/sửa/xóa tài liệu trong kho tạm; ingest lặp không nhân bản chỉ mục đang dùng. |
| R008 Thiếu dữ liệu | 0,75 | Không có nguồn thì trả thiếu thông tin và không gọi LLM; có kiểm thử. Kiểm soát chủ yếu qua ngưỡng tương đồng và prompt, chưa có quyết định rõ về thiếu điều kiện/mâu thuẫn/sai kỳ khi điểm vẫn cao. |
| R009 Phiên và lịch sử | 1 | SQLite, cookie UUID HttpOnly/SameSite Lax, điều kiện owner trong CRUD; kiểm thử chặn đọc/ghi/xóa chéo trình duyệt và lưu qua lần chạy lại. Phiên ẩn danh, chưa có đăng nhập tài khoản; nguồn chưa bắt buộc JWT/OAuth. |
| R010 Phản hồi | 0 | Chưa có bảng/schema/API/UI feedback gắn với assistant message. Lưu hội thoại và retry không thay cho phản hồi hữu ích/không hữu ích. |
| R011 Bốn nhóm và metadata | 0,25 | Có nhóm, tiêu đề, nội dung, URL, ngày thu thập; một số ngày đăng/cơ sở nằm trong note. Tuy nhiên 5 nhóm hiện tại khác 4 nhóm yêu cầu; thiếu trường cấu trúc hạn hiệu lực/từ khóa/ngày đăng xuyên suốt chunk/API và chưa có schema kiểm tra ngày. |
| R012 Đánh giá chất lượng/độ trễ | 0,5 | Có unit/integration test, build và phép đo truy xuất thực mới bổ sung. Thiếu tập đánh giá độc lập có nhãn, đáp án tham chiếu, đo end-to-end nhiều mẫu, khảo sát hài lòng và chấm đúng nguồn/đúng điều kiện. |
| **Tổng bắt buộc** | **8 / 12** | **6,7 / 10** |

| Khuyến nghị | Hiện trạng |
| --- | --- |
| R013 Reranking | Chưa triển khai cross-encoder/reranker và chưa có so sánh có/không. Không trừ điểm bắt buộc vì nguồn ghi tùy chọn. |
| R014 Phiên bản tri thức | Có fingerprint nội dung+cấu hình, collection mới và chuyển manifest sau khi hoàn tất; lỗi rebuild giữ bản cũ. Còn thiếu quản lý văn bản thay thế/hiệu lực theo nghiệp vụ, dọn collection cũ và chuyển collection cho tiến trình BE đang chạy. |

## 2. Kiểm chứng đã thực hiện

### Kiểm thử và đo thực

- Bộ kiểm thử BE: **27/27 đạt**, 12,472 giây; chạy `python -m unittest discover -s BE/tests -v`; kết quả cuối được lưu tại `logs/source-audit-tests.log`. Bao gồm ca T07 mới dùng dữ liệu tạm, encoder giả 3 chiều và Chroma thực; không dùng kết quả đó để suy ra chất lượng E5 thực.
- FE: `npm run build` thành công (type-check và Vite build), log `logs/source-audit-fe-build.log`. Đây không phải kiểm thử tương tác trong trình duyệt.
- Truy xuất E5/Chroma thực: **10/10 ca smoke**, gồm 8 câu cần tìm đúng file và nội dung bằng chứng, 2 câu ngoài phạm vi cần trả rỗng. Đủ 5 nhóm dữ liệu hiện tại; chưa thể nói bao phủ 4 nhóm yêu cầu vì phân loại chưa đồng bộ.
- Thời gian tìm kiếm trên 10 câu: **trung bình 32,362 ms; trung vị 16,254 ms; p95 nearest-rank 186,275 ms**. Với 10 mẫu, p95 chính là mẫu lớn nhất; câu đầu cũng là mẫu lớn nhất. Thời gian đo không gồm khởi tạo embedding/Chroma, HTTP, mạng tới model hoặc hiển thị FE. Không coi đây là benchmark tải/concurrency hoặc latency end-to-end.
- Phép đo này không gọi Gemini/Ollama, không lưu hội thoại, không rebuild chỉ mục. SHA256 trước/sau của 5 file dữ liệu trùng nhau.

Chi tiết từng câu, điểm nguồn, cấu hình, manifest và hash nằm trong [source_requirements_evaluation.json](source_requirements_evaluation.json). Bộ câu lấy từ dữ liệu hiện có và có câu gần với các câu từng dùng điều chỉnh ngưỡng; không phải tập giữ lại độc lập. **10/10 không có nghĩa chatbot chính xác 100%, cũng không phải Recall@K đầy đủ**: chưa gán mọi chunk liên quan cho từng câu, chỉ kiểm tra có bằng chứng mục tiêu trong kết quả.

Tái lập phép đo (từ thư mục gốc, cần chỉ mục tương thích đã tồn tại):

```powershell
.\.venv\Scripts\python.exe docs/evaluate_source_requirements.py
```

Script đọc `.env`, mở chỉ mục hiện hành, chỉ truy xuất và ghi đè báo cáo JSON của phép đo. Không gửi key ra báo cáo.

### Trạng thái T01–T12 trong tài liệu nguồn

| Ca | Bằng chứng / giới hạn |
| --- | --- |
| T01 Câu trực tiếp | Đã thử truy xuất thực; API gửi/nhận có test, nhánh LLM local được mock. Chưa chấm sinh câu trả lời thực toàn bộ bộ câu trong đợt đánh giá này. |
| T02 Diễn đạt lại | Có ca hỏi lại giá B2 bằng cách diễn đạt khác trong smoke; chưa phải đánh giá paraphrase diện rộng. |
| T03 Hỏi nối tiếp | Chưa đáp ứng theo mã: không truyền lịch sử cho truy xuất/LLM. Kiểm thử owner chứng minh cách ly phiên, không chứng minh hiểu “cái đó”. |
| T04 Thiếu đối tượng/năm | Có chỉ dẫn hỏi lại trong prompt; chưa có nhánh điều phối và test chốt hành vi. |
| T05 Ngoài phạm vi | Hai ca vector thực trả rỗng; có API test lexical không bịa. Không suy rộng cho mọi câu ngoài phạm vi. |
| T06 Sai học kỳ | Chưa có bộ lọc thời gian; chưa có tập ca nghiệp vụ được gán nhãn. Không đánh dấu đạt. |
| T07 Nhập/sửa/lặp | Test bổ sung dùng kho tạm kiểm tra thêm file, sửa mức thu, xóa file, rebuild lặp và mở lại collection. Test cũ kiểm tra rebuild lỗi giữ bản hoạt động. Chưa test xóa toàn bộ kho; `ensure_index([])` hiện báo lỗi. |
| T08 Link nguồn | API/test và FE lấy URL từ metadata. Chưa crawl xác thực khả dụng hoặc nội dung gốc ở thời điểm chấm. |
| T09 Feedback | Chưa có chức năng để thực hiện. |
| T10 Lỗi dịch vụ | Test mô phỏng Ollama/service lỗi trả 503 và không lưu lượt dở; FE có xử lý lỗi/timeout. Chưa diễn tập lỗi dịch vụ trên trình duyệt trong đợt này. |
| T11 Truy vấn lịch sử | Không có bộ lọc hết hạn nên không loại máy móc, nhưng cũng chưa hiểu thời điểm hỏi hay chọn đúng phiên bản. Chưa đánh dấu đạt. |
| T12 Thời gian | Đã đo 10 truy vấn retrieval và ghi mẫu; chưa đo nhiều lượt end-to-end hoặc TTFT/streaming. |

## 3. Trả lời các câu hỏi còn mở ở mục 11

**Mã nguồn ở đâu, stack gì?** `D:\chatbot-ptit`; FE Vue 3/TypeScript/Pinia/Router/Vite; BE FastAPI/Uvicorn/Pydantic/HTTPX; SQLite cho hội thoại, Chroma cho vector; FastEmbed ONNX E5-small cho embedding. Gemini và Ollama là hai nhánh sinh văn bản có mã thực, không suy ra từ bản thảo. Cấu hình triển khai xem `BE/.env`; không công bố key trong tài liệu đánh giá.

**Có bao nhiêu tài liệu, xuất xứ thế nào?** 5 file Markdown, tổng 26.944 byte, chỉ mục hiện hành 69 chunk/384 chiều. Các file là `clb.md`, `ktx.md`, `quy_che_chung.md`, `thu_vien.md`, `thuc_tap_viec_lam.md`. Metadata dẫn tới ptit.edu.vn, giaovu.ptit.edu.vn và lib.ptit.edu.vn. Đây là snapshot đã biên tập trong repository, chưa được đợt chấm này xác thực lại trực tuyến. Không khẳng định mọi đoạn đều là thông báo hiện hành hoặc trích nguyên văn.

**Dữ liệu có phải toàn bộ từ năm 2025?** Không. KTX là thông báo khóa 2025, thực tập có thông báo 2026; thủ tục có ngày gốc 2021 và nội quy thư viện dẫn quyết định 2009. `fetched_date` năm 2026 không phải ngày ban hành. Các ghi chú đã nêu hạn chế; không sửa/xóa/khôi phục dữ liệu theo ràng buộc giữ nguyên của người dùng.

**Phiên ẩn danh hay đăng nhập?** Phiên trình duyệt ẩn danh qua `ptit_session`, UUID, cookie 30 ngày, HttpOnly/SameSite Lax; SQLite kiểm tra owner. Chưa có đăng ký/đăng nhập, JWT hoặc OAuth. Đổi trình duyệt/mất cookie không tự khôi phục quyền truy cập lịch sử; chưa có cơ chế tài khoản đa thiết bị.

**Có hybrid search không?** Chưa có hybrid kết hợp thứ hạng. Vector là nhánh chính, lexical kiểu TF/IDF theo từ là dự phòng khi vector lỗi. Không chạy hai nhánh để hợp nhất; không phải BM25 hoặc reranking. Chưa có bộ lọc metadata năm/học kỳ/nhóm trong lời gọi search.

**Tham số được chọn thế nào?** Cấu hình hiện tại: E5-small; chunk 400 ký tự, overlap 60 ký tự (không phải 400/60 token); Top-K 4; ngưỡng cosine 0,80. Chia theo heading rồi recursive splitter. Ngưỡng đã được thử trên tập nhỏ, chưa tối ưu có hệ thống hoặc đánh giá độc lập. E5-small phù hợp nhu cầu chạy local nhẹ, không đồng nghĩa đã chứng minh là model tốt nhất.

**Có tự học khi nói chuyện không?** Không. Hội thoại lưu SQLite, không tự đi vào kho tri thức hoặc huấn luyện model. Thay tài liệu rồi ingest là cập nhật kho truy xuất, không phải fine-tune LLM. Hiện chưa có feedback pipeline để duyệt tri thức mới.

## 4. Luồng thực tế và bằng chứng module

| Chặng | File / hàm | Hành vi thực |
| --- | --- | --- |
| Nhập câu hỏi | `FE/src/features/chat/chat.store.ts`, `chat.service.ts` | Tin nhắn chờ, cookie, request UUID, timeout 120 giây, Fetch JSON; không streaming. |
| API/phiên | `BE/main.py:create_app`, `browser_session`, `send_message` | Kiểm tra chủ hội thoại, chống ghi trùng khi retry, gọi RAG bằng câu hiện tại. |
| Tài liệu | `BE/knowledge.py:_read_documents`, `_heading_chunks`, `chunks` | Đọc YAML front matter, heading, chia đoạn; sửa lỗi note đơn giản trong bộ nhớ, không ghi lại source. |
| Embedding/chỉ mục | `BE/rag_store.py:E5Embeddings`, `RagStore.ensure_index` | Passage/query prefix, cache vector, collection cosine, fingerprint và manifest chuyển sau rebuild. |
| Truy xuất | `Knowledge.retrieve`, `RagStore.search` | Top-K, lọc từng đoạn theo cosine; trace thời gian; lexical fallback khi lỗi, không fallback khi vector trả rỗng. |
| Tạo câu trả lời | `Knowledge.answer` | Chưa đủ nguồn thì không gọi LLM; có nguồn thì prompt có chỉ dẫn và tài liệu đánh số. Ollama rút gọn context; Gemini gửi nội dung kèm note/URL. |
| Lưu/hiển thị | `BE/database.py:save_turn`, `MessageBubble.vue` | Ghi nguyên lượt trong transaction sau khi thành công; hiển thị đoạn nguồn/link và thời gian. |

Hai lưu ý vận hành: (1) ingest ở tiến trình riêng không tự chuyển collection mà BE đang giữ; cần restart BE để nạp bản mới. (2) tạo collection mới giữ bản cũ trên đĩa, vì vậy xóa file khỏi `data/` và rebuild không đồng nghĩa đã xóa vật lý mọi vector cũ. Không tự dọn dữ liệu trong đợt đánh giá này.

## 5. Các yêu cầu tài liệu đã xử lý và việc còn thiếu

P01 hoàn thành: đối chiếu manifest, cấu hình và điểm khởi chạy, có bảng công nghệ.
P02 hoàn thành ở phạm vi rà soát: truy vết pipeline, test cập nhật kho tạm, ghi giới hạn phiên bản và metadata.
P03 hoàn thành ở phạm vi rà soát: truy request và ngoại lệ, chỉ ra thiếu ngữ cảnh hội thoại.
P04 hoàn thành một phần: có ca smoke, thời gian thực, test và build; chưa có feedback/reranking và bộ đánh giá end-to-end độc lập.
P05 hoàn thành ở phạm vi hiện tại: báo cáo này và JSON phân biệt đã có, đã chạy kiểm tra, chưa có và chưa kiểm chứng.

Các điểm cần chỉnh trong bản thảo: thay mô tả stack “chưa biết” bằng stack có mã chứng minh; bỏ khẳng định “độ chính xác tuyệt đối”; ghi đúng snapshot/ngày ban hành; không ghi đã có hybrid, feedback, reformulation hoặc tài khoản. Việc thống nhất tiêu đề Chương 3, MSSV Đinh Tuấn Anh và tỷ lệ tham gia cần bản thảo gốc và thông tin nhóm; các tệp S01/S02/S03 không có trong đầu vào đợt này, không tự điền hay suy đoán.

Thứ tự cải thiện để tăng mức đáp ứng:

1. R003: đưa lịch sử gần của đúng owner vào xử lý truy vấn; kiểm thử hỏi tiếp và cách ly phiên, giới hạn context.
2. R010: feedback gắn `message_id`, owner, đánh giá và nhận xét; API/UI/test, không tự đưa feedback vào tri thức.
3. R011/R004: thống nhất 4 nhóm `thong_bao`, `tin_tuc_su_kien`, `thong_tin_dao_tao`, `hoat_dong_sinh_vien`, giữ nhóm chi tiết hiện có như taxonomy phụ; bổ sung ngày/hiệu lực/đối tượng và quy tắc truy vấn lịch sử. Chưa tự ánh xạ hoặc sửa dữ liệu vì cần giữ nguyên bộ dữ liệu hiện tại.
4. R012/R005: tập hỏi độc lập có đáp án và chunk nguồn, đo Recall@K, chấm câu trả lời/nguồn, p50/p95 end-to-end; kiểm tra mã trích dẫn và nội dung vượt bằng chứng.
5. Sau khi đo các mục trên, mới cân nhắc hybrid/reranking và streaming theo lỗi/chậm thực tế.

Đợt này bổ sung báo cáo, script đo và test cập nhật, không tự thay stack, crawl lại dữ liệu, thêm tài khoản hoặc coi các đề xuất trong nguồn là yêu cầu triển khai mọi tính năng ngay lập tức. Bộ dữ liệu thật giữ nguyên SHA256; các thiếu hụt bắt buộc được chấm đúng trạng thái, chưa được mô tả là đã sửa.
