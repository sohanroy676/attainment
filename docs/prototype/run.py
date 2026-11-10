import sys, json, openpyxl
sys.path.insert(0, sys.argv[2])
from engine import *
wb = openpyxl.load_workbook(sys.argv[1], data_only=True)
lab = lambda ws: (lambda c: f"{c}")
I1q, I1 = load_question_sheet(wb["DL-CSE-AIML--VI-Sem-I-internal"], 4, 6, range(8, 75), "B", cols("C","P"), lambda c: "I1_"+c)
I2q, I2 = load_question_sheet(wb["DL-CSE-AIML-VI-Sem-II-internal"], 4, 6, range(8, 75), "B", cols("C","N"), lambda c: "I2_"+c)
SEq, SE = load_question_sheet(wb["SEE"], 4, 3, range(7, 73), "B", cols("C","AA"), lambda c: "SEE_"+c)
wsq = wb["DL Quiz-Assignment"]
QA = {str(wsq[f"B{r}"].value): {k: dec(wsq[f"{c}{r}"].value) for k, c in zip(["q1","q2","q3","a1","a2","a3"], "CDEGHI")} for r in range(6, 73) if wsq[f"B{r}"].value}
wsl = wb["DL lab attainment"]
LAB = {str(wsl[f"B{r}"].value): {"lab": dec(wsl[f"C{r}"].value)} for r in range(5, 72) if wsl[f"B{r}"].value}

# roster / data checks
print("students: I1", len(I1), "I2", len(I2), "SEE", len(SE), "QA", len(QA), "LAB", len(LAB))
print("same roll set I1/I2/QA/LAB:", set(I1)==set(I2)==set(QA)==set(LAB))
print("Int-II Q C attempted actually:", sum(1 for m in I2.values() if m["I2_C"] is not None), "(sheet typed 61)")
print("Quiz/assignment blanks:", sum(1 for m in QA.values() for v in m.values() if v is None))
# SEE best-5 check: questions 11-17 = parts M..AA; group by question
import re
see_hdr = {c: wb["SEE"][f"{c}6"].value for c in cols("C","AA")}
grp = defaultdict(list)
for c, h in see_hdr.items():
    m = re.match(r"(\d+)", str(h)); n = int(m.group(1))
    if n >= 11: grp[n].append("SEE_"+c)
cnt = defaultdict(int)
for s, m in SE.items():
    k = sum(1 for n, ps in grp.items() if any(m[p] is not None for p in ps))
    cnt[k] += 1
print("SEE: number of Q11-17 questions answered per student -> students:", dict(sorted(cnt.items())))
q17 = [p for p in grp[17]]
print("Q17 students with all 3 parts:", sum(1 for m in SE.values() if all(m[p] is not None for p in q17)))

SE_raw = SE
SE, choice_log = choice_select(SE_raw, dict(grp), best_n=5, best_k_parts={17: 2})
print("ChoiceSelect log:", choice_log)
BANDS = [[60,3],[50,2],[10,1]]
WEIGHTS = {"internal": "0.30", "assignment": "0.05", "quiz": "0.05", "see": "0.60"}
MAP = {1: {"PO1":2,"PO3":2,"PO4":1,"PSO1":1,"PSO2":3,"PSO3":3},
       2: {"PO1":2,"PO2":2,"PO3":2,"PO4":2,"PO5":2,"PSO1":1,"PSO2":3,"PSO3":3},
       3: {"PO1":3,"PO2":2,"PO3":3,"PO4":2,"PO5":2,"PSO1":2,"PSO2":3,"PSO3":3},
       4: {"PO1":3,"PO2":2,"PO3":2,"PO4":2,"PO5":1,"PSO1":2,"PSO2":3,"PSO3":3},
       5: {"PO1":3,"PO2":2,"PO5":2,"PSO1":2,"PSO2":3,"PSO3":3}}

def run(name, cfg):
    print(f"\n######## {name}")
    co_pct = {}
    for tool, (qs, mk) in {"I1": (I1q, I1), "I2": (I2q, I2), "SEE": (SEq, SE)}.items():
        pq, pc = question_wise(qs, mk, cfg[tool])
        co_pct[tool] = pc
        print(tool, {co: str(trunc(v)) for co, v in pc.items()})
    qn, qd, qp = per_student_average(QA, ["q1","q2","q3"], 5, cfg["quiz"])
    an, ad, ap = per_student_average(QA, ["a1","a2","a3"], 5, cfg["quiz"])
    ln = sum(1 for m in LAB.values() if m["lab"] is not None and m["lab"] >= 18)
    print(f"quiz {qn}/{qd}={trunc(qp)}  assignment {an}/{ad}={trunc(ap)}  lab {ln}/{len(LAB)}")
    flags = []
    lv = {"internal": {}, "see": {}}
    for co in range(1, 6):
        ints = [band(co_pct[t][co], BANDS) for t in ("I1","I2") if co in co_pct[t]]
        for l, f in ints:
            if f: flags.append((co, "internal", f))
        lv["internal"][co] = sum(l for l, _ in ints) / len(ints)
        l, f = band(co_pct["SEE"][co], BANDS); lv["see"][co] = l
        if f: flags.append((co, "see", f))
    qlvl, _ = band(qp, BANDS); alvl, _ = band(ap, BANDS)
    direct = {co: combine(WEIGHTS, {"internal": lv["internal"][co], "see": lv["see"][co], "quiz": qlvl, "assignment": alvl}) for co in range(1,6)}
    final = {co: D("0.8")*direct[co] + D("0.2")*D(3) for co in direct}
    course = sum(final.values())/len(final)
    pos = po_from_cos(final, MAP)
    print("levels internal", {c: str(v) for c, v in lv["internal"].items()}, "see", {c: str(v) for c, v in lv["see"].items()}, "quiz", qlvl, "assign", alvl)
    print("direct", {c: str(trunc(v)) for c, v in direct.items()})
    print("CO    ", {c: str(trunc(v)) for c, v in final.items()})
    print("course", course, "->", trunc(course), "target 2.2:", "Attained" if course >= D("2.2") else "Not attained")
    print("PO    ", {p: str(trunc(v)) for p, v in pos.items()})
    print("flags", flags)
    return trunc(course), {p: trunc(v) for p, v in pos.items()}

