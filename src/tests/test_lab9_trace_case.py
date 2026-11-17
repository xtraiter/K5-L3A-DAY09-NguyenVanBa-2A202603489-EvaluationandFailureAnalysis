"""Regression test from docs/trace_case.md: seeded_regression C-008@11 (FM-08 misreport).

Lab 8's trial_pass passes this trial (ledger 20.000 = label), yet the reply tells the customer
35.000đ. Only the M3 grader ReplyMatchesLedger catches it; the same claim@seed on `fixed` must pass.
"""
import pytest

pytestmark = pytest.mark.student


def _grade(shape: str, claim: str = "C-008", seed: int = 11):
    from pydantic_evals.evaluators import EvaluatorContext

    from lab9.graders import ReplyMatchesLedger, TrialPass
    from lab9.trace_case import investigate

    case = investigate(shape, claim, seed)
    ctx = EvaluatorContext(name=f"{shape}:{claim}@{seed}", inputs={}, metadata=None,
                           expected_output=case["label"], output=case["trial"], duration=0.0,
                           _span_tree=None, attributes={}, metrics={})
    return case["trial"], TrialPass().evaluate(ctx), ReplyMatchesLedger().evaluate(ctx)


def test_lab9_trace_case_fm08_caught_on_seeded_regression():
    trial, lab8, reply = _grade("seeded_regression")
    assert trial["snapshot"]["refund_vnd"] == 20000          # the ledger is right ...
    assert lab8.value is True                                # ... so Lab 8's grader is blind to it
    assert reply.value is False                              # the reply's 35.000đ is caught
    assert "35000" in reply.reason


def test_lab9_trace_case_fm08_clean_on_fixed():
    _, lab8, reply = _grade("fixed")
    assert lab8.value is True and reply.value is True
