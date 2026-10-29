# Đánh giá hệ thống chatbot PTIT sau cập nhật

Ngày đối chiếu 29/10/2026. Mã nguồn tại `D:\chatbot-ptit`. Tiêu chí từ `SOURCE_REQUIREMENTS.md` do người dùng cung cấp, mục 3, 10, 11 và phụ lục A.

## 1 Kết luận và cách chấm điểm

**Điểm đề xuất 7,1/10**, tương ứng 8,5/12 điểm yêu cầu bắt buộc. Hệ thống đã có chatbot RAG hoạt động, hybrid search thực sự, dữ liệu năm 2026 và nguồn riêng cho từng bài. Các khoảng thiếu chính là ngữ cảnh hội thoại, phản hồi người dùng, lọc phạm vi theo metadata và đánh giá chất lượng độc lập.

Tài liệu nguồn không có rubric điểm chính thức. Báo cáo dùng lại thang của lần đánh giá trước để so sánh: R001–R012 có trọng số bằng nhau, tối đa 1 điểm/mục; 1 là đáp ứng, 0,75 là phần chính đã có nhưng còn kiểm soát hoặc kiểm chứng thiếu, 0,5 là một phần, 0,25 là mới có nền tảng, 0 là chưa triển khai. Điểm là mức đáp ứng yêu cầu phần mềm, không phải tỷ lệ trả lời chính xác hoặc điểm của giảng viên.

So với 6,7/10 trước đây, R003 tăng từ 0 lên 0,25 vì đã có xử lý truy vấn thực sự; chưa có ngữ cảnh nên không chấm cao hơn. R011 tăng từ 0,25 lên 0,5 vì đã có ngày đăng và URL riêng xuyên suốt bài, chunk, API và FE; vẫn khác bốn nhóm yêu cầu và thiếu metadata hiệu lực. Tổng tăng từ 8 lên 8,5; **8,5/12 × 10 = 7,083**, làm tròn 7,1. Các mục khác giữ điểm cũ để tránh tự tăng điểm chỉ vì thêm dữ liệu hoặc thay model.

| ID và tiêu chí | Điểm / 1 | Bằng chứng hiện tại và giới hạn |
| --- | ---: | --- |
| R001 Công nghệ và luồng | 1 | Đã đối chiếu package, cấu hình và module. Báo cáo có kiến trúc, pipeline và luồng ngoại lệ. |
| R002 Câu hỏi tự nhiên | 1 | FE nhập/gửi tiếng Việt; API kiểm tra câu rỗng, độ dài và request UUID; có test gửi/nhận hội thoại. |
| R003 Xử lý truy vấn và ngữ cảnh | 0,25 | Có Unicode NFC, khoảng trắng, tên đầy đủ/viết tắt và từ khóa không dấu. API vẫn chỉ truyền câu hiện tại vào Knowledge.answer; chưa giải quyết “cái đó”, “khi nào” dựa trên lịch sử. |
| R004 Embedding và Vector DB | 0,75 | E5-small 384 chiều, Chroma cosine, hybrid BM25 và RRF đã có, kiểm tra trên vector thật. Chưa lọc chắc chắn năm học, học kỳ, cơ sở, đối tượng hoặc hiệu lực. |
| R005 Sinh từ context | 0,75 | Prompt dùng các đoạn nguồn đánh số, yêu cầu giữ điều kiện và không làm theo chỉ thị trong tài liệu. Chưa kiểm chứng từng khẳng định hoặc có bộ chấm câu trả lời độc lập. |
| R006 Hiển thị nguồn | 1 | Chunk/API/FE giữ URL và ngày đăng riêng của bài trong file tổng hợp. FE chỉ mở HTTP(S), hiển thị đoạn nguồn và ngày thu thập riêng. Chưa tự kiểm tra mã trích dẫn model sinh. |
| R007 Cập nhật dữ liệu | 1 | Crawler 2026, staging, backup, ingest và cache embedding. Test kho tạm xác minh thêm/sửa/xóa/lặp và rebuild lỗi. Cần restart BE sau ingest riêng. |
| R008 Thiếu bằng chứng | 0,75 | Có cổng cosine, khớp từ khóa và từ chối khi không có nguồn; không gọi LLM ở nhánh này. Kiểm tra âm tính có kết quả thực; chưa bảo đảm đúng với mọi câu hoặc tài liệu mâu thuẫn. |
| R009 Phiên và lịch sử | 1 | SQLite, cookie ẩn danh và điều kiện owner; test chặn truy cập chéo, lưu qua khởi động lại, retry không ghi trùng. Chưa có tài khoản đa thiết bị, nhưng nguồn chưa chốt cơ chế đăng nhập. |
| R010 Feedback | 0 | Chưa có schema, bảng, API hoặc UI ghi nhận đánh giá gắn đúng assistant message. |
| R011 Nhóm và metadata | 0,5 | Có 5 nhóm, tiêu đề, URL, ngày đăng/thu thập riêng từng bài và chunk. Chưa khớp 4 nhóm trong nguồn; chưa có hieu_luc_den, tu_khoa và chính sách văn bản thay thế đầy đủ. |
| R012 Đánh giá chất lượng | 0,5 | 36 test BE đạt, FE build đạt; có phép đo truy xuất và API dùng kho vector thật. Thiếu tập độc lập có nhãn, Recall@K đầy đủ, chấm câu trả lời, nguồn, hài lòng và latency end-to-end nhiều mẫu. |
| Tổng yêu cầu bắt buộc | 8,5 / 12 | 7,1 / 10 sau làm tròn |

