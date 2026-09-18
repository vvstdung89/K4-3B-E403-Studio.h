# AI SPEC — Nhắc LabCoach câu hỏi chưa trả lời · Nhóm Studio.h · Zone E403

Hướng: [ ] A — VLearn  [x] B — Trợ lý Học viên  [ ] C — Làn mở
Loại: [ ] Tối ưu tính năng có sẵn  [x] Tính năng mới

> Canvas CP1 — xem đủ 7 dòng trong `canvas.md`.

## §1. User &amp; Job

- Job executor + workflow: LabCoach, hàng ngày lúc rảnh, đang lướt Discord để kiểm tra còn câu hỏi học viên nào chưa có người trả lời.
- Core JTBD: Khi đang trực / lúc rảnh, LabCoach muốn biết câu hỏi nào của học viên vẫn chưa ai trả, để trả đúng người trước khi tin trôi.
- Problem statement (KHÔNG chữ AI): LabCoach phải tự lướt và tìm những câu hỏi chưa được trả lời, việc này lặp lại mỗi ngày nên dễ sót tin và mất thời gian theo kịp kênh. Ngoài ra việc này lập đi lập lại cho các thành viên labcoach (bị trùng việc đọc tin nhắn cũ), nên khá tốn thời gian chung. 
- Evidence (chuẩn B + phỏng vấn 2 LabCoach — log đầy đủ bổ sung trong repo):
  - Số liệu mining `data/discord-pack/k4_messages.csv`: tin người (`is_bot=False`) có dấu `?` = **107**; không có tin nào `reply_to` trỏ vào = **23/107 (21%)**. *Cách đếm:* lọc câu có `?`, đối chiếu tập `reply_to`.
  - Phỏng vấn LabCoach: anh Tài, Tiến Minh (n = 2) — xác nhận phải thường xuyên lướt Discord để tìm câu chưa trả lời.
  - Baseline bản tin bot `k4_daily_reports.md`: 2/4 bản cắt cụt giữa câu; nhiều dòng ghi “Đã có phản hồi, chưa xác nhận đã xử lý” — không dùng được để biết câu nào còn tồn.
  - ≥5 quote/ví dụ nguyên văn + nguồn:
    1. `M88027` — “cho em hỏi Lab2 có được extend thời gian submit thêm không v ạ? Em lỡ nộp muộn 1 phút không submit bài được ạ” (không reply).
    2. `M42852` — “Cú pháp của lệnh bot để thực hiện daily standup?” (không reply).
    3. `M60122` — “cho mình hỏi cái daily-standup này làm ở đâu vậy nhỉ, làm thế nào” (không reply).
    4. `k4_daily_reports.md` K4-L2-3 · 13/09 — bản tin cắt cụt: “Một số câu hỏi chưa được giải đá”.
    5. `k4_daily_reports.md` K4-L3-4 · 14/09 — “Đã có phản hồi, chưa xác nhận đã xử lý” / “Phản hồi tự động chưa phải hướng dẫn chính thức.”

## §2. Impact &amp; quyết định chọn

- Bảng impact ≥3 ứng viên:

  | Ứng viên                                               | Ai gặp                                 | Tần suất / quy mô                                                                               | Mỗi lần tốn gì                 | Khả thi 39h                                         | Chọn?  |
  | ------------------------------------------------------ | -------------------------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------ | --------------------------------------------------- | ------ |
  | B2 · Nhắc LabCoach câu hỏi chưa trả lời                | LabCoach (Tài, Tiến Minh xác nhận job) | **23/107 (21%)** tin `?` không có reply trong pack 3 ngày; bản tin ngày không list được câu tồn | Lướt tay, sót tin, HV chờ      | Có — quét + phân loại + notify, không trả lời HV    | **Có** |
  | B1 · Bot FAQ logistics có căn cứ (standup/XP/deadline) | HV tuần đầu                            | 58 tin người nói standup; bot TB 487 ký tự vs người 78                                          | HV hỏi lại / nhận deadline sai | Có, nhưng quyết định AI là trả lời HV — sai thì đắt | Không  |
  | B1 · “Biết mình không biết” khi bot đoán chính sách    | HV hỏi điểm/hạn nộp                    | Bot handoff chỉ 18/313 tin; vừa đoán vừa nhờ Mod                                                | Thông tin sai đến HV           | Trùng quyết định với FAQ, không tách sản phẩm       | Không  |

