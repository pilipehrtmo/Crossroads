import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import common as QA
import sys
from playwright.sync_api import sync_playwright
B=QA.B; errs=[]; out=[]
with sync_playwright() as p:
    br=p.chromium.launch()
    for lang in ("en","zh"):
      for name,size in (("desk",{"width":1280,"height":900}),("phone",{"width":390,"height":844})):
        ctx=br.new_context(viewport=size); ctx.add_cookies([{"name":"lang","value":lang,"url":B}]); pg=ctx.new_page()
        pg.on("pageerror",lambda e: errs.append(str(e)))
        pg.goto(B+"/login"); pg.fill("input[name=email]","ting-psy@demo.local"); pg.fill("input[name=password]","Tr0ub4dor&3xyz"); pg.locator("form button").last.click(); pg.wait_for_load_state()
        pg.goto(B+"/admin"); pg.wait_for_timeout(500)
        pg.click('[data-tour="admin:a_start"]'); pg.wait_for_timeout(600)
        titles=[]
        for i in range(12):
            t=pg.locator(".tour-card h3, .tour h3, [class*=tour] h3").first
            titles.append(t.inner_text() if t.count() else "?")
            if i==4: pg.screenshot(path=f"/tmp/claude-0/-home-claude/cb54ebef-8614-51cb-9597-ddb93223d729/scratchpad/at_{lang}_{name}.png")
            nb=pg.get_by_role("button",name="下一步" if lang=="zh" else "Next")
            fin=pg.get_by_role("button",name="完成" if lang=="zh" else "Finish")
            if nb.count() and nb.first.is_visible(): nb.first.click(); pg.wait_for_timeout(400)
            elif fin.count() and fin.first.is_visible(): fin.first.click(); pg.wait_for_timeout(400); titles.append("FINISHED"); break
            else: break
        # student tour must not leak to admin
        leak=pg.evaluate("Object.keys(JSON.parse(document.getElementById('tourdata').textContent).tours)")
        out.append((lang,name,len(titles),titles[0],titles[-2],titles[-1],leak))
        ctx.close()
    br.close()
for o in out: print(o)
print("errors:",errs)
