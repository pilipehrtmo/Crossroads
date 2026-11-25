import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import common as QA
import re, httpx, random
B=QA.B; R=[]
def ok(c,m): R.append((bool(c),m)); print(("PASS " if c else "FAIL ")+m)
anon=httpx.Client(base_url=B,follow_redirects=False,timeout=30)
# 1. pages that need login / admin
for p in ["/admin","/advisor","/profile","/notifications","/activity","/projects/new","/openings/new"]:
    r=anon.get(p); ok(r.status_code in (302,303,401,403), f"logged-out {p} blocked ({r.status_code})")
# 2. junk ids / paths never 500
for p in ["/projects/999999","/projects/abc","/u/nobody-here","/openings/999999","/projects/-1","/u/%27%3B--","/avatar/999999","/lang/xx","/%00"]:
    r=anon.get(p); ok(r.status_code<500, f"junk {p} -> {r.status_code}")
# 3. search with SQL / script chars
for q in ["' OR 1=1 --","<script>alert(1)</script>","%"*500,"🤖"*200]:
    r=anon.get("/",params={"q":q}); ok(r.status_code<500 and "<script>alert(1)</script>" not in r.text, f"search {q[:15]!r} -> {r.status_code}")
# 4. sign up + log in a user (verify off? use demo login via forgot? -> create with signup and read verify link from log)
c=httpx.Client(base_url=B,follow_redirects=True,timeout=30)
t=re.search(r'name="csrf" value="([^"]+)"',c.get("/signup").text)[1]
n=random.randint(100000,999999); em=f"abuse{n}@example.com"; PW="Tr0ub4dor&3xyz"
r=c.post("/signup",data=dict(csrf=t,email=em,name="Abuse Tester",student_id=f"118{n}",degree="bachelor",password=PW,password2=PW,role="student",privacy="1",agree="1"))
log=open(QA.log(),errors="ignore").read()
m=re.findall(r">>> EMAIL to "+re.escape(em)+r".*?(http\S+/verify/\S+)",log,re.S)
if m: c.get(m[-1].replace(QA.B,""))
c.post("/login",data=dict(csrf=re.search(r'name="csrf" value="([^"]+)"',c.get("/login").text)[1],email=em,password=PW))
me=c.get("/profile"); logged= "/login" not in str(me.url); ok(logged,"test user logged in")
if logged:
    # 5. POST without / with wrong CSRF is refused
    r=c.post("/projects/new",data=dict(title="no csrf"),follow_redirects=False); ok(r.status_code in (400,403), f"POST without csrf refused ({r.status_code})")
    r=c.post("/projects/new",data=dict(csrf="forged",title="x"),follow_redirects=False); ok(r.status_code in (400,403), f"POST forged csrf refused ({r.status_code})")
    # 6. normal user cannot hit admin actions
    tok=re.search(r'name="csrf" value="([^"]+)"',me.text)[1]
    for p in ["/admin","/admin/ban/1","/admin/verify_all/0","/admin/scrape/0"]:
        r=c.post(p,data=dict(csrf=tok),follow_redirects=False) if p!="/admin" else c.get(p,follow_redirects=False)
        ok(r.status_code in (302,303,401,403,404,405), f"student {p} blocked ({r.status_code})")
    # 7. XSS in profile fields is escaped on public page
    pg=c.get("/profile").text; tok=re.search(r'name="csrf" value="([^"]+)"',pg)[1]
    form=c.get("/profile")
    xss='<img src=x onerror=alert(1)>'
    r=c.post("/profile",data=dict(csrf=tok,name="Abuse Tester",bio=xss,skills="python, "+xss))
    h=re.search(r'href="/u/([^"]+)"',c.get("/profile").text)
    pub=c.get(f"/u/{h[1]}").text if h else ""
    ok(r.status_code<500, f"profile save with html ({r.status_code})")
    ok("<img src=x onerror" not in pub, "html in bio/skills is escaped on public page")
    # 8. giant input
    r=c.post("/profile",data=dict(csrf=tok,name="A"*5000,bio="B"*200000)); ok(r.status_code<500, f"giant profile input -> {r.status_code}")
# 9. login brute force gets limited
bad=httpx.Client(base_url=B,follow_redirects=True,timeout=30); codes=[]
for i in range(25):
    t=re.search(r'name="csrf" value="([^"]+)"',bad.get("/login").text)
    r=bad.post("/login",data=dict(csrf=t[1] if t else "",email=em,password=f"wrong{i}")); codes.append(r.status_code)
txt=r.text.lower()
ok(429 in codes or "too many" in txt or "wait" in txt, f"25 wrong passwords get rate-limited (last={codes[-1]})")
srv=open(QA.log(),errors="ignore").read()
ok("Traceback" not in srv, "no server crash (Traceback) in log")
print(f"\n{sum(a for a,_ in R)}/{len(R)} passed")
