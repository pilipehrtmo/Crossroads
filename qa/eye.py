import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import common as QA
import sys
from playwright.sync_api import sync_playwright
B = "http://localhost:%s" % sys.argv[1]
def state(pg, sel): return pg.eval_on_selector(sel, "e=>e.type")
with sync_playwright() as p:
    br = p.chromium.launch()
    for mobile in (False, True):
        ctx = br.new_context(**(p.devices["iPhone 13"] if mobile else {"viewport": {"width": 1280, "height": 800}}))
        pg = ctx.new_page()
        for path in ("/login", "/signup"):
            pg.goto(B + path); pg.wait_for_load_state("networkidle")
            pws = pg.locator("input[data-eye]")
            n = pws.count()
            for i in range(n):
                inp = pws.nth(i); eye = inp.locator("xpath=following-sibling::button[contains(@class,'pw-eye')]")
                res = []
                # A: plain click
                (eye.tap() if mobile else eye.click()); res.append(inp.evaluate("e=>e.type"))
                (eye.tap() if mobile else eye.click()); res.append(inp.evaluate("e=>e.type"))
                # B: typed, focused
                inp.fill("Secret123!"); inp.focus()
                (eye.tap() if mobile else eye.click()); res.append(inp.evaluate("e=>e.type"))
                (eye.tap() if mobile else eye.click()); res.append(inp.evaluate("e=>e.type"))
                # C: email with typo focused, then eye
                em = pg.locator("input[type=email], input[name=email]").first
                if em.count():
                    em.fill("abc@gmial.com"); em.focus()
                    (eye.tap() if mobile else eye.click()); res.append("C:" + inp.evaluate("e=>e.type"))
                    em.fill(""); 
                print(("phone" if mobile else "desk"), path, i, res)
        ctx.close()
    br.close()
