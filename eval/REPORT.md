# Báo cáo golden set — 18/09/2026

**Chạy lại đủ 30 ca: 27 PASS, 3 FAIL (90%).** Dùng `gpt-5.4`, reasoning `medium`, dữ liệu từ `eval/golden_set/`; hoàn tất khoảng 19:26 (UTC+7). Golden set giữ nguyên 30 testcase gốc và nhãn kỳ vọng. Đã đối chiếu SHA-256 của bản tổng hợp và từng file với `testcases.json` / `testcases/`.

| Nhóm | Quy tắc nhắc | Kết quả |
| --- | --- | --- |
| K4-01–K4-10 | `per_issue` | 8/10 PASS |
| K4-H11–K4-H20 | `per_message` | 10/10 PASS |
| K4-H21–K4-H30 | `per_message` | 9/10 PASS |
| Checkpoint H15 (index 2, 4), H16 (index 2, 3) | `per_message` | 4/4 PASS |
| Test hồi quy offline | Không gọi model | 20/20 PASS |

Chấm nhãn phân loại, trạng thái phản hồi, người phản hồi, nhu cầu nhắc LabCoach, số lượng và thành viên nhóm nhắc. Theo yêu cầu, không chấm chất lượng dữ liệu (`data_quality_flags`). Các đầu ra model của lần chạy mới đã được chấm lại bằng bộ đối chiếu sửa lỗi trùng ID; không gọi lại model để chọn kết quả tốt hơn.

**Ba ca lỗi:**

| Ca / tin | Kỳ vọng → thực tế | Nguyên nhân quan sát được |
| --- | --- | --- |
| K4-08 / `M84662` | `answered` → `partial_or_deferred`; mục nhắc 2 → 3 | Golden set chấp nhận hướng dẫn tạo ticket cho yêu cầu hỗ trợ Phoenix. Mô hình coi đây là chuyển tiếp và vẫn đòi xử lý nguyên nhân lỗi. |
| K4-10 / `M27034` | `answered` → `partial_or_deferred`; mục nhắc 2 → 3 | Câu hỏi chọn giữa dùng email cá nhân hoặc sửa lỗi Zoom. Phản hồi đã xác nhận phương án email cá nhân, nhưng mô hình vẫn coi cách sửa lỗi là một yêu cầu chưa đáp ứng. |
| K4-H28 / `M90350` | `no_visible_response` → `answered`; mục nhắc 1 → 0 | Phản hồi bot `M90351` trả lời `M90349` bị áp dụng thêm cho bản hỏi song song `M90350`. |

Lần trước đạt 29/30, chỉ lỗi K4-H28. Hai ca K4-08 và K4-10 thay đổi phân loại giữa hai lần chạy với cùng model, reasoning và logic phân loại; kết quả chưa ổn định. Các lỗi này cần tiếp tục xử lý, chưa thể kết luận golden set đã đạt toàn bộ.

**Phần đã sửa:**

- Tách nhận diện câu hỏi và xác định trạng thái thành hai bước; kiểm tra đủ chỉ số đầu vào, thử lại một lần nếu model bỏ sót hoặc lặp chỉ số.
- Bổ sung ngữ cảnh hội thoại, bằng chứng phản hồi, các ý hỏi còn thiếu và quy tắc phân biệt trả lời đầy đủ với trì hoãn/chuyển tiếp.
- Tính nhãn và số lượng từ kết quả phân loại; hỗ trợ gom mục nhắc theo vấn đề hoặc giữ riêng từng tin.
- Thêm lựa chọn model, cấu hình reasoning cho GPT-5 và bỏ tham số temperature khi dùng các model này.
- Sửa bộ chấm dùng `input_index` khi có, kiểm tra đầy đủ khóa tin trong mục nhắc, tránh ghi đè hai tin trùng `msg_id` ở khác kênh. Bổ sung 5 test hồi quy cho lỗi này; tổng cộng 20 test offline đạt.

Bảng đầy đủ tại [golden_set.md](golden_set.md); lệnh tái chạy tại [RUNNING.md](RUNNING.md). Phạm vi kiểm thử là classifier của golden set; chưa dùng kết quả này để kết luận chất lượng luồng bot chạy thực tế. Log và JSON chi tiết nằm cục bộ trong `outputs/golden-retest-*`; không commit `outputs/`.