- Ứng viên ĐÃ LOẠI: B1 FAQ có căn cứ — pain HV thật nhưng cost-of-error cao (bot trả lời thay người). B1 know-when-not-to-know — là lớp chỗ khó của FAQ, không phải lát cắt riêng.
- Ứng viên CHỌN: **B2 nhắc LabCoach** — có số 21% câu `?` không reply, bản tin hiện tại không dùng được, 2 LabCoach xác nhận job; AI chỉ nhắc kèm link, người mới trả lời nên sai thì rẻ hơn trả lời thay HV.

## §3. Giải pháp tương tự đã nghiên cứu

- **[Giải pháp tương tự · Bot tự động phân loại Discord của một nhóm khác]**:
  - **Flow:** Phân tích các tin nhắn trên kênh Discord để xác định câu hỏi chưa được giải đáp, tổng hợp câu hỏi cuối ngày và phân priority.
  - **Đáng học:** Phân chia Priority cho các câu hỏi(Không quan trọng - Khẩn cấp) và thông tin sớm hay muộn dựa vào đó.
  - **Đáng né:** Bộ testcase chưa xử lý nhiều tin nhắn cùng lúc. Việc tìm câu trả lời cho một câu hỏi rất phức tạp (*tricky*) giữa các mức độ: `answered` (đầy đủ), `partial_or_deferred` (một phần / hẹn sau), và `no_visible_response` (chưa có phản hồi), dẫn đến nguy cơ tốn kém chi phí nếu gọi xử lý lặp lại từng tin.
  - **Mình khác gì:** Tập trung phân tích trạng thái câu hỏi trên luồng hội thoại đa tin nhắn và tối ưu chi phí xử lý ngữ cảnh thay vì phân loại rời rạc từng tin đơn lẻ.

## §4. Thiết kế

- Lát cắt MỘT CÂU: Một LabCoach lúc rảnh · cần biết câu hỏi học viên nào còn chưa được trả lời · AI quyết định tin nào là câu hỏi còn tồn và cần nhắc · LabCoach nhận danh sách ngắn kèm link tin, đỡ phải lướt tay và hạn chế bỏ sót.
- Non-goals (≥3 thứ KHÔNG build):
  1. Không tự trả lời học viên.
  2. Không suy diễn / chốt đáp án (deadline, điểm, chính sách).
  3. Không gửi tin chủ động cho học viên khi chưa có LabCoach duyệt.
- Mức prototype nhắm tới: [ ] Sketch [x ] Mock [x ] Working — phần nào mock, phần nào thật:
  - Data input được mock vào để test
  - Bot discord thật verify luồng notify Labcoach
