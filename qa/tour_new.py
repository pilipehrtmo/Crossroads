import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import common as QA
import subprocess, json
from playwright.sync_api import sync_playwright
import sys; B=f"http://localhost:{sys.argv[1] if len(sys.argv)>1 else 8021}"; PW="Tr0ub4dor&3xyz"
def q(s): return QA.q(s, None)
keys=json.loads(subprocess.run([os.getenv("QA_PYTHON", sys.executable),"-c","import json;from app import tour;print(json.dumps({k:[x['key'] for x in v] for k,v in tour.TOURS.items()}))"],capture_output=True,text=True,cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).stdout.strip().splitlines()[-1])
NEW={"student":[("s_interests","/profile"),("s_cv","/profile"),("d_foryou","/"),("d_comps","/"),("d_nav","/"),("a_record","/activity")],
     "prof":[("p_supervise","/advisor"),("p_more","/advisor")]}
who={"student":q("select email from \\\"user\\\" where name='Test Amy' order by id desc limit 1"),"prof":q("select email from \\\"user\\\" where name='Test Ben' order by id desc limit 1")}
res=[]; errs=[]
with sync_playwright() as p:
    br=p.chromium.launch()
    for lang in ("en","zh"):
        for vp,size in (("desk",{"width":1280,"height":900}),("phone",{"width":390,"height":844})):
            for t,steps in NEW.items():
                ctx=br.new_context(viewport=size,device_scale_factor=2 if vp=="phone" else 1); ctx.add_cookies([{"name":"lang","value":lang,"url":B}]); pg=ctx.new_page()
                pg.on("pageerror",lambda e: errs.append(str(e)))
                pg.goto(B+"/login"); pg.fill("input[name=email]",who[t]); pg.fill("input[name=password]",PW); pg.locator("form button").last.click(); pg.wait_for_load_state()
                uid=q(f"select id from \\\"user\\\" where email='{who[t]}'")
                for k,path in steps:
                    i=keys[t].index(k)
                    pg.evaluate("([t,i,u])=>{localStorage.setItem('mm-tour',JSON.stringify({t,i,floor:i,uid:+u,ts:Date.now()}));localStorage.setItem('mm-wn','99')}",[t,i,uid])
                    pg.goto(B+path); pg.wait_for_timeout(1500)
                    panel=pg.locator(".tour:not(.t-pill)")
                    txt=panel.first.inner_text() if panel.count() else ""
                    spot=pg.locator(".t-spot"); sv=spot.count()>0 and spot.first.is_visible()
                    bb=panel.first.bounding_box() if panel.count() else None
                    fits=bool(bb) and bb["x"]>=-1 and bb["x"]+bb["width"]<=size["width"]+1 and bb["y"]>=-1 and bb["y"]+bb["height"]<=size["height"]+1
                    nxt=panel.first.locator("button",has_text="Next" if lang=="en" else "下一步").count()>0 if panel.count() else False
                    ok=bool(txt) and sv and fits and nxt and "isn't on the page" not in txt and "目前不在頁面上" not in txt
                    res.append((ok,f"{lang}/{vp}/{k}")); print("ok  " if ok else "FAIL", lang, vp, k, "|", (txt.split("\n")[:3]) if not ok else txt.split("\n")[1][:50], "" if ok else dict(spot=sv,fits=fits,next=nxt))
                    if (vp=="phone" and lang=="zh") or (vp=="desk" and lang=="en"): pg.screenshot(path=f"{QA.SHOTS}/tour_{lang}_{vp}_{k}.png")
                ctx.close()
    br.close()
print("FAILS",[m for c,m in res if not c]); print("JS errors",errs[:3]); print(sum(c for c,_ in res),"/",len(res))
