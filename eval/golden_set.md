# Golden set — LabCoach unanswered-question classifier

Bộ 30 ca trong [golden_set/](golden_set/), bản tổng hợp [golden_set.json](golden_set.json), được sao chép nguyên vẹn từ [testcases/](testcases/) và [testcases.json](testcases.json): 10 cửa sổ hội thoại Discord (`K4-01`–`K4-10`) và 20 ca giả lập (`K4-H11`–`K4-H30`). Dữ liệu và nhãn kỳ vọng được khôi phục từ commit `472481115e9cbf898ac06ab0db7c5a708ef58f1b`, giữ nguyên trong lần chạy này.

**Kết quả chạy lại ngày 18/09/2026: 27/30 PASS (90%), 3 FAIL: K4-08, K4-10, K4-H28.** Model: `gpt-5.4`; reasoning: `medium`. Nhóm ca thực đạt 8/10, nhóm giả lập đạt 19/20; 4/4 checkpoint của K4-H15 và K4-H16 đạt. Lần trước đạt 29/30; bảng dưới ghi kết quả mới nhất. Chi tiết trong [báo cáo](REPORT.md).

**Phạm vi chấm:** nhãn phân loại, `response_status`, `responder`, `needs_labcoach_review`, số lượng câu hỏi/tin bỏ qua và thành viên các nhóm nhắc LabCoach. Không chấm `data_quality_flags` theo yêu cầu. PASS/FAIL áp dụng cho toàn bộ cửa sổ được chấm; cột Factor measure mô tả taxonomy và kết quả kỳ vọng của tình huống trọng tâm.

**Quy tắc nhắc:** K4-01–K4-10 dùng `per_issue` (có thể gom các tin hỏi lặp cùng vấn đề vào một mục nhắc); K4-H11–K4-H30 dùng `per_message` (mỗi tin hỏi còn tồn có một mục nhắc riêng). Cả hai đều giữ từng tin hỏi riêng khi đếm câu hỏi. Trong bảng, “cần nhắc” nghĩa là `needs_labcoach_review=true`; “không nhắc” nghĩa là `false` trên tin trọng tâm.

| Taxonomy | Class |
| --- | --- |
| `nguon_su_that` | ① Nguồn sự thật |
| `mo_ho` | ② Mơ hồ / thiếu thông tin |
| `ngoai_pham_vi` | ③ Ngoài phạm vi / thẩm quyền |
| `dac_thu_domain` | ④ Đặc thù domain |

