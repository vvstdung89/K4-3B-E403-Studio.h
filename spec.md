# AI SPEC — Nhắc LabCoach câu hỏi chưa trả lời · Nhóm Studio.h · Zone E403
Hướng: [ ] A — VLearn  [x] B — Trợ lý Học viên  [ ] C — Làn mở
Loại: [ ] Tối ưu tính năng có sẵn  [x] Tính năng mới

> Canvas CP1 — xem đủ 7 dòng trong `canvas.md`.

## §1. User & Job
- Job executor + workflow: LabCoach, hàng ngày lúc rảnh, đang lướt Discord để kiểm tra còn câu hỏi học viên nào chưa có người trả lời.
- Core JTBD: Khi đang trực / lúc rảnh, LabCoach muốn biết câu hỏi nào của học viên vẫn chưa ai trả, để trả đúng người trước khi tin trôi.
- Problem statement (KHÔNG chữ AI): LabCoach phải tự lướt và tìm từng câu hỏi chưa được trả lời, việc này lặp lại mỗi ngày nên dễ sót tin và mất thời gian theo kịp kênh.
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

## §2. Impact & quyết định chọn
- Bảng impact ≥3 ứng viên:

  | Ứng viên | Ai gặp | Tần suất / quy mô | Mỗi lần tốn gì | Khả thi 39h | Chọn? |
  |---|---|---|---|---|---|
  | B2 · Nhắc LabCoach câu hỏi chưa trả lời | LabCoach (Tài, Tiến Minh xác nhận job) | **23/107 (21%)** tin `?` không có reply trong pack 3 ngày; bản tin ngày không list được câu tồn | Lướt tay, sót tin, HV chờ | Có — quét + phân loại + notify, không trả lời HV | **Có** |
  | B1 · Bot FAQ logistics có căn cứ (standup/XP/deadline) | HV tuần đầu | 58 tin người nói standup; bot TB 487 ký tự vs người 78 | HV hỏi lại / nhận deadline sai | Có, nhưng quyết định AI là trả lời HV — sai thì đắt | Không |
  | B1 · “Biết mình không biết” khi bot đoán chính sách | HV hỏi điểm/hạn nộp | Bot handoff chỉ 18/313 tin; vừa đoán vừa nhờ Mod | Thông tin sai đến HV | Trùng quyết định với FAQ, không tách sản phẩm | Không |

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
- Mức prototype nhắm tới: [ ] Sketch [ ] Mock [ ] Working — phần nào mock, phần nào thật:
- Automation: [ ] augment [x] conditional [ ] automate — *Tự:* quét tin, phát hiện câu chưa trả lời, nhắc LabCoach kèm link. *Không tự:* trả lời HV. *Lý do:* trả lời thay LabCoach thì thông tin sai đến HV (deadline/điểm) — đắt; sót câu thì LabCoach chịu, nên máy chỉ nhắc.
- §4b. Nguyên tắc đã áp dụng (≥4 — HAX/PAIR, xem guide):
  | Nguyên tắc | Áp cụ thể vào đâu trong prototype |
  |---|---|
  |  |  |

## §5. Kiểu lỗi — 4 lớp chỗ khó + kịch bản (≥8) [bảng theo guide §2.5]

| tình huống cụ thể | lớp | hành vi mong muốn | nguyên tắc |
|---|---|---|---|
|  |  |  |  |

## §6. Bốn đường đi của trải nghiệm
- Happy path: Câu hỏi được trả lời đầy đủ và có reply.
- Low-confidence (②): Câu hỏi không có từ nhận biết câu hỏi
- Failure/không căn cứ (①): 
- Correction (user sửa):
- Khi bị đòi ngoài phạm vi (③): LLM để phân loại, có guardrail nên nhóm không counter trường hợp này
- Case đặc thù domain (④): 

## §7. Kiểm thử
- Chiều chất lượng + định nghĩa kiểm chứng được:
- Golden set (≥20 case theo cơ cấu trong guide §2.6, file trong eval/):
- Quality bar (chốt từ hạn chốt spec của khoá, giữ nguyên sau đó): "Đạt khi ≥ ___% qua bộ, và ___"
- Kết quả các lượt chạy (bảng % — cập nhật đến trước CP6):

## §8. Phân công & kế hoạch
- Phân công có tên: Lương Sỹ Khánh — Discord integration + phát hiện tin · Văn Quốc Dũng — quản lý + QA · Nguyễn Đức Thịnh — backend/web + notification · Đào Quang Thái Anh — AI logic + LangGraph workflow.
- Willing users (≥2 tên): anh Tài (LabCoach), Tiến Minh (LabCoach). Kế hoạch validation: cho 2 LabCoach dùng thử danh sách câu tồn (R6 — cần thêm 1 người nếu làm đủ).
- Multi-prototype (nếu làm): trục khác biệt của ≥2 phương án + lý do chọn:

## §9. Changelog
| Thời điểm | Đổi gì | Vì sao (trỏ về feedback/case nào) |
|---|---|---|
|  |  |  |