- Automation: [ ] augment [] conditional [x] automate — *Tự:* quét tin, phát hiện câu chưa trả lời, nhắc LabCoach kèm link. *Không tự:* trả lời HV. *Lý do:* trả lời thay LabCoach thì thông tin sai đến HV (deadline/điểm) — đắt; sót câu thì LabCoach chịu, nên máy chỉ nhắc.
- §4b. Nguyên tắc đã áp dụng (≥4 — HAX/PAIR, xem guide):

  Luồng prototype: bot quét tin nhắn Discord → gọi LLM để xác định câu hỏi cần nhắc → gửi thông báo cho LabCoach tại một kênh riêng. LabCoach đọc lại ngữ cảnh và trực tiếp trả lời học viên.

  | Nguyên tắc                                                                        | Áp cụ thể vào đâu trong prototype                                                                                                                                                                                                                                   | Vị trí và cách kiểm tra                                                                                                                                                                                                                                                                                                                                                   |
  | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
  | **HAX G1 — Làm rõ hệ thống làm được gì**                                          | Lệnh `/labcoach-check` mô tả chức năng kiểm tra câu hỏi chưa được trả lời; thẻ thông báo có tiêu đề “Câu hỏi chưa được phản hồi”. Bot hỗ trợ phát hiện và nhắc việc; việc giải đáp do LabCoach thực hiện.                                                           | [Lệnh kiểm tra](codebase/bot_gateway.py), [thẻ thông báo](codebase/notify/formatter.py). Chạy lệnh và kiểm tra kết quả là danh sách câu cần xem xét, không phải câu trả lời tự động cho học viên.                                                                                                                                                                         |
  | **HAX G3 — Đưa dịch vụ đúng thời điểm**                                           | Bộ lọc chỉ đưa tin vào diện xem xét khi đã chờ ít nhất **4 giờ**, tránh nhắc ngay lúc học viên vừa hỏi. Thẻ thông báo hiển thị thời gian chờ và ngưỡng nhắc để LabCoach biết lý do tin xuất hiện lúc này.                                                           | [Bộ lọc thời gian](codebase/detect/rules.py), [footer thông báo](codebase/notify/formatter.py). Với cùng một câu hỏi chưa có phản hồi, kiểm tra trước và tại mốc 4 giờ: trước mốc chưa tạo ứng viên, đến mốc mới xét.                                                                                                                                                     |
  | **HAX G4 — Hiện thông tin đúng ngữ cảnh**                                         | Mỗi thẻ nhắc hiển thị câu hỏi, trích đoạn nội dung, kênh/server nguồn, thời điểm đăng và thời gian chờ. LabCoach có ngữ cảnh ban đầu để tìm lại hội thoại và quyết định hỗ trợ.                                                                                     | [Các trường của thẻ thông báo](codebase/notify/formatter.py). Đối chiếu thẻ với tin đầu vào, kiểm tra đúng nội dung, nguồn và thời gian; hiện thẻ mới hiển thị nguồn dạng văn bản, chưa có deep link tới tin gốc.                                                                                                                                                         |
  | **HAX G5 — Hợp chuẩn mực xã hội**                                                 | Luồng notify gửi vào kênh riêng dành cho LabCoach, tránh đưa danh sách cần hỗ trợ vào kênh trò chuyện chung. Trường “Học viên” trên thẻ dùng nhãn ẩn danh, không hiển thị trực tiếp mã `author`.                                                                    | [Đích webhook](codebase/run_live.py), [trường Học viên](codebase/notify/formatter.py). Cấu hình `DISCORD_WEBHOOK_URL` của kênh LabCoach, gửi thử dữ liệu mô phỏng và kiểm tra đúng kênh nhận, đúng nhãn ẩn danh.                                                                                                                                                          |
  | **HAX G8 — Gạt bỏ dễ dàng**                                                       | Thông báo là gợi ý để LabCoach xem xét. Nếu câu đã được xử lý hoặc bot nhận nhầm, LabCoach có thể bỏ qua và tiếp tục làm việc trên Discord; không phải xác nhận để mở khóa luồng trả lời. Việc bỏ qua chưa được lưu thành phản hồi huấn luyện hay trạng thái xử lý. | [Luồng gửi thông báo](codebase/notify/discord_client.py). Trong demo, bỏ qua một thẻ rồi tiếp tục đọc/trả lời hội thoại; bot không yêu cầu thao tác xác nhận.                                                                                                                                                                                                             |
  | **HAX G10 — Thu hẹp phạm vi khi nghi ngờ; PAIR — Errors &amp; graceful failures** | Khi lời gọi LLM lỗi hoặc thiếu kết quả cho một ứng viên, hệ thống giữ ứng viên để LabCoach kiểm tra thủ công, thay vì tự kết luận đã giải quyết. AI chỉ phân loại, không tự quyết định deadline, điểm hay chính sách.                                               | [Fallback quyết định](codebase/ai_decide/stub.py), [xử lý thiếu kết quả và prompt giới hạn phạm vi](codebase/ai_decide/graph.py). Mô phỏng lỗi API hoặc thiếu một kết quả: ứng viên vẫn có `still_needs_attention=True`; lý do fallback nằm trong kết quả nội bộ/báo cáo chữ. Thẻ Discord hiện chưa hiển thị lý do này và chưa có ngưỡng xử lý riêng cho confidence thấp. |


  Tham chiếu: [HAX Guidelines](further-reading/hax-guidelines.md) và [PAIR Guidebook, chương 6](further-reading/pair-guidebook-digest.md). Các bước kiểm tra trên dành cho luồng prototype; điểm benchmark của bộ phân loại riêng không thay thế kiểm thử notify trên Discord.

