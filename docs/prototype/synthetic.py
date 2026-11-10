import sys; sys.path.insert(0, sys.argv[1])
from engine import *
P = lambda: None
# 1. best 2 of 3 parts in Q17, best 5 of 7 questions, with a tie
groups = {n: [f"{n}a", f"{n}b"] for n in range(11, 17)}; groups[17] = ["17a", "17b", "17c"]
m = {p: None for ps in groups.values() for p in ps}
s = dict(m, **{"11a": D(4), "11b": D(4), "12a": D(3), "12b": D(3), "13a": D(2), "13b": D(2),
               "14a": D(2), "14b": D(2), "15a": D(1), "15b": D(1), "17a": D(4), "17b": D(1), "17c": D(3)})
out, log = choice_select({"x": s}, groups, best_n=5, best_k_parts={17: 2})
kept = sorted({k[:2] for k, v in out["x"].items() if v is not None})
print("T1 log:", log); print("T1 kept questions:", kept, "(expect 11,12,13,14,17; Q15 total 2 dropped; 17b dropped)")
assert out["x"]["17b"] is None and out["x"]["17a"] == 4 and out["x"]["15a"] is None
# 2. tie at the 5th place: Q13 and Q14 both total 4 -> tie rule lower number kept
s2 = dict(m, **{"11a": D(4), "11b": D(4), "12a": D(4), "12b": D(4), "13a": D(2), "13b": D(2), "14a": D(2), "14b": D(2), "15a": D(4), "15b": D(4), "16a": D(4), "16b": D(4)})
out2, log2 = choice_select({"y": s2}, groups, best_n=5)
print("T2 tie log:", log2, "(expect Q14 dropped by tie rule)")
assert out2["y"]["14a"] is None and out2["y"]["13a"] == 2
# 3. student who attempted only 4: nothing dropped; 'missing = 0' has no part/CO to attach to
s3 = dict(m, **{"11a": D(4), "12a": D(4), "13a": D(4), "14a": D(4)})
out3, log3 = choice_select({"z": s3}, groups, best_n=5)
print("T3 four attempted, log:", log3, "-> a missing 5th question has no CO, so per-part % ignores it")
# 4. boundary exactly at 60% and truncation vs float
qs = [{"id": "q", "max": D(3), "co": 1}]
mk = {str(i): {"q": D("1.8")} for i in range(3)}
_, ge = question_wise(qs, mk, {"pass_pct": 60, "boundary": ">=", "denominator": "attempted"})
_, gt = question_wise(qs, mk, {"pass_pct": 60, "boundary": ">", "denominator": "attempted"})
print("T4 exactly 1.8 of 3:", ge, gt); assert ge[1] == 100 and gt[1] == 0
print("T5 float trap: float 0.8*2.4+0.6 =", 0.8*2.4+0.6, " Decimal:", D("0.8")*D("2.4")+D("0.6"))
# 6. merged internal level can be fractional (R9): Int-I L3, Int-II L2 -> 2.5
print("T6 merged level:", (D(3)+D(2))/2, "-> direct =", combine({"i": "0.30", "s": "0.60", "q": "0.05", "a": "0.05"}, {"i": D("2.5"), "s": D(2), "q": D(3), "a": D(3)}))
# 7. below lowest band
print("T7 band 9.99%:", band(D("9.99"), [[60,3],[50,2],[10,1]]))
# 8. zero denominator: nobody attempted a choice part
_, z = question_wise([{"id": "q", "max": D(4), "co": 2}], {"a": {"q": None}}, {"pass_pct": 60, "boundary": ">=", "denominator": "attempted"})
print("T8 nobody attempted -> CO dict:", z, "(CO2 missing for this tool: needs a rule)")
print("ALL SYNTHETIC CHECKS DONE")
