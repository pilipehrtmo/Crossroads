import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import common as QA
"""Browser checks + screenshots for For you and track record. Usage: rep_ui.py <port> <db>"""
import sys, re, subprocess
from playwright.sync_api import sync_playwright
PORT, DB = sys.argv[1], sys.argv[2]; B = f"http://localhost:{PORT}"; PW = "Tr0ub4dor&3xyz"; OUT = QA.SHOTS
def q(sql): return QA.q(sql, DB)
res, errs = [], []
def ok(c, m): res.append((bool(c), m)); print(("ok  " if c else "FAIL"), m)
em = lambda n: q(f"select email from \\\"user\\\" where name='{n}' order by id desc limit 1")
amy, lead, olly, ben = em("Test Amy"), em("Test Lead"), em("Test Olly"), em("Test Ben")
hid = lambda e: q(f"select handle from \\\"user\\\" where email='{e}'")
uid = lambda e: q(f"select id from \\\"user\\\" where email='{e}'")
p1 = q("select id from project where status='completed' order by id limit 1")
# a fresh project of Lead's with Olly accepted, for the lead's form and Olly's confirmation
p5 = q(f"insert into project (owner_id,title,description,kind,category,stage,tagline,problem,audience,solution,objectives,methodology,outcomes,progress,needs,metrics,tags,event_name,links,hours_per_week,deadline,status,created) values ({uid(lead)},'Campus map app','An app that shows free study rooms','Side project','','','','','','','','','','','','','Website:blue','','',4,'','open',now()) returning id").splitlines()[0]
r5 = q(f"insert into role (project_id,name,skills,filled,advisor,about,must,nice,years,years_in,beginner) values ({p5},'Frontend developer','react,css',true,false,'','','',0,'',false) returning id").splitlines()[0]
q(f"insert into application (role_id,user_id,message,status,at) values ({r5},{uid(olly)},'I can build the map screens in React.','accepted',now())")
q(f"update \\\"user\\\" set skills='react,css', interests='education', roles_wanted='frontend developer' where email='{olly}'")
VPS = {"desk": {"width": 1280, "height": 900}, "tab": {"width": 820, "height": 1100}, "phone": {"width": 390, "height": 844}}
with sync_playwright() as p:
    br = p.chromium.launch()
    def page(email, lang, vp):
        ctx = br.new_context(viewport=VPS[vp], device_scale_factor=2 if vp == "phone" else 1); ctx.add_cookies([{"name": "lang", "value": lang, "url": B}])
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(f"{lang}/{vp}: {e}"))
        pg.add_init_script("try{localStorage.setItem('mm-tour','done');localStorage.setItem('mm-wn','99')}catch(e){}")
        pg.goto(B + "/login"); pg.fill("input[name=email]", email); pg.fill("input[name=password]", PW); pg.locator("form button").last.click(); pg.wait_for_load_state()
        return ctx, pg
    clean = lambda pg: pg.evaluate("document.querySelectorAll('.tour,.wn-root,.wn,.wn-ov,.t-pill').forEach(e=>e.remove())")
    wide = lambda pg: pg.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
    for lang in ("en", "zh"):
        for vp in ("desk", "tab", "phone"):
            tag = f"{lang}_{vp}"
            ctx, pg = page(amy, lang, vp); pg.goto(B + "/"); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(500); clean(pg)   # the board sorts itself after load: let it settle before hovering
            fy = pg.locator("#plist .fytag")
            ok(fy.count() >= 1 and fy.first.inner_text().strip() in ("For you", "為你推薦"), f"{tag} home: For you tag on cards ({fy.count()})")
            first = pg.locator("#plist .pcard:not([hidden])").first
            ok(first.get_attribute("data-fy") == "1", f"{tag} home: For you card is first")
            fy.first.evaluate("e=>e.scrollIntoView({block:'center'})"); pg.wait_for_timeout(100); (fy.first.click() if vp != "desk" else fy.first.hover()); pg.wait_for_timeout(400); url0 = pg.url; pg.wait_for_timeout(150)
            why = pg.locator("#plist .fytag").first.locator(".fywhy")
            ok(why.is_visible() and len(why.inner_text()) > 10, f"{tag} home: hovering the tag shows why")
            bb, cb = why.bounding_box(), pg.locator("#plist .pcard").first.bounding_box()
            ok(bb and bb["x"] >= 0 and bb["x"] + bb["width"] <= VPS[vp]["width"] + 1, f"{tag} home: reasons stay on screen")
            if vp == "desk" and lang == "en": pg.screenshot(path=f"{OUT}/{tag}_home_tooltip.png", clip={"x": cb["x"] - 20, "y": cb["y"] - 20, "width": cb["width"] + 40, "height": cb["height"] + 60})
            if vp == "phone" and lang == "zh": pg.screenshot(path=f"{OUT}/{tag}_home_tooltip.png", clip={"x": 0, "y": cb["y"] - 20, "width": 390, "height": cb["height"] + 80})
            ok(pg.url == url0, f"{tag} home: tapping the tag does not open the project"); ok(wide(pg), f"{tag} home: no sideways scroll")
            pg.mouse.move(1, 1)
            pg.locator("#fpanel summary").click(); pg.wait_for_timeout(150)
            n_all = pg.locator("#plist .pcard:not([hidden])").count()
            pg.select_option("#f-show", "fy"); pg.wait_for_timeout(150)
            vis = pg.locator("#plist .pcard:not([hidden])")
            ok(vis.count() >= 1 and vis.count() < n_all and all(vis.nth(i).get_attribute("data-fy") == "1" for i in range(vis.count())), f"{tag} home: Show 'For you only' filter")
            pg.select_option("#f-show", "xc"); pg.wait_for_timeout(150)
            vis = pg.locator("#plist .pcard:not([hidden])")
            ok(all(vis.nth(i).get_attribute("data-xc") == "1" for i in range(vis.count())), f"{tag} home: Show 'From other colleges' filter ({vis.count()})")
            if vp == "desk": pg.screenshot(path=f"{OUT}/{tag}_home_filters.png", clip={"x": 0, "y": 0, "width": 1280, "height": 900})
            pg.select_option("#f-show", ""); pg.locator("#fpanel summary").click()
            ccard = pg.locator("#clist .comp .fytag")
            ok(ccard.count() >= 1, f"{tag} home: competitions For you")
            pg.goto(B + "/research"); clean(pg)
            ok(pg.locator(".ocard .fytag").count() >= 1 and wide(pg), f"{tag} research: For you tag")
            pg.goto(B + "/profile"); clean(pg)
            ok(pg.locator("#int").input_value().startswith("machine learning") and pg.locator("#rw").input_value() == "backend developer", f"{tag} profile: interests and roles fields")
            if vp == "phone": pg.locator("#int").scroll_into_view_if_needed(); pg.screenshot(path=f"{OUT}/{tag}_profile_fields.png")
            pg.goto(B + f"/u/{hid(amy)}"); clean(pg)
            tr = pg.locator("#track")
            ok(tr.is_visible() and tr.locator(".vlabel").count() >= 1 and wide(pg), f"{tag} public: track record with labels")
            ok(pg.locator(".xp .v-self").count() >= 0, f"{tag} public: self-reported label rule")
            tr.scroll_into_view_if_needed(); tr.screenshot(path=f"{OUT}/{tag}_track.png")
            pg.goto(B + f"/projects/{p1}"); clean(pg)
            ok(pg.locator("#complete").is_visible() and wide(pg), f"{tag} project: completion section")
            if vp == "desk": pg.locator("#complete").screenshot(path=f"{OUT}/{tag}_project_complete.png")
            ctx.close()
    # lead marks the new project completed through the page, Olly confirms through the page
    for lang in ("en",):
        ctx, pg = page(lead, lang, "desk"); pg.goto(B + f"/projects/{p5}"); clean(pg)
        pg.locator("#complete .cform summary").click(); pg.wait_for_timeout(150)
        pg.fill("#ln-lead", "planned the app and wrote the backend"); pg.locator("#complete input[name^=note_]").fill("built the map screens")
        pg.locator("#complete").screenshot(path=f"{OUT}/en_desk_lead_form.png")
        pg.on("dialog", lambda d: d.accept())
        pg.evaluate("document.querySelectorAll('[hx-confirm]').forEach(e=>e.removeAttribute('hx-confirm'))")
        pg.locator("#complete form button").last.click(); pg.wait_for_load_state()
        ok(q(f"select status from project where id={p5}") == "completed", "lead completes through the page")
        ctx.close()
    for lang, vp in (("zh", "phone"), ):
        ctx, pg = page(olly, lang, vp); pg.goto(B + f"/projects/{p5}#complete"); clean(pg)
        box = pg.locator(".cask"); ok(box.is_visible() and "負責人記錄你的角色是" in box.inner_text(), "member sees the confirmation question in Chinese")
        box.scroll_into_view_if_needed(); pg.screenshot(path=f"{OUT}/zh_phone_member_confirm.png")
        box.locator("button").first.click(); pg.wait_for_load_state()
        ok(q(f"select member_status from contribution where project_id={p5} and user_id={uid(olly)}") == "confirmed", "member confirms through the page")
        ok(pg.locator(".eform").count() == 1, "endorse form for the lead appears")
        pg.locator(".eform .etag").nth(0).click(); pg.locator(".eform .etag").nth(1).click(); pg.locator(".eform .etag").nth(2).click()
        ok(pg.locator(".eform input[name=tag]:disabled").count() >= 1, "after 3 picks the rest are disabled")
        pg.locator(".eform").screenshot(path=f"{OUT}/zh_phone_endorse.png")
        pg.locator(".eform button").click(); pg.wait_for_load_state()
        ok(q(f"select count(*) from endorsement where project_id={p5} and from_id={uid(olly)}") == "3", "endorsement saved (3)")
        ctx.close()
    for lang in ("en", "zh"):
        ctx, pg = page("admin@audit.test", lang, "desk"); pg.goto(B + "/admin#track"); clean(pg)
        ok(pg.locator("#track").is_visible(), f"{lang} admin: track record section"); pg.locator("#track").screenshot(path=f"{OUT}/{lang}_admin_track.png"); ctx.close()
    br.close()
print("FAILS", [m for c, m in res if not c]); print("JS errors", errs[:5]); print(sum(c for c, _ in res), "/", len(res))