## §5. Kiểu lỗi — 4 lớp chỗ khó + kịch bản (≥8) [bảng theo guide §2.5]

Nguồn: [bảng testcase](eval/golden_set.md) và nhãn kỳ vọng trong [30 ca golden set](eval/golden_set/). Bảng dưới mô tả hành vi mong muốn; kết quả thực tế được ghi riêng trong [báo cáo kiểm thử](eval/REPORT.md). Các nguyên tắc tham chiếu [HAX](further-reading/hax-guidelines.md).


| Tình huống cụ thể                                                                                                                                     | Lớp                                            | Hành vi mong muốn                                                                                                                                                      | Nguyên tắc                                                                   |
| ----------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Học viên hỏi cách làm daily-standup hoặc báo lỗi Zoom, chưa có phản hồi — [K4-01](eval/golden_set/K4-01.json), [K4-H14](eval/golden_set/K4-H14.json). | ① Nguồn sự thật                                | Gán `no_visible_response`; đưa vào danh sách nhắc kèm tin gốc và lý do “chưa thấy phản hồi trong cửa sổ hội thoại”.                                                    | G10 — giới hạn kết luận theo dữ liệu thấy được; G11 — nêu căn cứ.            |
| Bot trả lời dài nhưng thiếu hạn nộp cụ thể, hoặc reply lạc đề — [K4-03](eval/golden_set/K4-03.json), [K4-H19](eval/golden_set/K4-H19.json).           | ① Nguồn sự thật                                | Gán `partial_or_deferred`; chỉ rõ phần chưa được giải đáp để LabCoach xử lý, giữ trong danh sách nhắc.                                                                 | G10 — không suy diễn đáp án thiếu; G11 — giải thích phần còn tồn.            |
| Một tin hỏi hai ý, chỉ một ý được trả lời — [K4-05](eval/golden_set/K4-05.json), [K4-H17](eval/golden_set/K4-H17.json).                               | ② Mơ hồ / thiếu thông tin; ④ Đặc thù domain    | Giữ từng ý hỏi; gán `partial_or_deferred` và nêu ý còn thiếu trong mục nhắc.                                                                                           | G4 — bám đúng yêu cầu; G11 — giải thích lý do nhắc.                          |
| Có lời hẹn trả lời nhưng không dùng `reply_to` — [K4-06](eval/golden_set/K4-06.json).                                                                 | ② Mơ hồ / thiếu thông tin                      | Nhận diện phản hồi qua ngữ cảnh; gán `partial_or_deferred`, dẫn tin hẹn trả lời và tiếp tục nhắc.                                                                      | G4 — xét ngữ cảnh hội thoại; G10 — chưa đóng câu hỏi khi mới hẹn.            |
| Ban đầu bot/người hẹn hỗ trợ, sau đó có đáp án đầy đủ — [K4-H15](eval/golden_set/K4-H15.json), [K4-H16](eval/golden_set/K4-H16.json).                 | ① Nguồn sự thật                                | Trước đáp án: `partial_or_deferred`; sau đáp án: `answered`, bỏ khỏi danh sách nhắc và dẫn phản hồi đã giải đáp.                                                       | G12 — giữ ngữ cảnh gần; G11 — cập nhật căn cứ kết luận.                      |
| Cùng học viên hỏi lặp một vấn đề chưa giải quyết — [K4-08](eval/golden_set/K4-08.json), [K4-H18](eval/golden_set/K4-H18.json).                        | ② Mơ hồ / thiếu thông tin; ④ Đặc thù domain    | Giữ từng tin khi đếm câu hỏi. Theo `per_issue`, gom cùng vấn đề vào một mục nhắc; theo `per_message`, giữ riêng từng mục. Hiện đủ tin thuộc nhóm để LabCoach kiểm tra. | G4 — gom đúng người và vấn đề; G11 — làm rõ thành viên nhóm nhắc.            |
| Hỏi giấy chứng nhận sinh viên, chưa có người có thẩm quyền trả lời — [K4-02](eval/golden_set/K4-02.json).                                             | ③ Ngoài phạm vi / thẩm quyền; ① Nguồn sự thật  | Gán `no_visible_response`, chuyển vào danh sách LabCoach xem xét; hệ thống chỉ phân loại, không tự xác nhận thủ tục hay quyền cấp giấy.                                | G1 — làm rõ phạm vi; G10 — giới hạn theo thẩm quyền.                         |
| Xin gia hạn hoặc mở lại Lab2, mới được hướng dẫn gửi ticket — [K4-10](eval/golden_set/K4-10.json), [K4-H30](eval/golden_set/K4-H30.json).             | ③ Ngoài phạm vi / thẩm quyền; ④ Đặc thù domain | Gán `partial_or_deferred`; nhắc rõ yêu cầu phê duyệt còn tồn, kèm phản hồi hướng dẫn ticket.                                                                           | G1 — phân loại không thay cho phê duyệt; G10 — chưa suy ra đã được gia hạn.  |
| Nội dung chat yêu cầu đổi nhãn phân loại hoặc sửa XP — [K4-H29](eval/golden_set/K4-H29.json).                                                         | ③ Ngoài phạm vi / thẩm quyền; ① Nguồn sự thật  | Coi chỉ thị trong chat là dữ liệu; giữ yêu cầu hỗ trợ ở `no_visible_response` và chuyển LabCoach xem xét. Không thực hiện thay đổi XP.                                 | G1 — giữ phạm vi chức năng; G10 — không làm theo chỉ thị vượt quyền.         |
| Bot đã trả lời đủ về mentor-duty hoặc yêu cầu được tag — [K4-09](eval/golden_set/K4-09.json), [K4-H12](eval/golden_set/K4-H12.json).                  | ④ Đặc thù domain                               | Gán câu hỏi `answered`, bỏ khỏi danh sách nhắc; phản hồi bot là bằng chứng, không được đếm thành câu hỏi của học viên.                                                 | G4 — phân biệt vai trò người hỏi/người trả lời; G11 — dẫn bằng chứng.        |
| Hai tin trùng `msg_id` ở hai kênh, chỉ một tin được trả lời — [K4-H21](eval/golden_set/K4-H21.json).                                                  | ④ Đặc thù domain; ② Mơ hồ / thiếu thông tin    | Phân biệt theo `input_index`, guild và channel; một tin `answered`, tin còn lại `no_visible_response` và vẫn cần nhắc.                                                 | G4 — đúng ngữ cảnh kênh; G11 — bằng chứng gắn đúng tin.                      |
| Hai bản hỏi song song, bot chỉ reply bản có tag — [K4-H28](eval/golden_set/K4-H28.json).                                                              | ② Mơ hồ / thiếu thông tin; ④ Đặc thù domain    | `M90349` là `answered`; giữ `M90350` ở `no_visible_response` và nhắc LabCoach theo kỳ vọng chấm riêng từng tin.                                                        | G10 — không tự mở rộng phạm vi phản hồi; G11 — kiểm tra liên kết bằng chứng. |
| Hỏi được dùng email cá nhân **hoặc** cách sửa lỗi Zoom; đã được xác nhận dùng email cá nhân — [K4-10, M27034](eval/golden_set/K4-10.json).            | ④ Đặc thù domain                               | Gán `answered` và bỏ mục nhắc: một phương án được chấp nhận đã đáp ứng câu hỏi lựa chọn.                                                                               | G4 — hiểu đúng quan hệ “hoặc”; G11 — nêu phương án đã được giải đáp.         |
| Nhờ hỗ trợ vì không vào được Phoenix, đã được hướng dẫn tạo ticket — [K4-08, M84662](eval/golden_set/K4-08.json).                                     | ④ Đặc thù domain                               | Gán `answered` theo kỳ vọng của ca và bỏ mục nhắc; giải thích rằng phản hồi đã cung cấp bước hỗ trợ tiếp theo.                                                         | G2 — làm rõ ý nghĩa trạng thái; G11 — dẫn hướng dẫn đã nhận.                 |


