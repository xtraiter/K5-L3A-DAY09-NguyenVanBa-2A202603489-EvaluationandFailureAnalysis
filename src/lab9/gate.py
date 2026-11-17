"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, aggregate, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    for who, rep in (("PR", pr), ("baseline", base)):
        for k, v in (rep.get("metrics") or {}).items():
            if isinstance(v, float) and not math.isfinite(v):
                problems.append(f"{who} metric {k} is {v} (NaN/inf hides a missing value)")
    problems += _row_problems(pr, base, spec)
    if base_spec is not None:
        problems += _ratchet_problems(spec, base_spec)
    return problems


_KEY = lambda r: (r.get("item_id"), r.get("seed"))   # noqa: E731


def _row_problems(pr: dict, base: dict, spec: dict) -> list[str]:
    out: list[str] = []
    rows, brows = pr.get("rows") or [], base.get("rows") or []
    man = pr.get("manifest") or {}
    want = int(man.get("items") or 0) * len(man.get("seeds") or [])
    if len(rows) != want:
        out.append(f"{len(rows)} rows, manifest says {man.get('items')} items x {len(man.get('seeds') or [])} seeds = {want}")
    keys = [_KEY(r) for r in rows]
    dups = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dups:
        out.append(f"duplicate (item, seed) rows: {dups[:5]}")
    pk, bk = set(keys), {_KEY(r) for r in brows}
    if pk != bk:
        out.append(f"(item, seed) set differs from the baseline's: missing {sorted(bk - pk, key=str)[:5]}, "
                   f"extra {sorted(pk - bk, key=str)[:5]}")
    bman = base.get("manifest") or {}
    for f in ("items", "seeds"):
        if man.get(f) != bman.get(f):
            out.append(f"manifest {f} {man.get(f)} != baseline {bman.get(f)}")
    if pr.get("evaluator_failures"):
        out.append(f"{len(pr['evaluator_failures'])} evaluator failure(s), first: {pr['evaluator_failures'][0]}")
    graded = [m["id"] for m in spec["metrics"] if m["id"] in GRADERS]
    for m in graded:
        bad = [_KEY(r) for r in rows if not isinstance(r.get(m), bool)]
        if bad:
            out.append(f"{len(bad)} row(s) with non-boolean {m} (crashed/missing grader), first {bad[0]}")
    # Slice tags must be the baseline's: relabelling an item hides it from the slice gate.
    btags = {_KEY(r): sorted(r.get("slices") or []) for r in brows}
    moved = [k for k, r in zip(keys, rows) if k in btags and sorted(r.get("slices") or []) != btags[k]]
    if moved:
        out.append(f"{len(moved)} row(s) carry slice tags that differ from the baseline's, first {moved[0]}")
    # Reported metrics must be what the rows say (a hand-edited headline number).
    if rows and not out:
        clean = [{**r, "cost": float(r.get("cost") or 0.0)} for r in rows]
        redo = aggregate(clean, [m for m in graded if all(m in r for r in rows)], k_values=spec.get("pass_k", []))
        has_cost = all("cost" in r for r in rows)
        for k, v in (pr.get("metrics") or {}).items():
            if k not in redo or (k == "cost_per_success" and not has_cost):
                continue
            r = redo[k]
            if (v is None) != (r is None) or (v is not None and abs(float(v) - float(r)) > 5e-4):
                out.append(f"metric {k}={v} but the rows give {r}")
    return out


def _looser(old: dict, new: dict) -> list[str]:
    """Threshold fields of `new` that are laxer than `old` (missing counts as laxer)."""
    out = []
    for f in ("max", "max_increase"):
        if f in old and (f not in new or new[f] > old[f]):
            out.append(f"{f} {old[f]} -> {new.get(f, 'removed')}")
    if "min" in old and ("min" not in new or new["min"] < old["min"]):
        out.append(f"min {old['min']} -> {new.get('min', 'removed')}")
    if old.get("no_significant_drop") and not new.get("no_significant_drop"):
        out.append("no_significant_drop dropped")
    return out


