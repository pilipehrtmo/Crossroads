"""Browser checks for the bilingual university / department search and the sign-up document step.
usage: python qa/directory_e2e.py <port> <db> <shots_dir>   (server started with MULTI_SCHOOL=1, directory imported)"""
import io, os, sys, json, subprocess, time
from playwright.sync_api import sync_playwright

PORT, DB, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
BASE = f"http://localhost:{PORT}"
os.makedirs(OUT, exist_ok=True)
PW = "Qa-dir-test-2026!"
fails, oks = [], []


def ok(cond, what):
    (oks if cond else fails).append(what); print(("PASS " if cond else "FAIL ") + what, flush=True)


def sql(q):
    return subprocess.run(["psql", "-h", "127.0.0.1", "-p", "5433", "-U", "postgres", DB, "-Atc", q], capture_output=True, text=True).stdout.strip()


def png(path):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (900, 560), "white"); d = ImageDraw.Draw(im)
    d.rectangle([20, 20, 880, 540], outline="black", width=4); d.text((60, 60), "STUDENT ID  TEST CARD  E1234567", fill="black")
    im.save(path, "PNG")


def options(page):
    return page.eval_on_selector_all("#inst-l .cbo", "els => els.map(e => e.textContent)")


def search(page, q):
    page.fill("#inst-q", ""); page.type("#inst-q", q, delay=15); page.wait_for_timeout(120)
    return options(page)


