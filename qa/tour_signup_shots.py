"""Sign-up tour: the university, department and student-document steps exist, point at a visible element and read
correctly in English and Chinese, on a laptop and a phone. Saves screenshots.
usage: python qa/tour_signup_shots.py <port> <out_dir>   (server with MULTI_SCHOOL=1 and the directory imported)"""
import sys, os
from playwright.sync_api import sync_playwright

PORT, OUT = sys.argv[1], sys.argv[2]
B = f"http://localhost:{PORT}"
os.makedirs(OUT, exist_ok=True)
bad = []
WANT = {"school": ("Your university", "你的學校 "), "dept": ("Department or major", "系所或主修"), "vdoc": ("Verify your student status", "驗證你的學生身分")}
with sync_playwright() as p:
    b = p.chromium.launch()
    for lang in ("en", "zh"):
        for dev, vp in (("desk", dict(viewport={"width": 1280, "height": 900}, device_scale_factor=2)),
                        ("phone", dict(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True))):
            ctx = b.new_context(**vp)
            ctx.add_cookies([{"name": "lang", "value": lang, "url": B}])
            pg = ctx.new_page(); pg.goto(B + "/signup"); pg.fill("#e", "tour.shot@gs.ncku.edu.tw")   # earlier steps filled, as in a real run
            for step in ("school", "dept", "vdoc"):
                if step == "dept":   # another university: the tour must point at the official-list department search
                    pg.keyboard.press("Escape")
                    pg.click("#inst-q"); pg.fill("#inst-q", "成功"); pg.wait_for_timeout(200); pg.keyboard.press("Enter"); pg.wait_for_timeout(800)
                pg.evaluate("s => { const x = document.createElement('button'); x.dataset.tour = 'student:' + s; document.body.append(x); x.click(); x.remove() }", step)
                pg.wait_for_timeout(1500)
                txt = pg.evaluate("[...document.querySelectorAll('.tour')].map(t => t.innerText).join(' | ')")
                title = WANT[step][1 if lang == "zh" else 0].strip()
                if step == "school" and ("Your email" in txt or "你的信箱" in txt): bad.append(f"{lang} {dev} school: stayed on the email step")
                if title not in txt: bad.append(f"{lang} {dev} {step}: bubble missing or wrong ({txt[:60]!r})")
                if "isn't on this page" in txt or "不在這個頁面" in txt: bad.append(f"{lang} {dev} {step}: target not found")
                print(lang, dev, step, "|", txt.replace("\n", " ")[:120], flush=True)
                pg.screenshot(path=f"{OUT}/tour_{step}_{lang}_{dev}.png")
            ctx.close()
    b.close()
print("problems:", bad or "none")
sys.exit(1 if bad else 0)
