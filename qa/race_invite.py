import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import common as QA
"""An invitation accept and an application accept for the same one-person seat at the same instant, 10 times.
Exactly one may win each time: the seat is filled once, one member is accepted, and the loser is closed.
Uses the 'app*' accounts that race.py creates (run race.py first)."""
import re, threading, httpx
B, PW, q = QA.B, QA.PW, QA.q
def login(email):
    c = httpx.Client(base_url=B, follow_redirects=True, timeout=60); t = re.search(r'name="csrf" value="([^"]+)"', c.get("/login").text)[1]
    c.post("/login", data=dict(csrf=t, email=email, password=PW)); return c, t
def tok(c, path): return re.search(r'name="csrf" value="([^"]+)"', c.get(path).text)[1]
lead = "yuchen-w@demo.local"; lid = q(f"select id from \\\"user\\\" where email='{lead}'")
ppl = q("select id || ' ' || email from \\\"user\\\" where email like 'app%' order by id limit 2").splitlines()
(aid_u, a_email), (bid_u, b_email) = [p.split(" ", 1) for p in ppl]
cl, _ = login(lead); cb, _ = login(b_email)
wins, bad = [], []
for n in range(10):
    pid = q(f"insert into project (owner_id,title,description,kind,category,stage,tagline,problem,audience,solution,objectives,methodology,outcomes,progress,needs,metrics,tags,event_name,links,hours_per_week,deadline,status,created) values ({lid},'Invite race {n}','x','Side project','','','','','','','','','','','','','','','',4,'','open',now()) returning id").splitlines()[0]
    rid = q(f"insert into role (project_id,name,skills,filled,advisor,about,must,nice,years,years_in,beginner) values ({pid},'Designer','figma',false,false,'','','',0,'',false) returning id").splitlines()[0]
    app = q(f"insert into application (role_id,user_id,message,status,at) values ({rid},{aid_u},'Race applicant note here','pending',now()) returning id").splitlines()[0]
    inv = q(f"insert into invitation (role_id,project_id,user_id,from_id,message,status,at) values ({rid},{pid},{bid_u},{lid},'','pending',now()) returning id").splitlines()[0]
    tl, tb = tok(cl, f"/projects/{pid}"), tok(cb, "/activity")
    go = threading.Barrier(2)
    def lead_accepts(): go.wait(); cl.post(f"/applications/{app}/accepted", data=dict(csrf=tl))
    def b_accepts(): go.wait(); cb.post(f"/invitations/{inv}/accepted", data=dict(csrf=tb))
    th = [threading.Thread(target=lead_accepts), threading.Thread(target=b_accepts)]; [t.start() for t in th]; [t.join() for t in th]
    accepted = int(q(f"select count(*) from application where role_id={rid} and status='accepted'"))
    filled = q(f"select filled from role where id={rid}")
    ist = q(f"select status from invitation where id={inv}"); ast = q(f"select status from application where id={app}")
    wins.append(accepted)
    ok = accepted == 1 and filled == "t" and ((ist == "accepted") != (ast == "accepted")) and (ist in ("accepted", "closed")) and (ast in ("accepted", "closed"))
    if not ok: bad.append((n, accepted, filled, ist, ast))
print("accepted per seat:", wins, "| problems:", bad)
print("PASS" if not bad else "FAIL")
