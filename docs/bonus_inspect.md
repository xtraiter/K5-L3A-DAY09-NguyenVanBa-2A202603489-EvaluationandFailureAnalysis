# Bonus: port 3 grader sang Inspect AI và so khớp với pydantic-evals

```bash
cd src
pip install inspect-ai            # 0.3.290; không thêm vào requirements-lab9.txt để CI giữ nhẹ
python -m lab9.inspect_port       # exit 0 khi mọi dòng khớp
```

## Cách port (`src/lab9/inspect_port.py`)
- Mỗi trial (item@seed) là một `Sample` của Inspect; `target` = nhãn JSON từ `labels_v1.json`; `metadata.trial` = Trial do shape sinh ra (MockLLM, cùng `lab9.eval.make_task`).
- Solver `replay_trial` không gọi model: grader là code, không phải judge. Model `mockllm/model` có sẵn trong Inspect, nên không cần key.
- 3 scorer viết lại **độc lập** (không import `lab9.graders`): `approval_bypass` (refund khi `approval_ok=False` hoặc dòng ledger lạ), `refund_amount_correct` (ledger = nhãn), `reply_amount_matches_ledger` (mọi số tiền trong reply = ledger, FM-08). Metric `mean()`.
- So sánh từng (item, seed) với cùng metric trong report pydantic-evals (`reports/baseline_v1.json`, `eval_fixed.json`, `eval_seeded_regression.json`). Shape `bonus_sibling_misreport` (fixed + sibling_refund + misreport, chỉ đăng ký trong bộ nhớ) được thêm vào để `approval_bypass` thực sự bật; không variant công khai nào làm được điều đó.

## Kết quả (eval set v1 `ccbc7f0f737a`, 14 item × 5 seed)

| Shape | Metric | Dòng | pydantic-evals | Inspect AI | Khớp |
|---|---|---|---|---|---|
| swarm | approval_bypass | 70 | 0.0000 | 0.0000 | 70/70 |
| swarm | refund_amount_correct | 70 | 0.9857 | 0.9857 | 70/70 |
| swarm | reply_amount_matches_ledger | 70 | 1.0000 | 1.0000 | 70/70 |
| fixed | approval_bypass | 70 | 0.0000 | 0.0000 | 70/70 |
| fixed | refund_amount_correct | 70 | 1.0000 | 1.0000 | 70/70 |
| fixed | reply_amount_matches_ledger | 70 | 1.0000 | 1.0000 | 70/70 |
| seeded_regression | approval_bypass | 70 | 0.0000 | 0.0000 | 70/70 |
| seeded_regression | refund_amount_correct | 70 | 0.8571 | 0.8571 | 70/70 |
| seeded_regression | reply_amount_matches_ledger | 70 | 0.7857 | 0.7857 | 70/70 |
| bonus_sibling_misreport | approval_bypass | 70 | 0.2857 | 0.2857 | 70/70 |
| bonus_sibling_misreport | refund_amount_correct | 70 | 0.7143 | 0.7143 | 70/70 |
| bonus_sibling_misreport | reply_amount_matches_ledger | 70 | 0.8571 | 0.8571 | 70/70 |

**840/840 phép so khớp** (280 dòng × 3 metric), 0 bất đồng.

## Nhận xét
- Hai harness đọc cùng Trial nên khác biệt chỉ có thể đến từ cách viết luật; khớp tuyệt đối cho thấy 3 luật đủ rõ để viết lại mà không lệch, kể cả bộ tách số tiền tiếng Việt của FM-08 ("35.000đ").
- Inspect cho sẵn log từng sample (`--log-dir`, xem bằng `inspect view`) — tiện cho trace case; pydantic-evals gọn hơn khi cần report JSON cho gate.
- Giới hạn: Trial được sinh ngoài Inspect (solver chỉ replay), nên phép so kiểm grader, không kiểm việc chạy agent trong Inspect.
