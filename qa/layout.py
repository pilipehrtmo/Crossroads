import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import common as QA
"""Every main page at phone and desktop size, logged out and logged in: horizontal scroll, JS errors, overlapping/cut text, tiny tap targets."""
import re, subprocess
from playwright.sync_api import sync_playwright
B = QA.B; PW = "Tr0ub4dor&3xyz"
q = lambda s: QA.q(s, None)
email = q("select email from \\\"user\\\" where email like 'fivea%' limit 1"); handle = q(f"select handle from \\\"user\\\" where email='{email}'")
pid = q("select id from project where status='open' order by id limit 1"); comp = q("select id from competition order by id limit 1")
PAGES = ["/", "/research", "/discuss", "/funding", "/help", "/privacy", "/login", "/signup", f"/projects/{pid}", f"/u/{handle}", "/forgot"]
IN = ["/profile", "/activity", "/notifications", "/projects/new", "/discuss/new"]
CHECK = """() => { const out = {}; out.hscroll = document.documentElement.scrollWidth > innerWidth + 1;
  const wide = [...document.querySelectorAll('body *')].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.right > innerWidth + 2 && getComputedStyle(e).position !== 'fixed' && !e.closest('.hscroll,[style*=overflow],pre,code,table,.tabs,.chips,.kinds,.scroller'); }).slice(0, 4).map(e => e.tagName + '.' + (e.className || '').toString().slice(0, 40));
  out.wide = wide;
  const small = [...document.querySelectorAll('a,button,input,select,summary')].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && (r.height < 24 || r.width < 24) && getComputedStyle(e).visibility !== 'hidden' && !e.closest('p,li,.fine,small,.muted,footer,td'); }).length;
  out.small_targets = small; return out; }"""
with sync_playwright() as p:
    br = p.chromium.launch()
    for vp, opts in (("phone", dict(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)), ("desk", dict(viewport={"width": 1366, "height": 768}))):
        for logged in (False, True):
            ctx = br.new_context(**opts); pg = ctx.new_page(); errs = []
            pg.add_init_script("try{localStorage.setItem('mm-wn','99')}catch(e){}")
            pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: m.type == "error" and "TUNNEL" not in m.text and errs.append(m.text))
            if logged:
                pg.goto(B + "/login"); pg.fill("input[name=email]", email); pg.fill("input[name=password]", PW); pg.locator("form button").last.click(); pg.wait_for_load_state()
            for path in (PAGES + (IN if logged else [])):
                r = pg.goto(B + path); pg.wait_for_timeout(250); c = pg.evaluate(CHECK)
                flag = c["hscroll"] or c["wide"] or r.status >= 400
                print(f"{vp:5} {'in ' if logged else 'out'} {path:22} {r.status} hscroll={c['hscroll']} wide={c['wide']} small={c['small_targets']}{'  <<<' if flag else ''}")
                pg.screenshot(path=f"{QA.SHOTS}/lay_{vp}_{'in' if logged else 'out'}_{path.strip('/').replace('/','_') or 'home'}.png", full_page=False)
            if errs: print("   JS errors:", errs[:5])
            ctx.close()