R013 là khuyến nghị reranking: **chưa có cross-encoder hoặc model đánh giá lại từng cặp câu hỏi–đoạn**. RRF hợp nhất thứ hạng đã có nhưng không đồng nghĩa triển khai reranker theo R013. Không trừ R013 vào điểm bắt buộc.

R014 là khuyến nghị phiên bản: có fingerprint nội dung/cấu hình, collection mới và chuyển manifest khi hoàn tất. Rebuild lỗi giữ bản cũ. Chưa có giao diện quản lý văn bản thay thế, dọn mọi collection cũ hoặc tự chuyển collection của BE đang chạy; bản cũ còn trên đĩa không đồng nghĩa còn nằm trong chỉ mục hoạt động.

## 2 Công nghệ và cấu hình đang dùng

| Thành phần | Công nghệ và trách nhiệm |
| --- | --- |
| Giao diện | Vue 3, TypeScript, Pinia, Vue Router, Vite; Fetch JSON, tin nhắn chờ và Thinking... |
| API | Python, FastAPI, Uvicorn, Pydantic; xác định owner, kiểm tra input và điều phối |
| Lịch sử | SQLite; conversations và messages, lưu trọn lượt sau khi sinh thành công |
| Dữ liệu | 5 file Markdown có front matter nhóm và source_metadata riêng trước từng bài |
| Chia đoạn | Heading và RecursiveCharacterTextSplitter, 400 ký tự và overlap 60 ký tự |
| Embedding | intfloat/multilingual-e5-small qua FastEmbed/ONNX int8 trên CPU; 384 chiều |
| Vector | ChromaDB persistent, cosine; passage: cho tài liệu, query: cho câu hỏi |
| Từ khóa | BM25 viết trong search_text.py; không dấu, cache RAM theo collection |
| Hợp nhất | Reciprocal Rank Fusion, cộng 1/(60 + thứ hạng) cho mỗi nhánh có ứng viên |
| Sinh văn bản | Gemini API hiện cấu hình gemini-3.5-flash-lite; nhánh Ollama vẫn có thể chọn qua .env |

`BE/.env` là cấu hình chính, nạp ưu tiên hơn environment của tiến trình và cần restart sau khi đổi. Hiện `RETRIEVAL_BACKEND=vector`, `RETRIEVAL_HYBRID=true`, `RAG_TOP_K=4`, `RAG_MIN_SCORE=0.80`, `RAG_SEMANTIC_ONLY_MARGIN=0.08`, `DIRECT_OLLAMA_CHAT=false`.

Embedding, BM25, Chroma và SQLite chạy local. Với Gemini, câu hỏi và các đoạn nguồn được gửi qua HTTPS tới Google; key ở BE, không gửi xuống FE. Kết nối dùng truststore và vẫn kiểm tra chứng chỉ. Đổi riêng Gemini sang Ollama không cần embedding lại. Model local có hậu tố -cloud bị chặn ở nhánh Ollama local.

## 3 Dữ liệu năm 2026 và xuất xứ

Kho đang nạp gồm **160 bài đăng**, tổng **625.083 byte** trong 5 file; chỉ mục gồm **1.459 chunk, 384 chiều**. Số file không bằng số bài và không bằng số chunk. Các số này lấy từ report.json, manifest và kiểm tra hash, không suy ra từ tên file.

