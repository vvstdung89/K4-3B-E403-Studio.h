Vai trò: Discord integration + phát hiện tin nhắn chưa trả lời (`detect/`, `data/`, `bot_gateway.py`).

Khó khăn:

- `detect/rules.py` nới lỏng bộ lọc (chỉ loại tin bot) khiến candidate tăng từ 21 lên 779 trong một lần chạy thật — AI-review phía sau không xử lý kịp, nếu mặc định "cần chú ý" cho phần chưa review thì bot flood hàng trăm embed vào kênh lớp thật.
- Xử lý: thêm hàm giới hạn số candidate được AI review mỗi lần gọi, phần dư mặc định "chưa cần chú ý".

Điều học được:

- Nới lỏng detect để tăng recall luôn kéo theo tăng tải AI-review/notification — phải thiết kế cả pipeline, không tách riêng `detect/`.
- Guard viết trong code không có nghĩa nó thật sự đang chạy: rà lại thấy hàm giới hạn AI-review định nghĩa lặp ở cả 3 file nhưng không file nào thực sự gọi nó - "fix" ban đầu chưa từng có hiệu lực dù nhìn code tưởng đã xong. Đây là case fail thật của nhóm mình cho là quan trọng nhất.
- `reply_to` chỉ là bằng chứng có liên kết, không phải đã trả lời đầy đủ; trả lời ở kênh/luồng khác thì bộ lọc hiện tại không thấy được.

Làm lại thì cải thiện:

- Viết test xác nhận guard thật sự được gọi ở đường chạy chính, không chỉ tin là code đã tồn tại trong file.
- Gộp câu hỏi lặp lại từ cùng người/cùng vấn đề trước khi đưa vào AI-review.
- Validate kỹ ngưỡng thời gian chờ trước khi để chạy tự động không giám sát.

AI hỗ trợ:

- Dùng Claude Code để gộp logic trùng lặp giữa 4 entry point, thêm tùy chọn quét toàn bộ lịch sử kênh, thêm tác vụ tự động kiểm tra định kỳ, thêm nút tương tác + đồng bộ dashboard, sửa lỗi "không tìm thấy trace AI".
- Kiểm tra bằng chạy thật, không chỉ tin AI: 29 test hiện có, gọi thật API dashboard để so sánh trước/sau, khởi động lại bot xem log lỗi. Một lần AI tự thử nghiệm đã gửi nhầm 2 cảnh báo thật vào kênh lớp — sau đó yêu cầu AI phải xác nhận trước mỗi lần thử nghiệm có thể gửi tin thật.
