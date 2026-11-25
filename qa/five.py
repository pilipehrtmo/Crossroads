import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import common as QA
"""Five people, five isolated browsers, all at once. Each does the whole student tutorial with their own behaviour."""
import sys, random, json, time, threading, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from journey import journey, state
from playwright.sync_api import sync_playwright
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8040
people = [
  dict(tag="A", vp="desk",  lang="en", extra={}, note="normal speed"),
  dict(tag="B", vp="desk",  lang="en", extra={"skills": "refresh", "d_open": "refresh", "p_people": "refresh"}, note="refreshes 3 times"),
  dict(tag="C", vp="phone", lang="en", extra={"pw2": "back", "d_comps": "back", "note": "back", "s_seats": "back"}, note="presses Back repeatedly"),
  dict(tag="D", vp="desk",  lang="zh", extra={"d_search": "away", "after": "away"}, note="leaves and comes back, Chinese"),
  dict(tag="E", vp="phone", lang="en", extra={}, note="fast", slow=0),
]
q = lambda s: QA.q(s, None)
res = {}
def run(pp):
    R = random.randint(100000, 999999); L = "".join(chr(97 + int(c)) for c in str(R)).capitalize()
    who = dict(email=f"five{pp['tag'].lower()}{R}@example.com", name=f"Person {pp['tag']} {L}", sid=f"116{R}")
    VP = {"desk": dict(viewport={"width": 1366, "height": 768}), "phone": dict(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)}
    out = []; log = lambda m: out.append(m)
    with sync_playwright() as p:
        ctx = p.chromium.launch().new_context(**VP[pp["vp"]]); ctx.add_cookies([{"name": "lang", "value": pp["lang"], "url": f"http://localhost:{PORT}"}])
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: m.type == "error" and "TUNNEL" not in m.text and errs.append(m.text))
        if pp["tag"] == "A": time.sleep(2)   # a slower starter
        t0 = time.time()
        try: recs = journey(pg, PORT, who, "student", pp["lang"], log=log, extra=pp["extra"])
        except Exception as e: recs = []; out.append("EXCEPTION " + repr(e)[:300])
        # who does the site think I am, at the end?
        pg.goto(f"http://localhost:{PORT}/profile"); me_name = pg.locator("#h").input_value() if pg.locator("#h").count() else None
        skills = pg.locator("#s").input_value() if pg.locator("#s").count() else None
        res[pp["tag"]] = dict(note=pp["note"], email=who["email"], steps=len(recs), finished=bool(recs and recs[-1].get("finished")), secs=round(time.time() - t0),
                              profile_name_ok=(me_name == who["name"]), skills=skills, issues=[(r["key"], r["issues"]) for r in recs if r["issues"]],
                              after=[(r["key"], r.get("after")) for r in recs if "after" in r], errs=errs[:5], log=out[-3:])
ts = [threading.Thread(target=run, args=(pp,)) for pp in people]
[t.start() for t in ts]; [t.join() for t in ts]
for k in sorted(res):
    r = res[k]; print(k, json.dumps({x: r[x] for x in r if x != "log"}, ensure_ascii=False))
    if not r["finished"]: print("   last:", r["log"])
emails = "','".join(r["email"] for r in res.values())
print("DB:", q(f"select email||' skills='||skills||' deg='||degree from \\\"user\\\" where email in ('{emails}') order by email"))