def _ratchet_problems(spec: dict, base_spec: dict) -> list[str]:
    out: list[str] = []
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        # The eval set itself is unchanged (sha checked before this), so a new version label is
        # only a way around the ratchet.
        out.append(f"eval_set_version {base_spec.get('eval_set_version')!r} -> {spec.get('eval_set_version')!r} "
                   "on the same eval set: ratchet still applies")
    new = {m["id"]: m for m in spec.get("metrics") or []}
    for m in base_spec.get("metrics") or []:
        n = new.get(m["id"])
        if n is None:
            out.append(f"ratchet: metric {m['id']} removed")
            continue
        if m.get("blocking") and not n.get("blocking"):
            out.append(f"ratchet: metric {m['id']} no longer blocking")
        out += [f"ratchet: metric {m['id']} {x}" for x in _looser(m.get("threshold") or {}, n.get("threshold") or {})]
    new_sl = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for s in base_spec.get("slices") or []:
        n = new_sl.get((s["name"], s["metric"]))
        tag = f"slice {s['name']}/{s['metric']}"
        if n is None:
            out.append(f"ratchet: {tag} removed")
            continue
        if s.get("blocking") and not n.get("blocking"):
            out.append(f"ratchet: {tag} no longer blocking")
        out += [f"ratchet: {tag} {x}" for x in _looser(s, n)]
    new_nnf = {r["metric"]: r for r in spec.get("no_new_failures") or []}
    for r in base_spec.get("no_new_failures") or []:
        n = new_nnf.get(r["metric"])
        if n is None or (r.get("blocking") and not n.get("blocking")):
            out.append(f"ratchet: no_new_failures/{r['metric']} removed or no longer blocking")
    if set(base_spec.get("pass_k") or []) - set(spec.get("pass_k") or []):
        out.append(f"ratchet: pass_k {base_spec.get('pass_k')} -> {spec.get('pass_k')}")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            verdict = "missing"                       # an empty slice cannot vouch for anything
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in sl and val < sl["min"]:
                verdict = "fail"
            if "max" in sl and val > sl["max"]:
                verdict = "fail"
            keys = sorted(set(a) & set(b))
            if sl.get("no_significant_drop") and keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                                                   confidence=bs.get("confidence", 0.95))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        th = {k: sl[k] for k in ("min", "max", "no_significant_drop") if k in sl}
        lines.append(f"  {sid:<38} {val!s:<8} n={len(a):<3} {json.dumps(th):<34} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        a, b = per_item(pr, mid), per_item(base, mid)
        keys = sorted(set(a) & set(b))
        if th.get("no_significant_drop") and val is not None and keys:   # report-level metrics (pass_hat_k) have no rows
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    if spec.get("no_new_failures"):
        nb, nl = new_failure_check(pr, base, spec)
        blocked += nb
        lines += nl
    return blocked, lines


def new_failure_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """An item that passed on EVERY seed in the baseline must not fail on any seed in the PR.
    Averages and paired CIs cannot see a PR that fixes some items and breaks others by the same
    amount (e.g. a 1-in-5-seed bug on items the baseline never failed). Spec:
    no_new_failures: [{metric: pass_rate, blocking: true}]."""
    blocked, lines = [], []
    for rule in spec.get("no_new_failures") or []:
        metric = rule["metric"]
        a, b = per_item(pr, metric), per_item(base, metric)
        stable = sorted(k for k, v in b.items() if v == 1.0)
        new = [k for k in stable if a.get(k, 0.0) < 1.0]
        rid = f"new_failures/{metric}"
        if new and rule.get("blocking"):
            blocked.append(rid)
        label = "ok" if not new else ("BLOCK" if rule.get("blocking") else "warn")
        lines.append(f"  {rid:<38} {len(new)} of {len(stable)} stable item(s) now fail {new[:6]!s:<40} {label}")
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