| File | Vai trò dữ liệu | Số bài |
| --- | --- | ---: |
| clb.md | Câu lạc bộ, hoạt động Đoàn/Hội, tình nguyện | 3 |
| ktx.md | Ký túc xá và nội trú | 3 |
| quy_che_chung.md | Quy chế, thủ tục, học vụ, học phí và chính sách sinh viên | 126 |
| thu_vien.md | Thư viện, học liệu, sách và văn hóa đọc | 9 |
| thuc_tap_viec_lam.md | Thực tập, hướng nghiệp, tuyển dụng và việc làm | 19 |
| Tổng | Năm nhóm theo yêu cầu giữ file hiện có | 160 |

Nguồn gồm student.ptit.edu.vn, giaovu.ptit.edu.vn, daotao.ptit.edu.vn, tuyensinh.ptit.edu.vn, ptit.edu.vn, lib.ptit.edu.vn và API bài công khai qldt.ptit.edu.vn. Crawler duyệt 770 bản ghi để lọc; không gọi đó là 770 bài năm 2026 vì danh sách QLDT có cả bản ghi ngoài năm. Dữ liệu được lọc theo trường ngày đăng của API và loại trùng; không dùng năm trong tiêu đề hoặc ngày thu thập thay cho ngày đăng.

Phạm vi là bài công khai đăng từ 01/01/2026 đến thời điểm thu thập 29/10/2026, không phải dữ liệu trọn năm tương lai hoặc toàn bộ website. Một bài đăng năm 2026 có thể nói về năm học 2025–2026 hay viện dẫn văn bản cũ; không tự loại phần điều kiện đó. Ngày đăng cũng không xác nhận ngày bắt đầu hoặc hết hiệu lực.

Mỗi bài có URL, ngày đăng, ngày thu thập và tiêu đề riêng trong comment source_metadata. Parser dùng marker để tách ranh giới bài và gắn metadata đúng cho từng chunk; marker không được đưa vào prompt. API Source giữ publish_date; FE hiển thị ngày đăng và ngày thu thập tách biệt.

Đã sao lưu 5 file trước thay đổi ngoài data/. Nguồn ảnh, PDF, Word và Excel đính kèm trong đợt này mới giữ liên kết, chưa trích nội dung hoặc OCR. Không coi alt ảnh/tên file là bằng chứng đã đọc. Crawler không đăng nhập và chưa bao phủ mọi endpoint. Phân loại theo vai trò không biến các thông báo thu thập thành quy định còn hiệu lực ở hiện tại.

## 4 Luồng xử lý thực tế và các nhánh ngoại lệ

### 4.1 Lập chỉ mục và cập nhật

Crawler lấy bài có ngày đăng phù hợp, làm sạch nội dung HTML, phân loại, loại trùng và ghi staging. Khi áp dụng, sao lưu 5 file rồi thay đúng 5 file dữ liệu. Không tự tạo thêm nhóm hoặc chạy thu thập định kỳ.

Ingest đọc front matter và marker nguồn từng bài, chia heading rồi chia đoạn theo ký tự. Fingerprint gồm nội dung, metadata, model và cấu hình; vector có cache nên không nhất thiết tính lại mọi đoạn. Khi dữ liệu đổi, tạo collection mới và chỉ đổi manifest sau khi hoàn tất; lỗi giữ collection cũ. Test cập nhật dùng kho tạm, không sửa dữ liệu thật.

BE khởi động nạp collection và làm nóng cache BM25. Ingest ở tiến trình riêng không tự chuyển collection mà BE đang giữ, vì vậy cần restart BE để dùng bản mới. Các collection cũ có thể còn trên đĩa; xóa bài khỏi chỉ mục mới không đồng nghĩa xóa vật lý mọi bản lưu.

### 4.2 Tiếp nhận và truy xuất

FE hiện tin nhắn chờ, gửi message/request_id cùng cookie. BE kiểm tra UUID hội thoại và owner, xử lý retry đã hoàn tất rồi gọi RAG bằng câu hỏi hiện tại. **Lịch sử được lưu nhưng chưa được dùng để hiểu câu hỏi tiếp nối.**

Truy vấn được chuẩn hóa Unicode NFC, khoảng trắng và thuật ngữ tên đầy đủ/viết tắt như BHYT, KTX, CLB, TTTN, ĐHCQ, CNTT, ATTT. Danh sách chỉ gồm các thuật ngữ đã xác định; từ mơ hồ như TV không được tự đoán nghĩa. Nhánh BM25 loại dấu trên cả tài liệu và truy vấn, nên có thể tìm cụm không dấu ngoài danh sách. Cơ chế không phải bộ sửa mọi lỗi chính tả hoặc phục hồi dấu tổng quát.

