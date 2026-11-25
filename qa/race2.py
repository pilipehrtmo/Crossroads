import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import common as QA
import re, subprocess, threading, httpx
B = QA.B; PW = "Tr0ub4dor&3xyz"
q = lambda s: QA.q(s, None)
ids = q("select id from application where role_id=1 and status='pending' order by id limit 2").split()
def login():
    c = httpx.Client(base_url=B, follow_redirects=True, timeout=60); t = re.search(r'name="csrf" value="([^"]+)"', c.get("/login").text)[1]
    c.post("/login", data=dict(csrf=t, email="yuchen-w@demo.local", password=PW)); return c
cs = [login(), login()]
tok = [re.search(r'name="csrf" value="([^"]+)"', c.get("/projects/1").text)[1] for c in cs]
paths = [x for x in re.findall(r'action="(/applications/\d+/[a-z]+)"', cs[0].get("/projects/1").text)][:6]; print("forms:", paths)
def go(i): cs[i].post(f"/applications/{ids[i]}/accepted", data=dict(csrf=tok[i]))
ts = [threading.Thread(target=go, args=(i,)) for i in range(2)]; [t.start() for t in ts]; [t.join() for t in ts]
print("accepted on 1-person seat:", q("select count(*) from application where role_id=1 and status='accepted'"), "| seat filled:", q("select filled from role where id=1"))