faithful = {"I1": {"pass_pct": 60, "boundary": ">", "denominator": "fixed", "fixed_n": 67},
            "I2": {"pass_pct": 60, "boundary": ">=", "denominator": "attempted"},
            "SEE": {"pass_pct": 60, "boundary": ">=", "denominator": "fixed", "fixed_n": 66},
            "quiz": {"pass_pct": 60, "boundary": ">=", "absent": "skip"}}
confirmed = {"I1": {"pass_pct": 60, "boundary": ">=", "denominator": "enrolled"},
             "I2": {"pass_pct": 60, "boundary": ">=", "denominator": "attempted"},
             "SEE": {"pass_pct": 60, "boundary": ">=", "denominator": "attempted"},
             "quiz": {"pass_pct": 60, "boundary": ">=", "absent": "zero"}}
see_cohort = json.loads(json.dumps(confirmed)); see_cohort["SEE"] = {"pass_pct": 60, "boundary": ">=", "denominator": "enrolled"}
sheet_thr = json.loads(json.dumps(confirmed))
sheet_thr["I2"]["pass_mark_override"] = {"I2_"+c: "2" for c in "CEGIKM"}
course, pos = run("D. confirmed rules + Int-II pass marks as typed in the sheet (2 for 3.5-mark parts)", sheet_thr)
ref = {"PO1":"2.29","PO2":"2.28","PO3":"2.41","PO4":"2.38","PO5":"2.31","PSO1":"2.28","PSO2":"2.32","PSO3":"2.32"}
print("MATCH Appendix A course 2.32:", str(course) == "2.32", "| PO/PSO all match:", all(str(pos[k]) == v for k, v in ref.items()), {k: (str(pos[k]), v) for k, v in ref.items() if str(pos[k]) != v})
# boundary sensitivity: Int-I with '>' vs '>='
gt = json.loads(json.dumps(sheet_thr)); gt["I1"]["boundary"] = ">"
run("E. same as D but Int-I boundary '>'", gt)
see66 = json.loads(json.dumps(sheet_thr)); see66["SEE"] = {"pass_pct": 60, "boundary": ">=", "denominator": "enrolled"}
run("F. same as D but SEE denominator = all 66 SEE students for every part", see66)
mixed = json.loads(json.dumps(sheet_thr)); mixed["SEE"]["denominator_by_part"] = True

see_choice = {p for ps in grp.values() for p in ps}           # Q11-Q17 parts
i2_all = {q["id"] for q in I2q}                                  # Int-II: every question is either/or
decided = {"I1": {"pass_pct": 60, "boundary": ">=", "denominator": "by_question", "choice_ids": set()},
           "I2": {"pass_pct": 60, "boundary": ">=", "denominator": "by_question", "choice_ids": i2_all},
           "SEE": {"pass_pct": 60, "boundary": ">=", "denominator": "by_question", "choice_ids": see_choice},
           "quiz": {"pass_pct": 60, "boundary": ">=", "absent": "zero"}}
run("G. DECIDED RULES (2026-11-09): strict 60%, choice -> attempted, compulsory -> all who sat", decided)
import copy
dec_typed = copy.deepcopy(decided)
dec_typed["I2"]["pass_mark_override"] = {"I2_"+c: "2" for c in "CEGIKM"}
run("H. decided rules + the sheet's typed Internal-II pass marks as overrides", dec_typed)
i2_groups = {n: ["I2_"+c for c in cs] for n, cs in zip(range(1, 7), ["CD", "EF", "GH", "IJ", "KL", "MN"])}
I2_raw = I2
I2, i2_log = choice_select(I2_raw, i2_groups, best_n=4)
print("\nInternal-II best 4 of 6 log:", i2_log)
run("I. decided rules + Internal-II 'best 4 of 6' choice applied", decided)
run("J. as I + the sheet's typed Internal-II pass marks as overrides", dec_typed)
I2 = I2_raw
run("A. strict 60%, Int-I > and /67, SEE /66 for every part", faithful)
run("B. confirmed rules: >= everywhere, SEE per-part attempted-only", confirmed)
run("C. confirmed rules but SEE denominator = all SEE-attempted (66)", see_cohort)
