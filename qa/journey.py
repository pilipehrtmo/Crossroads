import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import common as QA
"""Drives a whole tutorial like a person would, and checks every step.
journey(page, tour='student'|'prof', ...) -> list of step records. Used by run_one.py and five_users.py."""
import re, time, json, subprocess
PW = "Tr0ub4dor&3xyz"
SHOTS = {"d_nav", "d_nav_m", "d_comps", "d_open"}

def verify_link(port, email, tries=40):
    for _ in range(tries):
        log = open(QA.log(port), encoding="utf-8", errors="ignore").read()
        m = re.findall(r">>> EMAIL to " + re.escape(email) + r": Confirm.*?\n.*?\n\n.*?\n(http\S+/verify/\S+)", log, re.S)
        if m: return m[-1]
        time.sleep(0.25)
    return None

def state(pg):
    return pg.evaluate("""() => { const l = document.querySelector('.tour:not(.t-pill)'); if (!l) return null;
      const tip = l.querySelector('.t-tip'), sp = document.querySelector('.t-spot.on:not(.none)');
      const R = e => { if (!e) return null; const r = e.getBoundingClientRect(); return {x:r.left,y:r.top,w:r.width,h:r.height}; };
      const btns = [...l.querySelectorAll('.t-acts button, .t-sect')].map(b => ({t: b.textContent.trim(), dis: b.disabled}));
      return {key: l.dataset.key, step: l.querySelector('.t-step').textContent, title: l.querySelector('#t-h').textContent,
              text: l.querySelector('.t-text').textContent, hint: l.querySelector('.t-hint').textContent, tip: R(tip), spot: R(sp),
              btns, demo: l.dataset.demo || '', vw: innerWidth, vh: innerHeight, path: location.pathname + location.search}; }""")

def overlap(a, b):
    if not a or not b: return 0
    return max(0, min(a["x"]+a["w"], b["x"]+b["w"]) - max(a["x"], b["x"])) * max(0, min(a["y"]+a["h"], b["y"]+b["h"]) - max(a["y"], b["y"]))

def wait_step(pg, prev_key=None, prev_path=None, timeout=15):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try: s = state(pg)
        except Exception: s = None   # page navigating
        if s and s["key"] and (s["key"] != prev_key or s["path"] != prev_path) and pg.evaluate("!!document.querySelector('.tour.in:not(.t-pill)')"):
            pg.wait_for_timeout(250); s = state(pg)
            if s: return s
        pg.wait_for_timeout(120)
    return state(pg)

def btn(pg, label):
    return pg.locator(".tour:not(.t-pill) .t-acts button", has_text=label).last

def check_step(s, tdef):
    """Visibility/placement problems for one step."""
    issues = []
    if tdef.get("sel"):
        if "isn't on the page" in s["hint"] or "不在頁面上" in s["hint"]: issues.append("target missing")
        sp = s["spot"]
        if not sp: issues.append("no highlight")
        else:
            if sp["y"] + 8 < 0 or sp["y"] + sp["h"] - 8 > s["vh"] or sp["x"] < -8 or sp["x"] + sp["w"] > s["vw"] + 8:
                if sp["h"] < s["vh"] * 0.8: issues.append(f"highlight off screen {sp}")
            ov = overlap(sp, s["tip"])
            if ov > 0.25 * sp["w"] * sp["h"] and sp["h"] < s["vh"] * 0.6: issues.append(f"panel covers {int(100*ov/(sp['w']*sp['h']))}% of highlight")
    t = s["tip"]
    if t and (t["x"] < -1 or t["x"] + t["w"] > s["vw"] + 1 or t["y"] + t["h"] > s["vh"] + 1 or t["y"] < -1): issues.append(f"panel off screen {t}")
    return issues

