import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import common as QA
import sys, random, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from journey import journey
from playwright.sync_api import sync_playwright
port, tour, vp, lang = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
extra = json.loads(sys.argv[5]) if len(sys.argv) > 5 else {}
VPS = {"desk": dict(viewport={"width": 1366, "height": 768}), "phone": dict(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=2)}
R = random.randint(100000, 999999)
L = "".join(chr(97 + int(c)) for c in str(R)).capitalize()
who = dict(email=f"qa{R}@example.com", name=f"Tester {L}", sid=f"115{R}")
if tour == "prof": who.update(email=f"qaprof{R}@cs.nthu.edu.tw", name=f"Prof {L}")
with sync_playwright() as p:
    ctx = p.chromium.launch().new_context(**VPS[vp]); ctx.add_cookies([{"name": "lang", "value": lang, "url": f"http://localhost:{port}"}])
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: m.type == "error" and errs.append("console: " + m.text) if 'TUNNEL' not in m.text else None)
    recs = journey(pg, port, who, tour, lang, extra=extra)
    pg.screenshot(path=f"{QA.SHOTS}/qa_end_{tour}_{vp}_{lang}.png")
    print(json.dumps(dict(who=who["email"], steps=len(recs), finished=bool(recs and recs[-1].get("finished")), issues=[(r["key"], r["issues"]) for r in recs if r["issues"]], errs=errs[:10]), ensure_ascii=False))
