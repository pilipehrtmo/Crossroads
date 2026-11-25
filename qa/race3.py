import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import common as QA
"""B5: two accepts at the same instant, repeated 10 times on fresh one-person seats. Exactly one may win each time."""
import re, subprocess, threading, httpx, random
B = QA.B; PW = "Tr0ub4dor&3xyz"
q = lambda s: QA.q(s, None)
def login(email):
    c = httpx.Client(base_url=B, follow_redirects=True, timeout=60); t = re.search(r'name="csrf" value="([^"]+)"', c.get("/login").text)[1]
    c.post("/login", data=dict(csrf=t, email=email, password=PW)); return c
lead = "yuchen-w@demo.local"; lid = q(f"select id from \\\"user\\\" where email='{lead}'")
applicants = q("select id from \\\"user\\\" where email like 'app%' order by id limit 2").split()
cs = [login(lead), login(lead)]; wins = []; notices = []
for n in range(10):
    pid = q(f"insert into project (owner_id,title,description,kind,category,stage,tagline,problem,audience,solution,objectives,methodology,outcomes,progress,needs,metrics,tags,event_name,links,hours_per_week,deadline,status,created) values ({lid},'Race test {n}','x','Side project','','','','','','','','','','','','','','','',4,'','open',now()) returning id").splitlines()[0]
    rid = q(f"insert into role (project_id,name,skills,filled,advisor,about,must,nice,years,years_in,beginner) values ({pid},'Designer','figma',false,false,'','','',0,'',false) returning id").splitlines()[0]
    a = [q(f"insert into application (role_id,user_id,message,status,at) values ({rid},{u},'Race applicant note here','pending',now()) returning id").splitlines()[0] for u in applicants]
    tok = [re.search(r'name="csrf" value="([^"]+)"', c.get(f"/projects/{pid}").text)[1] for c in cs]
    res = [None, None]
    def go(i): res[i] = cs[i].post(f"/applications/{a[i]}/accepted", data=dict(csrf=tok[i]))
    ts = [threading.Thread(target=go, args=(i,)) for i in range(2)]; [t.start() for t in ts]; [t.join() for t in ts]
    acc = int(q(f"select count(*) from application where role_id={rid} and status='accepted'")); wins.append(acc)
    notices.append(sum("filled a moment ago" in r.text for r in res))
print("accepted per seat over 10 races:", wins, "| loser saw the 'seat filled' message:", notices)
print("PASS" if all(w == 1 for w in wins) else "FAIL")
