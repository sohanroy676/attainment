"""Prototype of the config-as-data engine, used only to validate the design."""
import sys, json, openpyxl
from decimal import Decimal as D, ROUND_DOWN, getcontext
from collections import defaultdict
getcontext().prec = 40

def dec(v):
    return None if v is None or v == "" else D(str(v))

def trunc(x, places=2):
    return x.quantize(D(1).scaleb(-places), rounding=ROUND_DOWN)

# ---------- loading (stands in for the import module) ----------
def load_question_sheet(ws, max_row, co_row, data_rows, roll_col, cols, label_fn):
    qs = []
    for c in cols:
        mx = ws[f"{c}{max_row}"].value
        co = ws[f"{c}{co_row}"].value
        if mx is None: continue
        co = int(str(co).replace("CO","").strip())
        qs.append({"id": label_fn(c), "col": c, "max": D(str(mx)), "co": co})
    marks = {}
    for r in data_rows:
        roll = ws[f"{roll_col}{r}"].value
        if roll is None: continue
        marks[str(roll)] = {q["id"]: dec(ws[f"{q['col']}{r}"].value) for q in qs}
    return qs, marks

def cols(a, b):
    import openpyxl.utils as u
    return [u.get_column_letter(i) for i in range(u.column_index_from_string(a), u.column_index_from_string(b)+1)]

# ---------- building-block steps ----------
def passes(mark, threshold, boundary):
    return mark >= threshold if boundary == ">=" else mark > threshold

def question_wise(qs, marks, rule):
    """Step: QuestionPass + Denominator + CO average. Returns per-question and per-CO detail."""
    per_q = []
    for q in qs:
        thr = q["max"] * D(rule["pass_pct"]) / 100
        if q["id"] in rule.get("pass_mark_override", {}):
            thr = D(rule["pass_mark_override"][q["id"]])
        vals = [m[q["id"]] for m in marks.values()]
        attempted = [v for v in vals if v is not None]
        n_pass = sum(1 for v in attempted if passes(v, thr, rule["boundary"]))
        mode = rule["denominator"]
        if mode == "by_question":   # decided rule (2026-11-09): choice -> attempted only, compulsory -> all who sat
            mode = "attempted" if q["id"] in rule["choice_ids"] else "enrolled"
        if mode == "attempted": den = len(attempted)
        elif mode == "fixed": den = rule["fixed_n"]
        else: den = len(vals)          # enrolled / cohort list
        pct = D(n_pass) * 100 / den if den else None
        per_q.append({"q": q["id"], "co": q["co"], "pass": n_pass, "den": den, "attempted": len(attempted), "pct": pct})
    per_co = defaultdict(list)
    for p in per_q:
        if p["pct"] is not None: per_co[p["co"]].append(p["pct"])
    return per_q, {co: sum(v)/len(v) for co, v in sorted(per_co.items())}

def per_student_average(marks, items, max_mark, rule):
    """Step: PerStudentAverage (quiz / assignment)."""
    thr = D(max_mark) * D(rule["pass_pct"]) / 100
    n_pass = 0; den = 0
    for m in marks.values():
        vals = [m.get(i) for i in items]
        if rule["absent"] == "zero": vals = [v if v is not None else D(0) for v in vals]
        else: vals = [v for v in vals if v is not None]
        if not vals: continue
        den += 1
        if passes(sum(vals)/len(vals), thr, rule["boundary"]): n_pass += 1
    return n_pass, den, D(n_pass)*100/den

def band(pct, bands):
    """Step: Bands. bands = [[min_pct, level], ...] high to low; below lowest -> flag."""
    for lo, lvl in bands:
        if pct >= D(str(lo)): return D(lvl), None
    return None, "BELOW_LOWEST_BAND"

def combine(weights, levels):
    return sum(D(str(w)) * levels[t] for t, w in weights.items())

def po_from_cos(co_att, mapping):
    out = {}
    for po in sorted({p for m in mapping.values() for p in m}, key=lambda s: (s.startswith("PSO"), int(s.replace("PSO","").replace("PO","")))):
        num = sum(D(mapping[co][po]) * co_att[co] for co in mapping if po in mapping[co])
        den = sum(D(mapping[co][po]) for co in mapping if po in mapping[co])
        out[po] = num/den
    return out

def choice_select(marks, groups, best_n, best_k_parts=None, missing="zero"):
    """Step: ChoiceSelect. groups = {question_no: [part ids]}. Keeps the best N question totals per
    student (question total = sum of parts, or best K parts where configured). Parts of dropped
    questions become 'not counted' (None). Returns new marks + a log for the explanation."""
    best_k_parts = best_k_parts or {}
    out, log = {}, []
    for s, m in marks.items():
        m = dict(m); totals = {}
        for qn, parts in groups.items():
            vals = [(p, m[p]) for p in parts if m[p] is not None]
            if not vals: continue
            k = best_k_parts.get(qn)
            if k and len(vals) > k:
                keep = sorted(vals, key=lambda x: x[1], reverse=True)[:k]
                for p, _ in vals:
                    if p not in dict(keep): m[p] = None; log.append((s, f"Q{qn} part {p} dropped (best {k} parts)"))
                vals = keep
            totals[qn] = sum(v for _, v in vals)
        if len(totals) > best_n:
            ranked = sorted(totals.items(), key=lambda x: (-x[1], x[0]))
            for qn, t in ranked[best_n:]:
                for p in groups[qn]: m[p] = None
                log.append((s, f"Q{qn} (total {t}) dropped: best {best_n} kept"))
        out[s] = m
    return out, log