E5 tạo vector cho các biến thể truy vấn được chọn; Chroma trả tập ứng viên. BM25 chạy trên cùng các chunk và metadata của collection đang hoạt động. Với Top-K 4 hiện tại, mỗi nhánh xét tối đa 16 ứng viên. Điểm cosine và BM25 không được cộng trực tiếp; kết quả được lọc bằng chứng và hợp nhất theo RRF, cuối cùng lấy tối đa 4 nguồn.

Ngưỡng 0,80 áp dụng cho cosine. Ứng viên từ khóa khớp mạnh có thể đủ điều kiện dù cosine thấp; cụm ngắn cần đủ từ và đúng chuỗi sau chuẩn hóa, câu dài dùng tỷ lệ bao phủ từ khóa. Với ứng viên vector thiếu hỗ trợ từ khóa, margin 0,08 làm yêu cầu điểm ngữ nghĩa chặt hơn. Đây là heuristic trên tập hiện tại, không phải bảo đảm truy xuất đúng tuyệt đối.

API ghi rõ score_type là cosine_similarity hoặc bm25; semantic_score, lexical_score và fusion_score tách các thang điểm. Chúng không phải xác suất trả lời đúng. /api/rag/search trả query_processing và hybrid_search để kiểm tra từng bước; health/status có search_strategy.

### 4.3 Sinh trả lời và lưu trữ

Không có bằng chứng phù hợp thì trả thiếu dữ liệu, không gọi LLM. Có nguồn nhưng thiếu API key thì chỉ trả kết quả tra cứu. Có model/key thì ghép các đoạn đánh số, ghi chú ngày và URL vào prompt, yêu cầu chỉ dùng bằng chứng và không làm theo chỉ thị trong tài liệu. Gemini hoặc Ollama tạo đáp án; Ollama có giới hạn context cho máy local.

API kiểm tra cấu trúc Source rồi lưu nguyên lượt hỏi–đáp trong transaction SQLite. FE hiển thị lời đáp cùng đoạn nguồn, URL và ngày đăng/thu thập. Chưa kiểm chứng tự động từng khẳng định, mã trích dẫn hoặc mâu thuẫn giữa tài liệu. FE hiện đợi JSON đầy đủ, chưa streaming token.

| Tình huống | Hành vi hiện có và giới hạn |
| --- | --- |
| Sai owner hoặc ID không có | 404; input không hợp lệ trả 422; không đọc/ghi/xóa lịch sử phiên khác |
| Vector lỗi | Ghi cảnh báo, dùng BM25 dự phòng với cùng chuẩn hóa |
| Không có nguồn | Thông báo thiếu thông tin; không buộc LLM trả lời |
| LLM/mạng lỗi | 503 và không lưu lượt dở; FE hiện lỗi, cho thử lại |
| Retry cùng request_id | Lượt đã lưu không bị ghi trùng; chưa có bằng chứng đây là cơ chế tránh mọi lần gọi LLM đồng thời |
| Câu hỏi thiếu khóa hoặc sai kỳ | Có chỉ dẫn trong prompt; chưa có bộ lọc/điều phối đủ để đảm bảo chọn đúng phạm vi |

## 5 Kiểm thử và số đo có bằng chứng

**36/36 test BE đạt** trong lần chạy đối chiếu báo cáo; FE type-check và build đã đạt sau cập nhật tìm kiếm. Test bao gồm API, owner, retry, lỗi dịch vụ, Chroma với encoder giả, cập nhật dữ liệu tạm, alias, Unicode, BM25 và lọc khớp yếu. Kết quả unit/integration không thay cho chấm chất lượng model thật.

Đợt kiểm tra kho mới trước hybrid tìm được file mong đợi ở cả 5 nhóm. Sau hybrid, có 11 truy vấn phát triển trên Chroma/E5 thật; log chi tiết nằm trong search_normalization_evaluation.json. Một kiểm tra API riêng chạy bằng TestClient, SQLite tạm và vector thật xác nhận schema/diagnostic, không gọi LLM hoặc lưu hội thoại. Hash của 5 file dữ liệu không đổi sau tối ưu tìm kiếm.

