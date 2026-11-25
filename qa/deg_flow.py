import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import common as QA
"""HTTP checks of the degree field. Usage: deg_flow.py <port> <db>"""
import sys, re, subprocess, random, httpx
PORT, DB = sys.argv[1], sys.argv[2]; B = f"http://localhost:{PORT}"; PW = "Tr0ub4dor&3xyz"; R = random.randint(10000, 99999)
res = []
def ok(c, m, extra=""): res.append((bool(c), m)); print(("ok  " if c else "FAIL"), m, "" if c else extra)
def q(sql): return QA.q(sql, DB)
def csrf(c, path="/signup"): return re.search(r'name="csrf" value="([^"]+)"', c.get(path).text)[1]
def signup(tag, degree, n):
    c = httpx.Client(base_url=B, follow_redirects=True, timeout=30)
    email = f"{tag}{R}@example.com"
    d = dict(csrf=csrf(c), role="student", email=email, name=f"Test {tag.capitalize()}", student_id=f"{R}{n:04d}", password=PW, password2=PW, agree="1", dept_sel="eecs-cs", degree=degree)
    r = c.post("/signup", data=d)
    return c, r, q(f"select id from \\\"user\\\" where email='{email}'")
c, r, uid = signup("nodeg", "", 1)
ok(not uid and "Choose your degree" in r.text, "signup without degree refused with a clear message")
ok('value="eecs-cs"' in r.text and 'selected' in r.text, "form keeps what was typed")
c, r, uid = signup("bogus", "postdoc", 2)
ok(not uid, "made-up degree refused")
M, r, mid = signup("mia", "master", 3)
ok(mid and q(f"select degree from \\\"user\\\" where id={mid}") == "master", "master's signup stored")
h = q(f"select handle from \\\"user\\\" where id={mid}")
pub = httpx.get(f"{B}/u/{h}").text
ok("Master&#39;s · " in pub or "Master's · " in pub, "public page shows Master's · department")
P, r, pid = signup("phil", "phd", 4)
# profile change
pg = M.get("/profile").text
ok('id="dg"' in pg and 'value="master" selected' in pg, "profile shows degree select with the current value")
ok('<option value="">Choose…</option>' not in pg.split('id="dg"')[1][:200], "no empty option once a degree is set")
form = dict(csrf=csrf(M, "/profile"), name="Test Mia", hours="6", degree="phd")
M.post("/profile", data=form)
ok(q(f"select degree from \\\"user\\\" where id={mid}") == "phd", "profile save changes degree")
form["degree"] = ""; form["csrf"] = csrf(M, "/profile"); M.post("/profile", data=form)
ok(q(f"select degree from \\\"user\\\" where id={mid}") == "phd", "empty degree on profile keeps the old one")
form["degree"] = "xyz"; form["csrf"] = csrf(M, "/profile"); r = M.post("/profile", data=form)
ok("Choose your degree" in r.text and q(f"select degree from \\\"user\\\" where id={mid}") == "phd", "bad degree on profile refused, nothing saved")
# old account without degree: profile shows Choose…, public page shows only department
q(f"update \\\"user\\\" set degree='' where id={pid}")
pp = P.get("/profile").text
ok('<option value="">Choose…</option>' in pp, "account without degree sees Choose…")
h2 = q(f"select handle from \\\"user\\\" where id={pid}")
pub2 = httpx.get(f"{B}/u/{h2}").text
ok("PhD" not in pub2 and "Computer Science" in pub2, "no degree = department only")
# zh
zh = httpx.get(f"{B}/u/{h}", cookies={"lang": "zh"}).text
zh2 = httpx.Client(base_url=B, follow_redirects=True)
zh2.get("/lang/zh"); t = zh2.get(f"/u/{h}").text
ok("博士班 · " in t, "Chinese label on public page", t[:0])
s = httpx.Client(base_url=B, follow_redirects=True); s.get("/lang/zh"); st = s.get("/signup").text
ok("學位" in st and "請選擇…" in st, "signup in Chinese")
# board filter appears when a lead has a degree
fails = [m for g, m in res if not g]
print(f"\n{len(res)-len(fails)}/{len(res)} passed")
