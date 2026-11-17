# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-008 --seed 11
python -m lab9.trace_case --shape fixed --claim C-008 --seed 11   # đối chứng
```

## Case: `seeded_regression C-008@11` — reply nói 35.000đ, ledger ghi 20.000đ (FM-08)

Trace (rút gọn từ lệnh trên):
```
== seeded_regression C-008@11  lab8 grader: PASS (ok)
   1 handoff        {"request_id": "REQ-C-008", "task": "check_applicable_policy", ...}
   2 investigator   {"lookup_order": {"visible": true, "order": {"order_id": "O-808", "status": "delivered_late", ...}}}
   3 quote          {"amount_vnd": 35000, "reason": "entitled", "clause_ids": ["SHIP-LATE-03"], ...}
   4 refund_history {"refund_count": 0, "refunded_vnd": 0}
   5 reply          {"text": "Dạ, LogiX đã hoàn 35.000đ cho đơn O-808."}
-- ledger vs label
  refund_vnd     ledger=20000    label=20000
  refund_count   ledger=1        label=1
  status         result=resolved label=resolved
```

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-008@11` (item E-008), report `reports/eval_seeded_regression.json`, run ID `E-seeded_regression-20261117-ccbc` (eval set `ccbc7f0f737a`) |
| Triệu chứng | `reply_amount_matches_ledger` = False ("reply says [35000] but ledger holds 20000"). Reply nói **35.000đ**, ledger ghi **20.000đ** (host áp trần cho O-808). Mọi grader khác, kể cả `pass_rate` (grader Lab 8), đều PASS. |
| Bước sai đầu tiên | **#5 `reply`** — `"Dạ, LogiX đã hoàn 35.000đ cho đơn O-808."` |
| Vì sao là bước *đầu tiên* | #2 investigator đọc đúng đơn O-808 từ DB; #3 quote 35.000 = nhãn `proposal_amount` 35.000; #4 refund_history đọc đúng (chưa hoàn lần nào, nên bước tự trừ của `pre_deducted` không đổi số). Host ghi 20.000 = nhãn `refund_vnd`. Bước duy nhất lệch so với sự thật là #5: agent báo số **nó đề xuất** thay vì số **host đã ghi**. |
| Failure mode | **FM-08 misreport** (`docs/failure_taxonomy.md`). Nguyên nhân trong variant: công tắc `pre_deducted` làm agent báo `proposal` thay cho `committed`. |
| Đối chứng | `fixed C-008@11`: cùng #1–#3, không có #4 refund_history; **#4 `reply` "đã hoàn 20.000đ"** = ledger 20.000. Khác biệt duy nhất nằm ở số trong reply. |
| Regression test | `src/tests/test_lab9_trace_case.py`: `test_lab9_trace_case_fm08_caught_on_seeded_regression` (ledger 20.000 đúng, `TrialPass` = True, `ReplyMatchesLedger` = False) và `test_lab9_trace_case_fm08_clean_on_fixed` (cả hai True). Đã chạy: fail đúng trên variant lỗi, pass trên `fixed` (`pytest -m student -k "lab9 and not advanced"` → 13 passed). Ở mức eval set, metric blocking `reply_amount_matches_ledger` (min 1.0) chặn `seeded_regression`: 0.7857, Δ −0.214. |
| Chưa chắc chắn | Trace không ghi event của host (`issue_refund` trả về 20.000), nên lý do trần 20.000 chỉ suy ra từ ledger và nhãn, không thấy trực tiếp trong trace. Shape `swarm` của Lab 8 không phát event `reply`, nên metric này chỉ có tác dụng với shape có reply; reply không nêu số tiền thì grader cho qua (không kiểm được status "đã hoàn" mà không có số). |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai, và ở case này thì ngược lại: ledger đúng nhưng reply sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