| Kiểm tra trực tiếp | Kết quả đã quan sát |
| --- | --- |
| bao hiem  y te / bảo hiểm y tế / bhyt | Cùng URL đầu về gia hạn thẻ BHYT năm học 2026–2027 |
| ky tuc xa / ktx | Cùng URL đầu về đăng ký nội trú Hà Đông tháng 1/2026 |
| thuc tap tot nghiep / tttn | Có kết quả tương đương; vẫn cần khóa/ngành để chọn thông báo cụ thể |
| Pizza không dấu, quasar, bảo hiểm thất nghiệp | Các câu thử trả rỗng sau cập nhật; không suy rộng cho mọi câu ngoài phạm vi |
| Truy xuất sau khởi tạo | Trung bình khoảng 53,56 ms trên 10 lượt trong phép đo trực tiếp |
| Lượt đầu tạo cache BM25 | Khoảng 1.526,47 ms; BE đã có warm_up khi khởi động |

Thời gian trên không gồm khởi tạo model, mạng/API model sinh câu trả lời hay hiển thị FE. Chưa có benchmark tải đồng thời hoặc thống kê p95 end-to-end đủ mẫu. Bộ câu phát triển không độc lập với quá trình chọn thuật ngữ/tham số; không ghi 100% chính xác hoặc Recall@K đầy đủ từ các phép thử này.

### Truy vết các ca T01 đến T12

| Ca | Trạng thái và giới hạn |
| --- | --- |
| T01 Câu trực tiếp | Có kiểm tra tìm nguồn thật và API; chưa chấm đủ đầu ra LLM trên tập độc lập |
| T02 Diễn đạt lại | Có không dấu, khoảng trắng, tên đầy đủ/viết tắt; chưa đánh giá paraphrase rộng |
| T03 Câu nối tiếp | Chưa đáp ứng; không truyền lịch sử vào truy xuất hoặc prompt |
| T04 Thiếu đối tượng | Chỉ có chỉ dẫn hỏi lại trong prompt; chưa có quy tắc điều phối và test nghiệp vụ đầy đủ |
| T05 Ngoài phạm vi | Có test và vài truy vấn âm tính thực; chưa đủ chứng minh mọi trường hợp |
| T06 Sai học kỳ | Chưa có lọc metadata và tập ca tham chiếu; chưa đánh dấu đạt |
| T07 Cập nhật | Có test thêm/sửa/xóa/lặp, mở lại index và rebuild lỗi; chưa test xoá toàn bộ kho |
| T08 Nguồn | Có URL/ngày đăng riêng và kiểm tra ranh giới bài; chưa xác thực tất cả URL gốc khi chạy báo cáo |
| T09 Feedback | Chưa có tính năng để kiểm thử |
| T10 Lỗi dịch vụ | Mô phỏng API/Ollama lỗi, 503 và không lưu dở; chưa diễn tập mọi lỗi trên trình duyệt |
| T11 Truy vấn lịch sử | Chưa chọn phiên bản theo thời điểm hỏi; không tự coi dữ liệu cũ là hiện hành |
| T12 Độ trễ | Có số đo truy xuất thực; chưa đủ đo end-to-end và tải nhiều người dùng |

## 6 Trả lời các câu hỏi còn mở của tài liệu nguồn

**Mã nguồn ở đâu và stack nào?** Repository D:\chatbot-ptit; công nghệ được xác nhận từ package.json, requirements và module ở mục 2, không suy từ bản thảo. Gemini hiện dùng gemini-3.5-flash-lite; LLM độc lập với embedding local.

**Dataset bao nhiêu và có nguồn không?** 160 bài, 5 file, 1.459 chunk; số bài từng nhóm ở mục 3. API gốc cung cấp ngày đăng; URL nằm ở từng bài và chunk. Chỉ thu bài đăng năm 2026 đến ngày thu thập, không coi nội dung tệp/ảnh chưa trích là đã nhập.

**Phiên ẩn danh hay đăng nhập?** Cookie ptit_session UUID, HttpOnly, SameSite Lax, thời hạn 30 ngày; SQLite kiểm tra owner. Chưa có JWT/OAuth, tài khoản hay khôi phục lịch sử đa thiết bị khi mất cookie.

**Có hybrid search thực sự không?** Có. Nhánh vector và nhánh BM25 cùng tìm ứng viên; RRF hợp nhất thứ hạng. Vector lỗi thì dùng BM25 dự phòng. Đây khác phiên bản cũ chỉ có lexical fallback; RRF không phải cross-encoder reranking.