def journey(pg, port, who, tour="student", lang="en", log=print, extra=None, start="home"):
    """who: dict(email,name,sid). extra: dict of behaviours keyed by step key: 'refresh', 'back', 'away'."""
    extra = extra or {}; recs = []; done_extra = set()
    B = f"http://localhost:{port}"
    pg.goto(B + "/"); pg.wait_for_load_state()
    D = json.loads(pg.locator("#tourdata").text_content())
    defs = {s["key"]: s for s in D["tours"][tour]}
    if start == "home":
        pg.locator(".howto-a button[data-tour]").nth(0 if tour == "student" else 1).click()
    s = wait_step(pg); prev = None; guard = 0
    while s and guard < 80:
        guard += 1
        k = s["key"]; tdef = defs.get(k, {})
        rec = dict(key=k, step=s["step"], title=s["title"], path=s["path"], issues=check_step(s, tdef), act=tdef.get("act"), t=time.time())
        try: pg.screenshot(path=f"{QA.SHOTS}/step_{pg.viewport_size['width']}_{k}.png")
        except Exception: pass
        if k in SHOTS:
            try: pg.screenshot(path=f"{QA.SHOTS}/fix_{pg.viewport_size['width']}_{k}.png")
            except Exception: pass
        recs.append(rec); log(f"  {s['step']:>14} {k:12} {s['path'][:28]:28} {'; '.join(rec['issues'])}")
        # behaviours that stress the tour (once each)
        if k in extra and k not in done_extra:
            done_extra.add(k); how = extra[k]
            if how == "refresh": pg.reload(); s2 = wait_step(pg, None, None); rec["after"] = s2 and s2["key"]; log(f"    refresh -> {rec['after']}"); s = s2; continue
            if how == "back":   # press Back three times, then Next back up
                for _ in range(3):
                    b = btn(pg, "Back" if lang == "en" else "上一步")
                    if b.count() and b.is_visible(): b.click(); s = wait_step(pg, s["key"], s["path"])
                rec["after"] = s and s["key"]; log(f"    back x3 -> {rec['after']}")
                continue
            if how == "away":
                pg.goto(B + "/discuss"); pg.wait_for_timeout(700)
                pill = pg.locator(".t-pill a"); rec["pill"] = pill.count() > 0
                if pill.count(): pill.click()
                else: pg.go_back()
                s = wait_step(pg, None, None); rec["after"] = s and s["key"]; log(f"    away (pill={rec['pill']}) -> {rec['after']}"); continue
        act = tdef.get("act"); before = (k, s["path"])
        tgt = pg.locator(".t-spot")  # not used for clicks; we click real elements
        sel = tdef.get("sel", "")
        def real():   # the element the tour is pointing at
            for one in sel.split("|"):
                loc = pg.locator(one)
                for i in range(loc.count()):
                    if loc.nth(i).is_visible(): return loc.nth(i)
            return None
        if act == "done":
            b = btn(pg, "Finish" if lang == "en" else "完成"); b.click(); pg.wait_for_timeout(400)
            rec["finished"] = state(pg) is None and pg.evaluate("localStorage.getItem('mm-tour')") is None
            log(f"    finished={rec['finished']}"); break
        elif act == "click":
            el = real(); el.click()
        elif act == "role":
            pg.locator(f"#lf .kind:has(input[value={'student' if tour == 'student' else 'faculty'}])").click(); pg.wait_for_timeout(300)
            btn(pg, "Next" if lang == "en" else "下一步").click()
        elif act == "input":
            el = real(); val = {"email": who["email"], "p_email": who["email"], "name": who["name"], "p_name": who["name"], "sid": who.get("sid", ""),
                                "pw": PW, "p_pw": PW, "pw2": PW, "p_pw2": PW, "skills": "python, figma, pitching", "p_dept": "Department of Computer Science",
                                "p_research": "machine learning, IoT"}.get(k, "x")
            nb = btn(pg, "Next" if lang == "en" else "下一步"); rec["next_disabled_before"] = nb.is_disabled() if nb.count() else None
            if k == "degree": el.select_option("bachelor")
            else: el.fill(""); el.type(val, delay=5)
            pg.wait_for_timeout(150); nb.click()
        elif act == "check":
            real().locator("input").first.check(); pg.wait_for_timeout(150); btn(pg, "Next" if lang == "en" else "下一步").click()
        elif act == "pick":
            pg.locator("#f .kinds .kind").first.click(); pg.wait_for_timeout(250); btn(pg, "Next" if lang == "en" else "下一步").click()
        elif act == "submit":
            if k in ("create", "p_create", "save", "p_rsave", "p_send"):
                real().click()
            else:   # publishing real content: a careful first-timer skips it, like the warning says
                pg.locator(".tour .t-skip").click()
        elif act in ("next", "go"):
            label = {"next": "Next", "go": "Take me there"}[act] if lang == "en" else {"next": "下一步", "go": "帶我過去"}[act]
            b = btn(pg, label)
            if not b.count():
                b = btn(pg, "Back to projects")
            b.click()
        pg.wait_for_timeout(200)
        s = wait_step(pg, before[0], before[1])
        if s and s["key"] in ("inbox", "p_inbox"):
            link = verify_link(port, who["email"]); rec["verify"] = bool(link)
            recs.append(dict(key=s["key"], step="", title=s["title"], path=s["path"], issues=check_step(s, {}), act="next", t=time.time()))
            log(f"  {'':>14} {s['key']:12} verify link found={bool(link)}")
            if link: pg.goto(link); s = wait_step(pg, None, None)
        if s and s["key"] == before[0] and s["path"] == before[1]:
            rec["issues"].append("did not advance"); log("    !! did not advance")
            try:
                pg.screenshot(path=f"{QA.SHOTS}/stuck_{k}.png")
                log("    url=" + pg.url + " invalid=" + str(pg.evaluate("[...document.querySelectorAll(':invalid')].map(e=>e.id||e.name).join(',')")) + " err=" + str(pg.locator('.err').all_text_contents()[:2]))
            except Exception as e: log(str(e))
            break
    return recs