stamp = str(int(time.time()))[-6:]
card = os.path.join(OUT, "card.png"); png(card)
with sync_playwright() as p:
    b = p.chromium.launch()
    for lang in ("en", "zh"):
        ctx = b.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
        ctx.add_cookies([{"name": "lang", "value": lang, "url": BASE}])
        pg = ctx.new_page(); pg.goto(BASE + "/signup")
        pg.click("#inst-q")
        first = options(pg)
        ok(first and "國立清華大學" in first[0], f"[{lang}] no query: NTHU first ({first[0][:30] if first else None})")
        ok(len(first) == 139, f"[{lang}] no query lists all 139 ({len(first)})")
        r = search(pg, "NTU"); ok(r and r[0].startswith("國立臺灣大學"), f"[{lang}] 'NTU' -> NTU first ({r[0][:20] if r else None})")
        pg.screenshot(path=f"{OUT}/uni_search_ntu_{lang}.png")
        r = search(pg, "清華"); ok(r and r[0].startswith("國立清華大學"), f"[{lang}] '清華' -> NTHU")
        pg.screenshot(path=f"{OUT}/uni_search_zh_query_{lang}.png")
        r = search(pg, "National Taiwan"); ok(len(r) >= 5 and all("National Taiwan" in x for x in r[:5]), f"[{lang}] 'National Taiwan' -> {len(r)} English matches")
        r = search(pg, "cheng kung"); ok(r and r[0].startswith("國立成功大學"), f"[{lang}] 'cheng kung' (lower case) -> NCKU")
        r = search(pg, "台灣大學"); ok(r and r[0].startswith("國立臺灣大學"), f"[{lang}] '台灣大學' (台 for 臺) -> NTU")
        r = search(pg, "natoinal tsing hua"); ok(r and r[0].startswith("國立清華大學"), f"[{lang}] typo 'natoinal tsing hua' -> NTHU")
        r = search(pg, "tsinghua"); ok(r and r[0].startswith("國立清華大學"), f"[{lang}] 'tsinghua' (no space) -> NTHU")
        r = search(pg, "NYCU"); ok(r and r[0].startswith("國立陽明交通大學"), f"[{lang}] 'NYCU' -> NYCU")
        search(pg, "xyzzyqq"); empty = pg.inner_text("#inst-l"); ok("No university" in empty or "沒有" in empty or "找不到" in empty, f"[{lang}] empty state shown")
        pg.screenshot(path=f"{OUT}/uni_empty_{lang}.png")
        pg.keyboard.press("Escape"); ok(pg.is_hidden("#inst-l"), f"[{lang}] Escape closes the list")
        search(pg, "成功"); pg.keyboard.press("ArrowDown"); pg.keyboard.press("ArrowUp"); pg.keyboard.press("Enter")
        ok(pg.input_value("#inst") == "0005", f"[{lang}] keyboard Enter stores moe_code 0005 (got {pg.input_value('#inst')})")
        ok(pg.is_visible("#ut") and pg.is_hidden("#dsel") if pg.query_selector("#dsel") else pg.is_visible("#ut"), f"[{lang}] non-NTHU shows the department search")
        pg.wait_for_function("document.querySelector('#ut-st') && !/Loading|載入/.test(document.querySelector('#ut-st').textContent)", timeout=8000)
        pg.click("#ut"); pg.type("#ut", "資訊", delay=20); pg.wait_for_timeout(150)
        u = pg.eval_on_selector_all("#ut-l .cbo", "els => els.map(e => e.textContent)")
        ok(len(u) >= 2, f"[{lang}] department search '資訊' at NCKU -> {len(u)} options")
        pg.screenshot(path=f"{OUT}/dept_search_{lang}.png")
        pg.fill("#ut", ""); pg.type("#ut", "electrical", delay=15); pg.wait_for_timeout(150)
        u2 = pg.eval_on_selector_all("#ut-l .cbo", "els => els.map(e => e.textContent)")
        ok(u2 and ("Use what I typed" in u2[-1] or "使用" in u2[-1]), f"[{lang}] no English list for NCKU: offers 'Use what I typed'")
        pg.screenshot(path=f"{OUT}/dept_custom_{lang}.png")
        # clear button
        pg.click("#inst-q"); pg.click("[data-schoolpick] .cbx")
        ok(pg.input_value("#inst") == "", f"[{lang}] clear button empties the university")
        ctx.close()

    # NTU's list must contain only NTU units; the English-taught pairs show both languages
    api = json.loads(subprocess.run(["curl", "-s", "--noproxy", "*", BASE + "/api/units/0022"], capture_output=True, text=True).stdout)
    n22 = sql("select count(*) from academicunit a join institution i on i.id=a.institution_id where i.moe_code='0022' and a.active")
    ok(len(api["units"]) == int(n22), f"/api/units/0022 returns exactly NTUST's {n22} units")
    ok(any(u["en"] for u in api["units"]), "NTUST has verified English pairs from the MOE English-taught list")
    nthu = json.loads(subprocess.run(["curl", "-s", "--noproxy", "*", BASE + "/api/units/0002"], capture_output=True, text=True).stdout)
    ok(nthu["catalog"] == "nthu" and nthu["units"] == [], "NTHU keeps its reviewed catalog (API returns no MOE units)")

    # ---------- full sign-ups ----------
    def signup(ctx, email, name, sid, school, dept=None, typed=None, doc=False, skip=False, nthu_dept=None):
        pg = ctx.new_page(); pg.goto(BASE + "/signup")
        pg.fill("#e", email); pg.fill("#n", name)
        pg.click("#inst-q"); search(pg, school); pg.keyboard.press("Enter")
        pg.fill("#s", sid); pg.select_option("#dg", "bachelor")
        if nthu_dept:
            pg.click("#dq-dpw"); pg.type("#dq-dpw", nthu_dept, delay=15); pg.keyboard.press("Enter")
        elif dept or typed:
            pg.wait_for_function("!/Loading|載入/.test(document.querySelector('#ut-st').textContent)", timeout=8000)
            pg.click("#ut"); pg.type("#ut", dept or typed, delay=15); pg.wait_for_timeout(150)
            if dept: pg.keyboard.press("Enter")
            else:
                pg.click("#ut-l .cbtyped") if pg.query_selector("#ut-l .cbtyped") else pg.keyboard.press("Escape")
        if skip: pg.check("input[name=vmode][value=skip]")
        elif doc:
            pg.select_option("#vdt", "student_card"); pg.set_input_files("#vf", card); pg.check("#vcons input")
        pg.fill("#pw", PW); pg.fill("#pw2", PW); pg.check("input[name=agree]")
        return pg

    ctx = b.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
    pg = signup(ctx, f"a{stamp}@gs.ncku.edu.tw", "Dir Tester Alpha", f"E1{stamp}", "成功", dept="資訊工程", doc=True)
    pg.screenshot(path=f"{OUT}/signup_upload_en.png", full_page=True)
    ok("card.png" in pg.inner_text("#vft"), "selected filename shown")
    pg.click("#lf button:not([type=button])"); pg.wait_for_load_state("networkidle"); time.sleep(.5)
    pg.screenshot(path=f"{OUT}/signup_after_upload_en.png", full_page=True)
    row = sql(f"select i.moe_code, a.unit_key, a.unit_text, a.review, u.student_status, u.verified from \"user\" u join affiliation a on a.user_id=u.id and a.current join institution i on i.id=a.institution_id where u.email='a{stamp}@gs.ncku.edu.tw'")
    print("   ", row)
    parts = row.split("|")
    ok(len(parts) == 6 and parts[0] == "0005" and parts[1].startswith("moe:") and parts[3] in ("", "id_format"), "NCKU sign-up stores institution 0005 + official unit key")
    ok(len(parts) == 6 and parts[4] == "needs_review" and parts[5] == "f", "upload puts the account in needs_review, NOT verified")
    sv = sql(f"select count(*), max(storage_key) like 'verify/%' from studentverification s join \"user\" u on u.id=s.user_id where u.email='a{stamp}@gs.ncku.edu.tw'")
    ok(sv.startswith("1|t"), f"exactly one private verification record ({sv})")
    unitinst = sql(f"select i.moe_code from academicunit au join institution i on i.id=au.institution_id where 'moe:'||au.unit_code='{parts[1] if len(parts) > 1 else ''}' and i.moe_code='0005'")
    ok(unitinst == "0005", "linked unit belongs to NCKU (no cross-institution leak)")
    ctx.close()

    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True)
    pg = signup(ctx, f"b{stamp}@ntu.edu.tw", "Dir Tester Beta", f"B1{stamp}", "NTU", typed="Department of Imaginary Studies", skip=True)
    pg.screenshot(path=f"{OUT}/signup_skip_mobile_en.png", full_page=True)
    ok(pg.is_visible("#vskipnote"), "skip shows the Pending explanation")
    pg.click("#lf button:not([type=button])"); pg.wait_for_load_state("networkidle"); time.sleep(.5)
    row = sql(f"select i.moe_code, a.unit_key, a.unit_text, a.review, u.student_status from \"user\" u join affiliation a on a.user_id=u.id and a.current join institution i on i.id=a.institution_id where u.email='b{stamp}@ntu.edu.tw'")
    print("   ", row); parts = row.split("|")
    ok(len(parts) == 5 and parts[0] == "0003" and parts[1] == "" and "unit" in parts[3], "typed department is stored as user-entered and flagged for review")
    ok(len(parts) == 5 and parts[4] in ("", "pending"), "skipped upload: status stays Pending")
    ctx.close()

    # NTHU path unchanged (reviewed catalog picker)
    ctx = b.new_context(viewport={"width": 1280, "height": 900})
    pg = signup(ctx, f"c{stamp}@m114.nthu.edu.tw", "Dir Tester Gamma", "11" + stamp[-6:].rjust(7, "0"), "清華", nthu_dept="資工", skip=True)
    pg.click("#lf button:not([type=button])"); pg.wait_for_load_state("networkidle"); time.sleep(.5)
    row = sql(f"select i.moe_code, a.unit_key, u.dept_id from \"user\" u join affiliation a on a.user_id=u.id and a.current join institution i on i.id=a.institution_id where u.email='c{stamp}@m114.nthu.edu.tw'")
    print("   ", row); parts = row.split("|")
    ok(len(parts) == 3 and parts[0] == "0002" and parts[1] == parts[2] and parts[1] != "", "NTHU sign-up keeps the NTHU catalog department")
    ctx.close()

    # profile: the NCKU student changes department from the official list; the university can't be changed there
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
    pg = ctx.new_page(); pg.goto(BASE + "/login"); pg.fill("input[name=email]", f"a{stamp}@gs.ncku.edu.tw"); pg.fill("input[name=password]", PW)
    pg.click("#lf button:not([type=button])"); pg.wait_for_load_state("networkidle")
    pg.goto(BASE + "/profile")
    ok("國立成功大學" in pg.inner_text(".pinst"), "profile shows the university read-only")
    ok(pg.query_selector("select[name=institution]") is None, "profile has no university field")
    pg.wait_for_function("!/Loading|載入/.test(document.querySelector('#ut-st').textContent)", timeout=8000)
    pg.click("#ut"); pg.fill("#ut", ""); pg.type("#ut", "電機工程", delay=15); pg.wait_for_timeout(150); pg.keyboard.press("Enter")
    pg.screenshot(path=f"{OUT}/profile_dept_en.png")
    pg.evaluate("document.getElementById('pform').requestSubmit()"); pg.wait_for_load_state("networkidle")
    row = sql(f"select a.unit_text, a.unit_key, u.faculty from \"user\" u join affiliation a on a.user_id=u.id and a.current where u.email='a{stamp}@gs.ncku.edu.tw'")
    print("   ", row)
    ok("電機" in row and "moe:" in row, "profile edit links the new official unit")
    # logout/login persistence
    ctx.clear_cookies(); pg.goto(BASE + "/login"); pg.fill("input[name=email]", f"a{stamp}@gs.ncku.edu.tw"); pg.fill("input[name=password]", PW)
    pg.click("#lf button:not([type=button])"); pg.wait_for_load_state("networkidle"); pg.goto(BASE + "/profile")
    ok("電機" in pg.input_value("#ut"), "department persists after logging in again")
    # access control
    for path in ("/admin/affiliations", "/admin/verification", "/admin/verification/1/file"):
        r = pg.request.get(BASE + path); ok(r.status == 403, f"student GET {path} -> {r.status}")
    r = pg.request.post(BASE + "/admin/affiliations/1", form={"action": "keep"}); ok(r.status in (403,), f"student POST /admin/affiliations/1 -> {r.status} (CSRF/403)")
    ctx.close()

    # zh mobile screenshots of the pickers
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True)
    ctx.add_cookies([{"name": "lang", "value": "zh", "url": BASE}])
    pg = ctx.new_page(); pg.goto(BASE + "/signup"); pg.click("#inst-q"); search(pg, "成大")
    pg.screenshot(path=f"{OUT}/uni_search_mobile_zh.png"); search(pg, "高雄"); pg.keyboard.press("Enter")
    pg.wait_for_timeout(600); pg.click("#ut"); pg.type("#ut", "系", delay=15); pg.wait_for_timeout(150)
    pg.screenshot(path=f"{OUT}/dept_search_mobile_zh.png")
    w = pg.evaluate("document.documentElement.scrollWidth"); ok(w <= 390, f"mobile: no horizontal scroll ({w}px)")
    pg.locator("#vstep").scroll_into_view_if_needed(); pg.screenshot(path=f"{OUT}/signup_upload_mobile_zh.png")
    ctx.close()
    b.close()

print(f"\n{len(oks)} passed, {len(fails)} failed")
for f in fails: print("  FAIL", f)
sys.exit(1 if fails else 0)
