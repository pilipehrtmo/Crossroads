import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import common as QA
import re, subprocess
from playwright.sync_api import sync_playwright
B=QA.B
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={"width":1280,"height":900})
    errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B+"/"); n=lambda: pg.eval_on_selector_all("article.card, .pcard, [data-deg]", "els=>els.filter(e=>e.dataset.deg!==undefined && e.offsetParent).length")
    before=n(); pg.select_option("#f-deg","phd"); after=n()
    print("board filter", before, "->", after, "url", pg.url)
    pg.reload(); print("after reload", n(), pg.eval_on_selector("#f-deg","e=>e.value"))
    pg.goto(B+"/signup"); pg.locator("#dg").scroll_into_view_if_needed(); pg.screenshot(path="shots/deg_signup.png")
    m=p.chromium.launch().new_page(viewport={"width":390,"height":844}); m.goto(B+"/signup"); m.locator("#dg").scroll_into_view_if_needed(); m.screenshot(path="shots/deg_signup_m.png")
    print("errors", errs)
    b.close()
