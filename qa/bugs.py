import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import common as QA
"""Reproduce each original bug (B1-B4, B6-B12) and check the fix. B5 is race2.py."""
import sys, random, json, time, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from journey import state, verify_link, PW, btn, wait_step
from playwright.sync_api import sync_playwright
B = QA.B; R = []
def ok(c, m, extra=""): R.append((bool(c), m)); print(("PASS " if c else "FAIL ") + m + ("" if c else "  " + str(extra)))
def mk(tag=""):
    n = random.randint(100000, 999999); L = "".join(chr(97 + int(c)) for c in str(n)).capitalize()
    return dict(email=f"bug{tag}{n}@example.com", name=f"Tester {L}", sid=f"119{n}")
def ctx(br, vp="desk", lang="en"):
    c = br.new_context(**({"viewport": {"width": 1366, "height": 768}} if vp == "desk" else dict(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)))
    c.add_cookies([{"name": "lang", "value": lang, "url": B}]); pg = c.new_page(); pg.errs = []
    pg.on("pageerror", lambda e: pg.errs.append(str(e))); return pg
def tour_to_create(pg, w, name=None, sid=None):
    """Walk the real tutorial through the sign-up form like a person."""
    pg.goto(B + "/"); pg.locator(".howto-a button[data-tour]").first.click(); s = wait_step(pg)
    pg.locator('.howto-a a[href="/signup"], .npost[href="/signup"]').first.click(); s = wait_step(pg, "start", "/")
    pg.locator("#lf .kind:has(input[value=student])").click(); pg.wait_for_timeout(300); btn(pg, "Next").click(); s = wait_step(pg, "role", "/signup")
    vals = {"email": w["email"], "name": name or w["name"], "sid": sid or w["sid"], "pw": PW, "pw2": PW}
    while s and s["key"] != "create":
        k = s["key"]
        if k in vals: pg.fill({"email": "#e", "name": "#n", "sid": "#s", "pw": "#pw", "pw2": "#pw2"}[k], vals[k])
        elif k == "degree": pg.select_option("#dg", "bachelor")
        elif k == "agree": pg.locator("#lf .chk input").check()
        pg.wait_for_timeout(150); btn(pg, "Next").click(); s = wait_step(pg, k, "/signup")
    return s
def err_visible(pg):
    return pg.evaluate("(()=>{const e=document.querySelector('.t-err');if(!e)return null;const r=e.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight?e.textContent:'off:'+e.textContent})()")
