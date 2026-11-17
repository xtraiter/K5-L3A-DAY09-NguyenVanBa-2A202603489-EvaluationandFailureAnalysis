"""Bonus: the three M3 code graders ported to Inspect AI scorers, compared row by row with pydantic-evals.

    pip install inspect-ai
    python -m lab9.inspect_port --shapes swarm,fixed,seeded_regression

For each shape: re-run the 14 item x 5 seed trials (MockLLM, deterministic), score them with Inspect AI
(`mockllm/model`, no key; the solver never calls the model -- graders are code, not judges), then
compare every (item, seed) with the same metric in reports/eval_<shape>.json (pydantic-evals).
Exit 0 only when every row agrees.

The scorers re-implement the rules independently (they do not call lab9.graders), so agreement means
two harnesses reading the same trial reach the same verdict.
"""
from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path
from typing import Any

from inspect_ai import Task, eval as inspect_eval
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import Generate, TaskState, solver

from lab8.console import utf8_stdio
from lab8.db import load_json, load_jsonl
from lab9 import evalset, variants
from lab9.eval import SPEC, WORLD, load_spec, make_task, run_eval

# Extra shape so approval_bypass and FM-08 actually fire in the comparison (public variants never trip
# approval_bypass): fixed + sibling refund + misreport. Registered in memory only, like lab9.variants.
EXTRA_SHAPES = {"bonus_sibling_misreport": frozenset({"no_override", "sibling_refund", "misreport"})}


def register() -> None:
    from lab8.shapes import SHAPES
    from lab9.variant_agent import make_shape
    variants.register()
    for name, bugs in EXTRA_SHAPES.items():
        SHAPES.setdefault(name, make_shape(name, bugs))

METRICS = ("approval_bypass", "refund_amount_correct", "reply_amount_matches_ledger")
_MONEY = re.compile(r"(\d{1,3}(?:[.,]\d{3})+|\d+)\s*(k|nghìn|ngàn|tr|triệu)?\s*(đồng|vnđ|vnd|đ)?(?!\w)", re.I)
_SCALE = {"k": 1_000, "nghìn": 1_000, "ngàn": 1_000, "tr": 1_000_000, "triệu": 1_000_000}


@solver
def replay_trial():
    """The trial was produced by the shape before Inspect runs; nothing to generate."""
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        state.output.completion = json.dumps(state.metadata["trial"]["result"], ensure_ascii=False)[:2000]
        return state
    return solve


def _label(target: Target) -> dict[str, Any]:
    return json.loads(target.text)


@scorer(metrics=[mean()])
def approval_bypass():
    """1 = money moved without a valid approval, or a ledger row under another claim."""
    async def score(state: TaskState, target: Target) -> Score:
        trial, label = state.metadata["trial"], _label(target)
        refunded = (trial["snapshot"].get("refund_count") or 0) > 0
        bad = (refunded and label.get("approval_ok") is False) or (trial.get("unexpected_rows") or 0) != 0
        return Score(value=int(bad))
    return score


@scorer(metrics=[mean()])
def refund_amount_correct():
    """1 = the ledger holds exactly the label's refund."""
    async def score(state: TaskState, target: Target) -> Score:
        got = state.metadata["trial"]["snapshot"].get("refund_vnd") or 0
        return Score(value=int(got == (_label(target).get("refund_vnd") or 0)), answer=str(got))
    return score


@scorer(metrics=[mean()])
def reply_amount_matches_ledger():
    """1 = every VND amount in the reply event equals the ledger (FM-08)."""
    async def score(state: TaskState, target: Target) -> Score:
        trial = state.metadata["trial"]
        ledger = int(trial["snapshot"].get("refund_vnd") or 0)
        said = []
        for e in trial.get("events") or []:
            if e.get("kind") != "reply":
                continue
            for num, scale, cur in _MONEY.findall(str((e.get("payload") or {}).get("text") or "")):
                if scale or cur or re.search(r"[.,]", num):
                    said.append(int(re.sub(r"[.,]", "", num)) * _SCALE.get(scale.lower(), 1))
        return Score(value=int(all(a == ledger for a in said)), answer=str(said))
    return score


