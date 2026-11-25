import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import common as QA
"""Server-side races: same student ID at the same instant; five apply to one seat at once; lead accepts two at once."""
import re, random, subprocess, threading, httpx, time
B = QA.B; PW = "Tr0ub4dor&3xyz"
q = lambda s: QA.q(s, None)
def csrf(c, path): return re.search(r'name="csrf" value="([^"]+)"', c.get(path).text)[1]
def L(n): return "".join(chr(97 + int(c)) for c in str(n)).capitalize()
def verify(email):
    for _ in range(40):
        log = open(QA.log(), encoding="utf-8", errors="ignore").read()
        m = re.findall(re.escape(email) + r": Confirm.*?(http\S+/verify/\S+)", log, re.S)
        if m: return m[-1]
        time.sleep(.25)
def signup(email, name, sid):
    c = httpx.Client(base_url=B, follow_redirects=True, timeout=60)
    r = c.post("/signup", data=dict(csrf=csrf(c, "/signup"), role="student", email=email, name=name, student_id=sid, degree="bachelor", password=PW, password2=PW, agree="1"))
    return c, r
R = random.randint(100000, 999999); out = {}
# 1) same student ID, two different emails, same instant
sid = f"117{R}"
def one(i): c, r = signup(f"race{i}{R}@example.com", f"Racer {L(R)} {'ab'[i]}", sid); out[i] = ("Check your inbox" in r.text, "already has an account" in r.text)
ts = [threading.Thread(target=one, args=(i,)) for i in range(2)]; [t.start() for t in ts]; [t.join() for t in ts]
print("same student ID twice at once:", out, "rows in DB:", q(f"select count(*) from \\\"user\\\" where student_id='{sid}'"))
# 2) five verified users apply to the same open seat at the same moment
seat = q("select r.id from role r join project p on p.id=r.project_id where not r.filled and not r.advisor and p.status='open' order by r.id limit 1")
pid = q(f"select project_id from role where id={seat}"); print("seat", seat, "project", pid)
users = []
for i in range(5):
    e = f"app{i}{R}@example.com"; c, r = signup(e, f"Applicant {L(R)} {'abcde'[i]}", f"118{R}"[:-1] + str(i)); c.get(verify(e)); users.append(c)
res = []
def apply(c, i):
    tok = csrf(c, f"/projects/{pid}")
    r = c.post(f"/roles/{seat}/apply", data=dict(csrf=tok, message=f"I would like to join, applicant {i}.", link=""))
    res.append((i, r.status_code))
ts = [threading.Thread(target=apply, args=(c, i)) for i, c in enumerate(users)]; [t.start() for t in ts]; [t.join() for t in ts]
print("5 simultaneous applications:", sorted(res), "rows:", q(f"select count(*) from application where role_id={seat} and message like 'I would like to join, applicant %'"))
# apply twice at once from the same user: only one row?
res = []; ts = [threading.Thread(target=apply, args=(users[0], 9)) for _ in range(3)]; [t.start() for t in ts]; [t.join() for t in ts]
print("same user applies 3x at once:", q(f"select count(*) from application a join \\\"user\\\" u on u.id=a.user_id where role_id={seat} and u.email='app0{R}@example.com'"))
# 3) the lead accepts two applicants for a 1-person seat at the same moment
owner = q(f"select email from \\\"user\\\" u join project p on p.owner_id=u.id where p.id={pid}"); print("lead:", owner)