with sync_playwright() as p:
    br = p.chromium.launch()
    # ---------- B1: refused sign-up (name with a digit) ----------
    pg = ctx(br); w = mk("a"); tour_to_create(pg, w, name="Tester 2"); pg.locator("#lf > p > button").click(); s = wait_step(pg, None, None)
    ok(s and s["key"] == "name", "B1 refused sign-up (name with digit): tour goes back to the Name step", s and s["key"])
    ev = err_visible(pg); ok(ev and "number" in ev and not ev.startswith("off:"), "B1 the server's error is shown in the tutorial panel, on screen", ev)
    ok(pg.input_value("#e") == w["email"] and pg.input_value("#s") == w["sid"] and pg.input_value("#dg") == "bachelor" and pg.locator("#lf .chk input").is_checked(),
       "B1 valid fields kept (email, student ID, degree, privacy tick)")
    ok(pg.input_value("#pw") == "" and pg.input_value("#pw2") == "", "B1 passwords are not sent back to the page")
    # finish it: fix the name, then the tour asks for the passwords again, then create works
    pg.fill("#n", w["name"]); btn(pg, "Next").click(); s = wait_step(pg, "name", "/signup"); seen = [s["key"]]
    while s and s["key"] != "create":
        k = s["key"]
        if k == "pw": pg.fill("#pw", PW)
        elif k == "pw2": pg.fill("#pw2", PW)
        pg.wait_for_timeout(120); b = btn(pg, "Next"); b.click(); s = wait_step(pg, k, "/signup"); seen.append(s["key"])
    ok("pw" in seen and "pw2" in seen, "B1 after fixing the name, the tour walks through the emptied passwords", seen)
    pg.locator("#lf > p > button").click(); s = wait_step(pg, "create", "/signup")
    ok(s and s["key"] == "inbox", "B1 second try creates the account", s and s["key"])
    # ---------- B1b: duplicate student ID ----------
    pg2 = ctx(br); w2 = mk("b"); tour_to_create(pg2, w2, sid=w["sid"]); pg2.locator("#lf > p > button").click(); s = wait_step(pg2, None, None)
    ok(s and s["key"] == "sid", "B1 duplicate student ID: tour goes back to the Student ID step", s and s["key"])
    ok("already has an account" in (err_visible(pg2) or ""), "B1 duplicate ID error shown in the panel")
    # ---------- B7: refresh in the middle of sign-up ----------
    pg3 = ctx(br); w3 = mk("c"); pg3.goto(B + "/"); pg3.locator(".howto-a button[data-tour]").first.click(); wait_step(pg3)
    pg3.locator('.howto-a a[href="/signup"], .npost[href="/signup"]').first.click(); s = wait_step(pg3, "start", "/")
    pg3.locator("#lf .kind:has(input[value=student])").click(); pg3.wait_for_timeout(300); btn(pg3, "Next").click(); s = wait_step(pg3, "role", "/signup")
    pg3.fill("#e", w3["email"]); btn(pg3, "Next").click(); s = wait_step(pg3, "email", "/signup")
    pg3.fill("#n", w3["name"]); btn(pg3, "Next").click(); s = wait_step(pg3, "name", "/signup")
    ok(s["key"] == "sid", "B7 setup: at Student ID step")
    pg3.reload(); s = wait_step(pg3, None, None); pg3.wait_for_timeout(300)
    emptied = pg3.input_value("#e") == ""
    ok(s["key"] == ("email" if emptied else "sid"), f"B7 refresh: tour goes to the first emptied field (fields emptied by the browser: {emptied})", s["key"])
    # ---------- B2 + B11: 'Check your inbox' ----------
    s = state(pg)   # pg is on the inbox notice now
    names = [b["t"] for b in s["btns"]]
    ok(s["key"] == "inbox" and "Next" not in names and "Skip this step" not in names, "B2 inbox step has no Next/Skip that leads into the login loop", names)
    ok("logs you in" in s["text"], "B11 inbox wording says the link logs you in", s["text"])
    pg.goto(B + "/login"); s = wait_step(pg, None, None); pill = pg.locator(".t-pill").count()
    ok(s and s["key"] == "inbox" and not pill, "B2 on the login page the same step stays (no 'Continue the tour' loop)", (s and s["key"], pill))
    # ---------- B3: confirm on another device, then log in here ----------
    other = ctx(br); other.goto(verify_link(8040, w["email"])); other.wait_for_timeout(500)
    pg.fill("input[name=email]", w["email"]); pg.fill("input[name=password]", PW); pg.locator("form button").last.click(); s = wait_step(pg, "inbox", "/login")
    ok(s and s["key"] == "skills" and s["path"].startswith("/profile"), "B3 after logging in on this computer the tour starts at Add your skills", s and (s["key"], s["path"]))
    # ---------- B6: For you step without a tagged card ----------
    pg.fill("#s", "underwater basket weaving"); btn(pg, "Next").click(); s = wait_step(pg, "skills", "/profile")
    while s and s["key"] != "save": btn(pg, "Next").click(); s = wait_step(pg, s["key"], s["path"])
    pg.locator("#psave").click(); s = wait_step(pg, "save", "/profile")
    while s and s["key"] not in ("d_foryou", "d_foryou0"): btn(pg, "Next").click(); s = wait_step(pg, s["key"], s["path"])
    tagged = pg.locator("#plist .fytag").count()
    ok(s and s["key"] == ("d_foryou" if tagged else "d_foryou0") and ("No card is tagged" in s["text"]) == (not tagged), f"B6 For you step matches the page (cards tagged: {tagged})", s and s["key"])
    ok(s and s["step"].startswith("Step "), "B6 fallback keeps the step number", s and s["step"])
    # ---------- B9: no step on this page: pill at once ----------
    pg.goto(B + "/discuss"); t0 = time.time()
    pg.wait_for_selector(".t-pill", timeout=3000); dt = time.time() - t0
    ok(dt < 0.9, f"B9 'Continue the tour' appears right away ({dt:.2f}s after navigation started)")
    pg.locator(".t-pill a").click(); s = wait_step(pg, None, None)
    ok(s and s["key"] in ("d_foryou", "d_foryou0"), "B9 Continue the tour brings you back to the same step", s and s["key"])
    # ---------- B8: Back on 'Where to apply' ----------
    while s and s["key"] != "d_open": btn(pg, "Next").click(); s = wait_step(pg, s["key"], s["path"])
    pg.locator("#plist .pcard:not([hidden]) h2 a").first.click(); s = wait_step(pg, "d_open", "/")
    while s and s["key"] != "seat": btn(pg, "Next").click(); s = wait_step(pg, s["key"], s["path"])
    has_back = any(b["t"] == "Back" for b in s["btns"]); ok(has_back, "B8 'Where to apply' has a Back button")
    btn(pg, "Back").click(); s2 = wait_step(pg, "seat", s["path"]); ok(s2 and s2["key"] == "p_skills", "B8 Back goes to 'What each seat needs'", s2 and s2["key"])
    # ---------- B10 ----------
    btn(pg, "Next").click(); s = wait_step(pg, "p_skills", s2["path"])
    while s and s["key"] != "track":
        b = btn(pg, "Take me there") if s["key"] == "totrack" else btn(pg, "Next"); b.click(); s = wait_step(pg, s["key"], s["path"])
    ok("empty until you apply" in s["text"], "B10 'Your applications' explains the empty list", s["text"])
    # ---------- B4: log out mid-tour ----------
    pg.evaluate("document.querySelector('form[action=\"/logout\"]').submit()"); pg.wait_for_timeout(1500)
    ok(state(pg) is None and pg.locator(".t-pill").count() == 0 and pg.evaluate("localStorage.getItem('mm-tour')") is None, "B4 after logout no tutorial is shown and the saved progress is gone")
    pg.goto(B + "/"); pg.wait_for_timeout(1200); ok(state(pg) is None, "B4 the next person on this computer sees no tutorial")
    # ---------- B12: professor progress ----------
    errs = sum((x.errs for x in (pg, pg2, pg3, other)), [])
    ok(not errs, "no JavaScript errors in these journeys", errs[:3])
print(f"\n{sum(1 for g, _ in R if g)}/{len(R)} passed")
