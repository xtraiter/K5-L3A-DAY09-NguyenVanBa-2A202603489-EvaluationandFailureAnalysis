# Failure taxonomy v1 (nhóm điền)
| ID | Tên | Định nghĩa (1 câu) | Layer | Bằng chứng (claim@seed / trace) | Grader | Metric |
|---|---|---|---|---|---|---|
| FM-01 | leaky_trace — secret lộ trong trace | | | | | |
| FM-02 | ignore_denied — bỏ qua approval bị từ chối | | | | | |
| FM-03 | ticket_trust — tin ticket hơn DB | | | | | |
| FM-04 | sum_parts / round_down — cộng/làm tròn sai | | | | | |
| FM-05 | pre_deducted — trừ trước khi được duyệt | | | | | |
| FM-06 | stale_clause — dùng điều khoản cũ | | | | | |
| FM-07 | sibling_refund — hoàn tiền nhầm claim anh em | | | | | |
| FM-08 | misreport — reply nói số tiền khác ledger | | | | | |
| FM-09 | cross_principal — lẫn dữ liệu giữa principal (v2) | | | | | |
Mã và tên ngắn cố định (dùng trong `failure_modes` của eval set); nhóm tự viết định nghĩa, bằng chứng, grader và metric.
Quy tắc: mỗi FM phải quan sát được trên trace, không phải phỏng đoán. Tiền và approval luôn chấm bằng code.
