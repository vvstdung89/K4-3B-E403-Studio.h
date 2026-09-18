# Reflection cá nhân — Lương Sỹ Khánh

**Vai trò:** Discord integration + phát hiện tin nhắn chưa được trả lời (`detect/`, `data/`, phần lớn `bot_gateway.py`).

**Phần việc:** Bộ lọc rule-based phát hiện câu hỏi chưa trả lời (`detect/rules.py`), nạp dữ liệu Discord thật/CSV (`data/`), và toàn bộ phần bot trên Discord: hai lệnh slash `/labcoach-check` và `/labcoach-demo`, tác vụ nền tự động kiểm tra định kỳ (`auto_check_live`, không cần ai gõ lệnh), tùy chọn quét toàn bộ lịch sử kênh thay vì chỉ cửa sổ gần đây, nút bấm tương tác trên mỗi cảnh báo (nhảy tới tin nhắn gốc / đánh dấu đã xử lý), và đồng bộ trạng thái đó về dashboard.

## Khó khăn gặp phải và cách xử lý

Ban đầu `detect/rules.py` chỉ nhận tin có dấu "?" và chưa có `reply_to` — bỏ sót nhiều câu hỏi thật (không có dấu chấm hỏi, câu hỏi lồng trong câu dài). Khi nới lỏng bộ lọc để chỉ loại tin của bot, số candidate tăng từ 21 lên 779 trong một lần chạy thử trên dữ liệu thật - bước AI-review phía sau không thể xử lý hết, và nếu mặc định "vẫn cần chú ý" cho phần chưa kịp review thì bot sẽ gửi hàng trăm embed vào kênh chỉ trong một lần chạy, rất nguy hiểm cho một bot đang chạy sống trên kênh lớp thật.

Hướng xử lý lúc đó: thêm một hàm giới hạn số candidate được AI review mỗi lần gọi, phần còn lại mặc định "chưa cần chú ý" thay vì "cần chú ý" để tránh flood.

## Điều đã học qua phần việc này

- Nới lỏng rule-based detection để tăng recall luôn kéo theo tăng khối lượng xử lý phía sau — không thể thiết kế `detect/` tách rời AI-review và notification, phải tính cả pipeline.
- **Một guard được viết ra trong code không có nghĩa là nó thật sự đang chạy.** Khi rà soát lại kỹ hơn, phát hiện hàm giới hạn nói trên được định nghĩa lặp lại ở cả ba file gọi tới AI review, nhưng **không file nào thực sự gọi nó** — mọi đường chạy sống đều gọi thẳng bước AI-review không giới hạn. Tức là bản "fix" ban đầu chưa từng thật sự có hiệu lực, dù nhìn code thì tưởng đã fix — đây là bài học/case fail thật của nhóm mà mình cho là quan trọng nhất.
- `reply_to` chỉ là bằng chứng có liên kết, không phải bằng chứng đã được trả lời đầy đủ — và một câu trả lời ở kênh/luồng khác thì bộ lọc reply-based hiện tại không thấy được.

## Nếu làm lại sẽ cải thiện việc gì

- Sau khi thêm một guard quan trọng như giới hạn AI-review, phải có test xác nhận nó **thực sự được gọi** ở đường chạy chính, không chỉ tin là code đã tồn tại trong file.
- Gộp các câu hỏi lặp lại từ cùng một người/cùng vấn đề trước khi đưa vào AI-review, giảm cả rủi ro flood lẫn tải xử lý.
- Kiểm tra kỹ ngưỡng thời gian chờ trước khi để chạy tự động không giám sát — README của nhóm tự ghi rõ ngưỡng chờ yêu cầu vẫn chưa được `detect/` áp dụng đầy đủ, đây là rủi ro thật vẫn chưa xử lý hết.

## AI/công cụ hỗ trợ đã dùng, dùng vào đâu và cách kiểm tra kết quả

Dùng Claude Code (Claude Sonnet 5) để: gộp lại logic trùng lặp giữa 4 entry point đang gọi cùng một pipeline, thêm tùy chọn quét toàn bộ lịch sử kênh, thêm tác vụ nền tự động kiểm tra định kỳ, thêm nút bấm tương tác và đồng bộ trạng thái "đã xử lý" với dashboard, và sửa lỗi dashboard báo "không tìm thấy trace AI".

Mỗi thay đổi đều được xác nhận bằng cách chạy thật, không chỉ tin câu trả lời của AI: chạy lại toàn bộ test hiện có (29 test, `python3 -m unittest discover`), gọi thật API dashboard (`/api/runs`, `/api/traces`) để so sánh dữ liệu trước/sau, và khởi động lại bot thật để xem log đăng nhập/đồng bộ lệnh có lỗi không. Có một lần khi thử AI, nó vô tình gửi thật 2 cảnh báo vào kênh lớp đang hoạt động (nội dung đúng, nhưng không được chủ động cho phép việc gửi tại đúng thời điểm đó) - sau việc yêu cầu AI phải xác nhận trước mỗi lần thử nghiệm thay vì tự ý chạy.