| Index | Description | Factor measure | Pass / Fail | If fail: hypothesis why |
| --- | --- | --- | --- | --- |
| [K4-01](testcases/K4-01.json) | Hỏi cách làm daily-standup nhưng chưa thấy phản hồi | ① Nguồn sự thật · `no_visible_response` · cần nhắc LabCoach | PASS | — |
| [K4-02](testcases/K4-02.json) | Hỏi giấy chứng nhận sinh viên: cần người có thẩm quyền | ③ Ngoài phạm vi + ① Nguồn sự thật · `no_visible_response` · cần nhắc LabCoach | PASS | — |
| [K4-03](testcases/K4-03.json) | Bot trả lời dài nhưng không có hạn nộp cụ thể | ① Nguồn sự thật + ④ Đặc thù domain · `partial_or_deferred` · cần nhắc LabCoach | PASS | — |
| [K4-04](testcases/K4-04.json) | Bot nhờ Mod hỗ trợ nhưng chưa trả lời về cơ sở vật chất | ① Nguồn sự thật · `partial_or_deferred` · cần nhắc LabCoach | PASS | — |
| [K4-05](testcases/K4-05.json) | Hai ý hỏi về demo: mới trả lời ý chọn đội | ② Mơ hồ + ④ Đặc thù domain · `partial_or_deferred` · cần nhắc LabCoach | PASS | — |
| [K4-06](testcases/K4-06.json) | Phản hồi trì hoãn không có reply_to | ② Mơ hồ · `partial_or_deferred` · cần nhắc LabCoach | PASS | — |
| [K4-07](testcases/K4-07.json) | Đã có hướng dẫn điểm danh trong hội thoại dù không reply trực tiếp | ④ Đặc thù domain + ② Mơ hồ · `answered` · không nhắc | PASS | — |
| [K4-08](testcases/K4-08.json) | Cùng học viên hỏi lại: gom một vấn đề còn tồn | ④ Đặc thù domain + ② Mơ hồ · `no_visible_response` (hai tin lặp) · cần nhắc LabCoach | FAIL | Tin khác trong cửa sổ: `M84662` bị gán `partial_or_deferred` thay vì `answered`; mô hình coi hướng dẫn tạo ticket là chuyển tiếp, làm dư 1 mục nhắc. |
| [K4-09](testcases/K4-09.json) | Bot đã hướng dẫn mentor-duty: không báo nhầm câu còn tồn | ④ Đặc thù domain · `answered` · không nhắc, không đếm tin bot là câu hỏi | PASS | — |
| [K4-10](testcases/K4-10.json) | Xin gia hạn Lab2: chuyển ticket chưa phải chấp thuận | ③ Ngoài phạm vi + ④ Đặc thù domain · `partial_or_deferred` · cần nhắc LabCoach | FAIL | Tin khác trong cửa sổ: `M27034` bị gán `partial_or_deferred` thay vì `answered`; đã được hướng dẫn dùng email cá nhân nhưng mô hình vẫn đòi thêm cách sửa lỗi Zoom, làm dư 1 mục nhắc. |
| [K4-H11](testcases/K4-H11.json) | [Giả lập] Người trả lời trực tiếp đầy đủ | ④ Đặc thù domain · `answered` / responder=`user` · cảm ơn không tạo câu hỏi mới | PASS | — |
| [K4-H12](testcases/K4-H12.json) | [Giả lập] Bot trả lời đúng yêu cầu đã tag | ④ Đặc thù domain · `answered` / responder=`bot` · không bỏ qua phản hồi bot | PASS | — |
| [K4-H13](testcases/K4-H13.json) | [Giả lập] Chỉ thông báo, cảm ơn và lời chào | ② Mơ hồ + ④ Đặc thù domain · không có câu hỏi · `ignored_messages=20` | PASS | — |
| [K4-H14](testcases/K4-H14.json) | [Giả lập] Lỗi Zoom không có phản hồi | ① Nguồn sự thật · `no_visible_response` · cần nhắc LabCoach · không bịa đáp án | PASS | — |
| [K4-H15](testcases/K4-H15.json) | [Giả lập] Hẹn trả lời rồi bổ sung đầy đủ | ① Nguồn sự thật · từ `partial_or_deferred` sang `answered` / responder=`user` · cuối cửa sổ không nhắc | PASS | — |
| [K4-H16](testcases/K4-H16.json) | [Giả lập] Bot chuyển hỗ trợ, người bổ sung đáp án | ① Nguồn sự thật · bot trì hoãn, người bổ sung đầy đủ · cuối cửa sổ `answered` / responder=`user`, không nhắc | PASS | — |
| [K4-H17](testcases/K4-H17.json) | [Giả lập] Một tin hỏi hai ý, người mới trả lời một ý | ② Mơ hồ + ④ Đặc thù domain · `partial_or_deferred` / responder=`user` · cần nhắc LabCoach | PASS | — |
| [K4-H18](testcases/K4-H18.json) | [Giả lập] Hai lần hỏi lặp đều chưa có phản hồi | ② Mơ hồ + ④ Đặc thù domain · hai tin `no_visible_response` độc lập · hai mục nhắc | PASS | — |
| [K4-H19](testcases/K4-H19.json) | [Giả lập] Reply lạc đề không phải đã giải đáp | ① Nguồn sự thật · `partial_or_deferred` · cần nhắc LabCoach | PASS | — |
| [K4-H20](testcases/K4-H20.json) | [Giả lập] Reply tới tin cha không có trong input | ① Nguồn sự thật + ② Mơ hồ · câu hỏi trọng tâm `no_visible_response` · không gán reply mất tin cha cho câu hỏi khác | PASS | — |
| [K4-H21](testcases/K4-H21.json) | [Giả lập] Trùng msg_id ở hai kênh, chỉ một câu có đáp án | ④ Đặc thù domain + ② Mơ hồ · phân biệt hai tin `M90206` theo kênh và `input_index`: một `answered`, một `no_visible_response` | PASS | — |
| [K4-H22](testcases/K4-H22.json) | [Giả lập] Nội dung nhiều dòng và dấu ngoặc kép vẫn là một tin | ④ Đặc thù domain · giữ một bản ghi cho nội dung nhiều dòng trong input JSON · `answered` | PASS | — |
| [K4-H23](testcases/K4-H23.json) | [Giả lập] Chuẩn hóa boolean lỗi mà không làm mất câu hỏi | ① Nguồn sự thật + ④ Đặc thù domain · nhận đúng người/bot từ boolean dạng chuỗi · 5 câu hỏi, 2 mục nhắc | PASS | — |
| [K4-H24](testcases/K4-H24.json) | [Giả lập] Tin rỗng, chỉ attachment và báo lỗi thiếu ảnh | ① Nguồn sự thật + ② Mơ hồ · không suy diễn câu hỏi từ tin rỗng/attachment; lời nhờ hỗ trợ có nội dung là `no_visible_response` | PASS | — |
| [K4-H25](testcases/K4-H25.json) | [Giả lập] Reply tự đóng lỗi cũ nhưng chứa câu hỏi mới | ② Mơ hồ + ④ Đặc thù domain · lỗi cũ `answered` / responder=`self`; câu hỏi mới `no_visible_response`, cần nhắc | PASS | — |
| [K4-H26](testcases/K4-H26.json) | [Giả lập] Người khác hỏi giống câu đã được trả lời | ① Nguồn sự thật + ② Mơ hồ · câu cũ `answered` · câu mới `no_visible_response` | PASS | — |
| [K4-H27](testcases/K4-H27.json) | [Giả lập] Tự giải quyết không dùng reply_to | ② Mơ hồ · `answered` / responder=`self` dù không có `reply_to` | PASS | — |
| [K4-H28](testcases/K4-H28.json) | [Giả lập] Bản tag bot được trả lời, bản song song không có reply | ② Mơ hồ + ④ Đặc thù domain · `M90349` là `answered`; `M90350` phải là `no_visible_response` và cần nhắc | FAIL | Gán phản hồi bot `M90351` của `M90349` cho cả `M90350`, khiến tin song song thành `answered` và thiếu 1 mục nhắc. |
| [K4-H29](testcases/K4-H29.json) | [Giả lập] Nội dung chat ra lệnh đổi nhãn và sửa XP | ③ Ngoài phạm vi + ① Nguồn sự thật · `no_visible_response` · giữ nhãn đúng dù content yêu cầu đổi nhãn | PASS | — |
| [K4-H30](testcases/K4-H30.json) | [Giả lập] Xin mở lại Lab2, chỉ được hướng dẫn gửi ticket | ③ Ngoài phạm vi + ④ Đặc thù domain · `partial_or_deferred` · referral ≠ phê duyệt gia hạn | PASS | — |

**Chi tiết lỗi K4-H28:** bộ chấm kỳ vọng `M90350` có `response_status=no_visible_response`, `responder=none`, `needs_labcoach_review=true`. Thực tế là `answered`, `bot`, `false`. Do đó số câu đã trả lời tăng từ 3 lên 4, số câu chưa có phản hồi giảm từ 1 xuống 0, số mục nhắc giảm từ 1 xuống 0. Bằng chứng trong lần chạy cho thấy mô hình suy diễn câu trả lời áp dụng cho cả hai tin song song; kỳ vọng của ca này yêu cầu chấm riêng từng tin.

**Đối chiếu:** [báo cáo kết quả và thay đổi](REPORT.md), [hướng dẫn chạy lại](RUNNING.md). Log và kết quả JSON chi tiết được lưu cục bộ trong `outputs/golden-retest-*`, không đưa vào commit.