Lượt chạy gần nhất còn sai ở **K4-08/M84662**, **K4-10/M27034** và **K4-H28/M90350**; các hành vi kỳ vọng tương ứng ở trên chưa đạt ổn định. Bốn lớp đều có ít nhất hai testcase đối chiếu.

## §6. Bốn đường đi của trải nghiệm

- **Happy path:** Có câu hỏi chưa được trả lời sau 4 giờ → bot quét tin, gọi LLM xác định câu cần nhắc → gửi thông báo vào kênh riêng của LabCoach. LabCoach đọc lại hội thoại và trả lời học viên.
- **Low-confidence (②):** Câu hỏi thiếu ngữ cảnh hoặc mới được trả lời một phần → cần giữ lại để LabCoach kiểm tra. LabCoach hỏi thêm học viên nếu cần, AI không tự đoán vấn đề đã giải quyết.
- **Failure/không căn cứ (①):** Thiếu tin nhắn liên quan thì AI chỉ kết luận theo dữ liệu đang có. Nếu gọi LLM lỗi, hệ thống giữ câu hỏi cho LabCoach kiểm tra thủ công.
- **Correction (user sửa):** Nếu bot nhắc nhầm, LabCoach kiểm tra hội thoại và bỏ qua thông báo. Hiện chưa có nút sửa nhãn hoặc lưu feedback; phần này đang xử lý thủ công.
- **Ngoài phạm vi (③):** Bot không cộng XP, duyệt gia hạn hay làm theo lệnh nhúng trong tin nhắn. Bot chỉ phân loại và nhắc LabCoach; quyết định thuộc về người có thẩm quyền.
- **Đặc thù Discord (④):** Có reply chưa chắc đã trả lời đúng; không có reply vẫn có thể đã được giải đáp trong hội thoại. Mục tiêu là xét nội dung và đúng người hỏi, tránh nhắc trùng hoặc bỏ sót câu còn tồn.