**Chunk, Top-K và ngưỡng chọn thế nào?** Hiện 400/60 ký tự, Top-K 4, cosine 0,80; hybrid bổ sung BM25 và margin 0,08. Tham số đã thử trên tập nhỏ, chưa được tối ưu và xác minh trên tập giữ lại độc lập. Không gọi 400 ký tự là 400 token.

**Hệ thống tự học sau mỗi hội thoại không?** Không. Hội thoại lưu SQLite; không tự nhập vào kho tri thức hoặc fine-tune model. Thu thập/ingest cập nhật dữ liệu truy xuất; chưa có feedback được duyệt để làm tri thức mới.

**Các thông tin hành chính và bản thảo có tự sửa được không?** Chưa có bản thảo gốc S01 hoặc thông tin nhóm để xác minh MSSV, tỷ lệ tham gia và mục lục Chương 3. Không tự điền. Nội dung báo cáo kỹ thuật hiện tại cần bỏ các khẳng định đã lỗi thời như chưa có hybrid, và tránh “độ chính xác tuyệt đối”.

## 7 Bằng chứng mã nguồn và kết quả tái lập

| Chặng | File hoặc hàm | Trách nhiệm |
| --- | --- | --- |
| Giao diện | FE/src/features/chat/chat.store.ts và chat.service.ts | Pending message, request UUID, cookie và Fetch |
| API | BE/main.py create_app và send_message | Owner, input, trạng thái và điều phối |
| Dữ liệu | BE/knowledge.py _read_documents, _heading_chunks và chunks | Parser nhóm/bài, metadata và chia đoạn |
| Query và BM25 | BE/search_text.py canonical, terms và KeywordIndex | Unicode, alias, không dấu và BM25 |
| Hybrid | BE/rag_store.py search, _keywords và warm_up | Chroma, tập ứng viên, lọc, RRF và cache RAM |
| Sinh và lưu | BE/knowledge.py answer và BE/database.py save_turn | Prompt có nguồn, adapter LLM và transaction |
| Nguồn trên FE | MessageBubble.vue và BE/schemas.py Source | URL, ngày đăng/thu thập và các loại điểm |

Bằng chứng dữ liệu: docs/ptit_2026_five_files/report.json, validation.json và README.md; chỉ mục: BE/chroma_db/manifest.json. Bằng chứng tìm kiếm: docs/search_normalization_evaluation.json và search_api_validation.json. Log kiểm thử đối chiếu mới: logs/report-update-tests.log; log build: logs/search-normalization-fe-build.log. Không công bố API key trong báo cáo.

Tái lập kiểm thử bằng `.venv\Scripts\python.exe -m unittest discover -s BE/tests -v`. Build FE bằng `npm run build` trong FE. `/api/rag/search` cho phép kiểm tra từng nhánh mà không gọi LLM hoặc lưu lịch sử. Khi cần áp dụng mã mới, restart BE và kiểm tra search_strategy=hybrid. Không mặc định cho rằng tiến trình BE đang chạy đã nạp mọi thay đổi trên đĩa.

## 8 Ưu tiên cải thiện và trạng thái kế hoạch nguồn

1. R003: dùng lịch sử gần của đúng owner để làm rõ chủ đề, giữ giới hạn context; test hỏi nối tiếp và cách ly phiên.
2. R010: thêm phản hồi gắn message_id, owner, mức đánh giá và nhận xét; API/UI/test; không tự biến feedback thành quy định chính thức.
3. R011/R004: xác định ánh xạ bốn nhóm yêu cầu và năm nhóm chi tiết đang dùng, bổ sung hiệu lực, đối tượng, học kỳ và chính sách truy vấn lịch sử. Chưa tự đổi năm file vì người dùng yêu cầu giữ cấu trúc đó.
4. R012/R005: bộ câu độc lập có đáp án/chunk nguồn; Recall@K, chấm đúng điều kiện, trích dẫn và latency end-to-end; đánh giá âm tính và tình huống văn bản mâu thuẫn.
5. Sau khi đo lỗi còn lại, mới cân nhắc cross-encoder reranker hoặc streaming; chưa coi các tính năng đó là đã triển khai.

P01 đối chiếu công nghệ và P02/P03 truy vết dữ liệu/request đã có bằng chứng; P04 mới hoàn thành ở kiểm thử và phép đo phát triển, chưa xong đánh giá độc lập/feedback/reranking; P05 đã cập nhật ma trận yêu cầu và kết luận theo mã hiện tại. Các giới hạn được giữ trong báo cáo để việc demo và bảo vệ phản ánh đúng hệ thống.
