import sys, openpyxl
from decimal import Decimal as D, ROUND_DOWN, ROUND_HALF_UP
wb = openpyxl.load_workbook(sys.argv[1], data_only=True)
wbf = openpyxl.load_workbook(sys.argv[1])
ws = wb["CSE_PO_Attainment"]; wf = wbf["CSE_PO_Attainment"]
hdr = [c.value for c in ws[7]]
pcols = [i for i, h in enumerate(hdr) if h and str(h).startswith(("PO","PSO"))]
print("direct formula PO1:", wf.cell(129, pcols[0]+1).value[:120])
print("total formula PO1:", wf.cell(132, pcols[0]+1).value)
vals = {hdr[i]: [] for i in pcols}
for r in range(8, 128):
    row = [c.value for c in ws[r]]
    if row[2] is None or row[2] == "Course Name": continue
    for i in pcols:
        v = row[i]
        if isinstance(v, (int, float)): vals[hdr[i]].append(D(str(v)))
tgt = {hdr[i]: D(str(ws.cell(131, i+1).value)) for i in pcols}
print(f"{'PO':5} {'n':>3} {'my avg':>8} {'file':>8} {'total':>8} {'trunc':>6} {'round':>6} {'target':>6}  status(unrounded/trunc/round)")
for i in pcols:
    h = hdr[i]; v = vals[h]; avg = sum(v)/len(v)
    filev = D(str(ws.cell(129, i+1).value))
    tot = D("0.8")*avg + D("0.6")
    tr = tot.quantize(D("0.01"), ROUND_DOWN); ro = tot.quantize(D("0.01"), ROUND_HALF_UP)
    st = lambda x: "A" if x >= tgt[h] else "NOT"
    print(f"{h:5} {len(v):>3} {str(avg.quantize(D('0.0001'))):>8} {str(filev.quantize(D('0.0001'))):>8} {str(tot.quantize(D('0.0001'))):>8} {str(tr):>6} {str(ro):>6} {str(tgt[h]):>6}  {st(tot)}/{st(tr)}/{st(ro)}")
g = wb["CSE 3yrs Graph PO PSO attainmen"]
for r in range(1, 25):
    v = [c.value for c in g[r] if c.value is not None]
    if v: print("graph", r, v[:17])
