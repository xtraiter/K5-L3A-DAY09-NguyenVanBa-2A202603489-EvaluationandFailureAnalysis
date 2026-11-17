"""Team tests for the M5-M7 gate additions (run in the eval-gate-v2 job via -k advanced)."""
import copy

import pytest

pytestmark = pytest.mark.student


def _rows(fail=()):
    return [{"item_id": f"E-{i:03d}", "seed": s, "pass_rate": (i, s) not in fail,
             "slices": ["money_movement"] if i < 2 else [], "cost": 1.0} for i in range(4) for s in (1, 2)]


def _rep(rows):
    from lab9.eval import aggregate

    return {"manifest": {"eval_set_sha": "x", "items": 4, "seeds": [1, 2]}, "rows": rows,
            "metrics": aggregate(rows, ["pass_rate"]), "evaluator_failures": []}


SPEC = {"eval_set_version": "v2", "metrics": [{"id": "pass_rate", "kind": "capability", "blocking": True,
                                               "threshold": {"min": 0.5}}],
        "no_new_failures": [{"metric": "pass_rate", "blocking": True}]}


def test_advanced_new_failure_on_stable_item_blocks():
    from lab9 import gate

    base = _rep(_rows(fail={(0, 1)}))                  # baseline fails E-000 once
    swapped = _rep(_rows(fail={(3, 1)}))               # PR fixes E-000, breaks stable E-003: same mean
    blocked, _ = gate.check(swapped, base, SPEC)
    assert blocked == ["new_failures/pass_rate"]
    assert gate.check(base, base, SPEC)[0] == []


def test_advanced_integrity_duplicates_hand_edits_and_slice_relabels():
    from lab9 import gate

    base = _rep(_rows())
    dup = copy.deepcopy(base)
    dup["rows"][1] = copy.deepcopy(dup["rows"][0])
    assert any("duplicate" in p for p in gate.integrity_check(dup, base, SPEC))
    edited = _rep(_rows(fail={(1, 1)}))
    edited["metrics"]["pass_rate"] = 1.0
    assert any("rows give" in p for p in gate.integrity_check(edited, base, SPEC))
    moved = copy.deepcopy(base)
    for r in moved["rows"]:
        r["slices"] = []
    assert gate.integrity_check(moved, base, SPEC)
    green_but_crashed = copy.deepcopy(base)
    green_but_crashed["evaluator_failures"] = ["E-000@1:X:boom"]
    assert gate.integrity_check(green_but_crashed, base, SPEC)


def test_advanced_ratchet_version_bump_and_dropped_rules():
    from lab9 import gate

    base = _rep(_rows())
    bumped = dict(copy.deepcopy(SPEC), eval_set_version="v3")
    assert gate.integrity_check(base, base, bumped, SPEC)
    no_rule = {k: v for k, v in copy.deepcopy(SPEC).items() if k != "no_new_failures"}
    assert gate.integrity_check(base, base, no_rule, SPEC)


def test_advanced_proposal_correct_grader():
    from pydantic_evals.evaluators import EvaluatorContext

    from lab9.graders import ProposalCorrect

    def ctx(proposal):
        return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output={"proposal_amount": 35000},
                                output={"result": {"proposal_amount": proposal}, "snapshot": {}},
                                duration=0.0, _span_tree=None, attributes={}, metrics={})

    assert ProposalCorrect().evaluate(ctx(35000)).value is True
    assert ProposalCorrect().evaluate(ctx(0)).value is False