**Phần còn thiếu:** Luồng live vẫn lọc theo dấu `?` và `reply_to`, nên có thể bỏ sót trước bước LLM. Thẻ Discord chưa có nhãn độ tin cậy, lý do fallback hay link tin gốc; bước gửi embed chưa lọc câu AI đánh dấu đã giải quyết. Các luồng trên cần được kiểm thử trực tiếp trên bot, ngoài benchmark phân loại.

## §7. Kiểm thử

- **Dataset:** [30 case](eval/golden_set.md) — 10 thực, 20 giả lập, phủ 4 lớp lỗi.
- **Metric:** case pass khi nhãn, trạng thái, người phản hồi, số lượng và nhóm nhắc khớp expected output.
- **Run 18/09:** `gpt-5.4`, reasoning `medium`; pass rate **27/30 (90%)**. Checkpoint **4/4**, unit test **20/20**.
- **Offline hiện tại:** **26/26**, gồm 6 test bổ sung cho luồng live batch với LLM giả lập; chưa xác nhận gửi Discord thực tế.
- **Failure:** K4-08 — hiểu sai chuyển ticket; K4-10 — hiểu sai câu hỏi “hoặc”; K4-H28 — gán nhầm phản hồi. [Chi tiết](eval/REPORT.md).
- **Quality gate:** chưa chốt ngưỡng nghiệm thu; còn 3 case fail.

## §8. Phân công &amp; kế hoạch

- Phân công có tên: Lương Sỹ Khánh — Discord integration + phát hiện tin · Văn Quốc Dũng — quản lý + QA · Nguyễn Đức Thịnh — backend/web + notification · Đào Quang Thái Anh — AI logic + LangGraph workflow.
- Willing users (≥2 tên): anh Tài (LabCoach), Tiến Minh (LabCoach). Kế hoạch validation: cho 2 LabCoach dùng thử danh sách câu tồn (R6 — cần thêm 1 người nếu làm đủ).
- Multi-prototype (nếu làm): trục khác biệt của ≥2 phương án + lý do chọn:

## §9. Changelog

Các mốc chức năng theo lịch sử Git đến `0b6206d`; thời gian UTC+7.


