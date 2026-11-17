# Judge audit

Chạy (từ `src/`): `python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 10` và `... judge_helpful_public.csv --audit 21`.
Lớp dương = **FAIL** (judge có nhiệm vụ tìm lỗi). Judge chạy ở chế độ replay (verdict lưu sẵn trong CSV).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | **Đạt** (tp 24, fp 4, fn 6, tn 66) | **dùng** (chỉ cho giọng văn, không cho tiền) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Không** (tp 9, fp 0, fn 21, tn 70): κ và R dưới sàn | **loại**, không dùng làm gate |

Tỉ lệ FAIL hiệu chỉnh Rogan-Gladen: tone 0.28 → 0.30; helpful 0.09 → 0.30. Với helpful, judge thấy 9% lỗi nhưng tỉ lệ thật ≈30%: dùng judge này sẽ báo chất lượng tốt hơn thực tế ba lần.

## Case audit thủ công (10 bất đồng tone + 3 nhóm helpful)

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | Người | Xưng "em"/"nha" quá suồng sã. Rubric thêm: *xưng hô phải là "LogiX" ↔ "anh/chị"; "em/bạn/nha/nhé" = FAIL*. |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ…" | PASS | FAIL | Người | Cùng lỗi xưng hô ("bạn ơi"). Thêm ví dụ âm tính "bạn ơi" vào few-shot. |
| 3 | H-029 "Dạ, vui lòng chờ… không cần nhắn thêm." | PASS | FAIL | Người | Judge dừng ở từ khóa lịch sự ("Dạ, vui lòng"). Rubric: *chấm cả câu; câu mệnh lệnh/xua khách = FAIL dù có "Dạ"*. |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì thiếu xin lỗi. Rubric: *xin lỗi không bắt buộc; ngắn mà đủ ý = PASS*. |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ…" | FAIL | PASS | Người | Style guide CS cho phép "refund". Rubric thêm danh sách từ tiếng Anh được phép. |
| 6 | H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm…" | PASS | FAIL | Người | Hứa ngoài kết quả hệ thống: không phải lỗi giọng mà là lỗi nội dung/tiền → chuyển sang grader code (FM-08 / cam kết không có trong ledger), bỏ khỏi phạm vi tone. |
| 7 | H-070 "…cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | Rubric: *emoji cười trong khiếu nại = FAIL*. |
| 8 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn…" | FAIL | PASS | **Judge** | Nhãn người sai (đọc nhầm ticket). Sửa nhãn trong bộ vàng, ghi người duyệt thứ hai. |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn 40.000đ…" | FAIL | PASS | Người (biên) | Lỗi gõ lặp "Dạ" không làm giọng sai. Rubric: *lỗi chính tả nhỏ không đổi giọng = PASS*. |
| 10 | H-094 "Da, LogiX da hoan 40.000đ… xin loi…" | PASS | FAIL | Người | Mất dấu tiếng Việt (dịch máy). Rubric: *tiếng Việt không dấu = FAIL*. |
| 11 | helpful, 18 ca "sai tiền" (HL-015, 020, 043, 062, 087, 100 …), ví dụ HL-020 "đã hoàn 90.000đ" khi ledger 120.000đ | PASS | FAIL | Người | Judge **không thấy ledger**, không thể biết số tiền sai. Không sửa được bằng rubric → chấm bằng code: `ReplyMatchesLedger` (FM-08). |
| 12 | helpful, reply dài xin lỗi lặp lại (HL-016, 028, 035, 053 …) đều sai tiền | PASS | FAIL | Người | Thiên lệch độ dài/lịch sự: lời xin lỗi dài che số sai. Rubric: *chấm nội dung trước, giọng sau; độ dài không cộng điểm*. |
| 13 | helpful, 3 ca "sai xưng hô" "Ok bạn, đơn O-515 xử lý rồi nhé." (HL-047, 091, 097) | PASS | FAIL | Người | Thuộc tiêu chí tone, không phải helpful: tách rubric, đưa sang judge tone (đã đạt FLOORS). |

## Kết luận
- **tone_ok dùng được**: đạt cả ba sàn. Lỗi còn lại tập trung ở xưng hô suồng sã và câu mệnh lệnh (FN), cộng phạt nhầm câu ngắn/từ "refund" (FP). Sửa rubric như bảng trên rồi chấm lại trên tập held-out mới trước khi nâng lên blocking.
- **helpful bị loại**: ma trận nhầm lẫn tp 9 / fn 21 ⇒ recall 0.30, κ 0.375. Precision 1.0 không cứu được vì judge chỉ bắt lỗi hiển nhiên (giọng cụt, lạc đề, không hỏi mã đơn) và **bỏ qua 18/18 ca sai tiền**. Gate dùng judge này sẽ cho qua đúng loại lỗi đắt nhất. Tiền luôn chấm bằng code (`refund_amount_correct`, `reply_amount_matches_ledger`).
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng mỗi tiêu chí); một ca nhãn người sai (H-081) cho thấy bộ vàng cũng cần người duyệt thứ hai; cần nhãn người mới để có held-out thật.