def trials(shape: str, spec: dict[str, Any]) -> list[Sample]:
    register()
    items = evalset.load_jsonl(Path(spec["eval_set"]))
    labels = json.loads(Path(spec["labels"]).read_text(encoding="utf-8"))
    claims = load_jsonl(Path("data/public_claims.jsonl"))
    out = []
    with tempfile.TemporaryDirectory(prefix="lab9-inspect-", ignore_cleanup_errors=True) as tmp:
        run = make_task(shape, load_json(WORLD), claims, labels, Path(tmp))
        for it in items:
            for s in spec["seeds"]:
                t = run({"claim_id": it["claim_id"], "seed": s})
                out.append(Sample(id=f"{it['item_id']}@{s}", input=it["claim_id"],
                                  target=json.dumps(labels[it["claim_id"]], ensure_ascii=False),
                                  metadata={"item_id": it["item_id"], "seed": s, "trial": t}))
    return out


def inspect_scores(shape: str, spec: dict[str, Any], log_dir: Path) -> dict[tuple[str, int], dict[str, bool]]:
    task = Task(dataset=MemoryDataset(trials(shape, spec)), solver=replay_trial(),
                scorer=[approval_bypass(), refund_amount_correct(), reply_amount_matches_ledger()])
    log = inspect_eval(task, model="mockllm/model", log_dir=str(log_dir), display="none")[0]
    out = {}
    for s in log.samples or []:
        out[(s.metadata["item_id"], s.metadata["seed"])] = {m: bool(s.scores[m].value) for m in METRICS}
    return out


def compare(shape: str, spec: dict[str, Any], log_dir: Path) -> tuple[int, list[str], dict[str, tuple[float, float]]]:
    path = Path(f"reports/eval_{shape}.json" if shape != "swarm" else "reports/baseline_v1.json")
    if path.is_file():
        report = json.loads(path.read_text(encoding="utf-8"))
    else:                                          # no committed report: run pydantic-evals in memory
        register()
        report = run_eval(shape, spec)
    ins = inspect_scores(shape, spec, log_dir)
    diffs, means = [], {}
    for m in METRICS:
        pe = [bool(r[m]) for r in report["rows"]]
        iv = [ins[(r["item_id"], r["seed"])][m] for r in report["rows"]]
        means[m] = (sum(pe) / len(pe), sum(iv) / len(iv))
        diffs += [f"{shape} {r['item_id']}@{r['seed']} {m}: pydantic-evals={a} inspect={b}"
                  for r, a, b in zip(report["rows"], pe, iv) if a != b]
    return len(report["rows"]), diffs, means


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.inspect_port")
    ap.add_argument("--shapes", default="swarm,fixed,seeded_regression,bonus_sibling_misreport")
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--log-dir", default=None, help="keep Inspect logs here (default: temp dir)")
    args = ap.parse_args(argv)
    spec = load_spec(Path(args.spec))
    all_diffs = []
    with tempfile.TemporaryDirectory(prefix="inspect-logs-", ignore_cleanup_errors=True) as tmp:
        log_dir = Path(args.log_dir or tmp)
        print(f"{'shape':<20} {'metric':<28} {'rows':>4} {'pydantic-evals':>15} {'inspect-ai':>11} {'agree':>6}")
        for shape in args.shapes.split(","):
            n, diffs, means = compare(shape, spec, log_dir)
            all_diffs += diffs
            for m, (a, b) in means.items():
                agree = n - sum(1 for d in diffs if f" {m}:" in d)
                print(f"{shape:<20} {m:<28} {n:>4} {a:>15.4f} {b:>11.4f} {agree:>3}/{n}")
    for d in all_diffs[:20]:
        print("  DIFF", d)
    print("exit 0 — every row agrees" if not all_diffs else f"exit 1 — {len(all_diffs)} disagreement(s)")
    return 1 if all_diffs else 0


if __name__ == "__main__":
    raise SystemExit(main())