| Thời điểm                               | Đổi gì                                                                                                                                                    | Vì sao (trỏ về feedback/case nào)                                                                                                                                                                                              |
| --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 17/09/2026 19:36 · `8bf8cb3`            | Chốt B2: nhắc LabCoach câu hỏi chưa trả lời; bổ sung Canvas, bằng chứng và so sánh ba hướng giải pháp.                                                    | Mining ghi nhận 23/107 câu có dấu `?` không có reply; `M88027`, `M42852`, `M60122` minh họa nhu cầu. Chọn hỗ trợ LabCoach, giữ quyền trả lời cho người.                                                                        |
| 17/09/2026 20:39 · `4d9264e`            | Thêm pipeline mẫu: đọc CSV → lọc câu hỏi chưa có reply, đã chờ ít nhất 4 giờ → AI stub → in bản tin.                                                      | Tạo luồng chạy được để kiểm tra phát hiện câu tồn trước khi tích hợp AI và Discord thật.                                                                                                                                       |
| 17/09/2026 20:57 · `17feaa4`            | Cập nhật sơ đồ workflow CP2 thành `outputs/workflow.jpg`.                                                                                                 | Làm rõ luồng quét tin, chọn câu cần nhắc và hiển thị bản tin; commit này cập nhật sơ đồ.                                                                                                                                       |
| 17/09/2026 23:03 · `07030c1`            | Thêm gửi bản tin qua Discord webhook bằng `--send-to-discord`, chia nội dung theo giới hạn 2.000 ký tự.                                                   | Chuyển bản tin từ terminal tới nơi LabCoach làm việc; xử lý giới hạn độ dài tin Discord.                                                                                                                                       |
| 18/09/2026 09:16 · `595721c`            | Mô phỏng nhịp cron 30 phút, chống nhắc lặp và đổi bản tin sang embed; thêm User-Agent cho webhook.                                                        | Kiểm tra ngưỡng chờ 4 giờ và định dạng theo workflow; khắc phục lỗi HTTP 403 gặp khi kiểm tra webhook.                                                                                                                         |
| 18/09/2026 09:53 · `abc6957`            | Thêm đọc tin Discord qua Bot REST API và `run_live.py`; lấy cửa sổ 6 giờ, lưu ID đã báo giữa các lần chạy.                                                | Đưa dữ liệu thực vào cùng pipeline; tránh bỏ sót câu vừa vượt ngưỡng 4 giờ và gửi lại câu đã báo.                                                                                                                              |
| 18/09/2026 11:00 · `61e7c95`, `8220976` | Thêm chế độ CSV cho `run_live.py`, lệnh `/labcoach-check`, `/labcoach-demo` và cấu hình worker Render.                                                    | Cho phép kiểm tra bằng dữ liệu mẫu khi chưa có quyền vào server đích và gọi demo trực tiếp; trạng thái chống trùng của lượt thử tách khỏi lượt chạy thực.                                                                      |
| 18/09/2026 11:47 · `87dc01b`            | Tích hợp LangGraph, factory nhiều nhà cung cấp model và log lời gọi AI; khi gọi AI lỗi, giữ câu hỏi cho LabCoach xem xét.                                 | Thay AI stub bằng phân tích ngữ cảnh phản hồi, đồng thời giữ đường xử lý khi model/API không trả kết quả.                                                                                                                      |
| 18/09/2026 11:56 · `45df3d1`            | Thêm tùy chọn xem riêng cho `/labcoach-demo` và lệnh xem CSV luôn ở chế độ ephemeral.                                                                     | Người demo xem trước kết quả; dữ liệu CSV chỉ hiện cho người gọi lệnh.                                                                                                                                                         |
| 18/09/2026 15:23 · `0d52ff9`            | Thêm 30 testcase, formatter phân loại và benchmark runner; đặt Gemini làm mặc định trong decision graph.                                                  | Đối chiếu nhãn, trạng thái phản hồi và số lượng với kỳ vọng trong `eval/testcases/`, thay vì chỉ quan sát bản tin thủ công.                                                                                                    |
| 18/09/2026 19:30 · `0b6206d`            | Đưa đủ 30 ca gốc vào golden set; tách nhận diện câu hỏi và xác định trạng thái, thêm bằng chứng, quy tắc gom nhắc và hỗ trợ GPT-5; sửa chấm tin trùng ID. | K4-05/06 kiểm tra ý hỏi còn thiếu, K4-08 kiểm tra gom nhắc, K4-H21 kiểm tra trùng ID. Chạy lại đạt **27/30**, còn lỗi **K4-08, K4-10, K4-H28**; **4/4 checkpoint**, **20/20 test offline** đạt. Xem [báo cáo](eval/REPORT.md). |
