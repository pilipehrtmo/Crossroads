import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import common as QA
"""HTTP checks of For you + track record on a local server. Usage: rep_flow.py <port> <db>"""
import sys, re, subprocess, random, httpx
PORT, DB = sys.argv[1], sys.argv[2]; B = f"http://localhost:{PORT}"; PW = "Tr0ub4dor&3xyz"; R = random.randint(10000, 99999)
res = []

import json as _json
_req = {}
def ins(sql):
    """INSERT INTO t (cols) VALUES (...) RETURNING ...: fills every other NOT NULL column without a default with '' / 0 / false."""
    m = re.match(r"insert into (\\?\"?\w+\\?\"?) \(([^)]*)\) (values \((.*)\)|select (.*?) from (.*))( returning \w+)?$", sql, re.S)
    if not m: return q(sql)
    t = m[1].replace('\\', '').strip('"'); cols = [c.strip() for c in m[2].split(",")]
    if t not in _req:
        rows = q(f"select column_name||'|'||data_type from information_schema.columns where table_name='{t}' and is_nullable='NO' and column_default is null")
        _req[t] = [r.split("|") for r in rows.splitlines() if r]
    extra = [(c, d) for c, d in _req[t] if c not in cols]
    lit = lambda d: "false" if d == "boolean" else ("0" if d in ("integer", "bigint", "double precision", "real", "numeric") else ("now()" if "timestamp" in d else "''"))
    ec = ",".join(c for c, _ in extra); ev = ",".join(lit(d) for _, d in extra)
    tbl = '\\"user\\"' if t == "user" else t
    if m[4] is not None:
        body = f"values ({m[4]}{',' + ev if ev else ''})"
    else:
        body = f"select {m[5]}{',' + ev if ev else ''} from {m[6]}"
    return q(f"insert into {tbl} ({m[2]}{',' + ec if ec else ''}) {body}{m[7] or ''}")
def ok(c, m, extra=""): res.append((bool(c), m)); print(("ok  " if c else "FAIL"), m, "" if c else extra)
def q(sql): return QA.q(sql, DB)
def csrf(c, path="/signup"): return re.search(r'name="csrf" value="([^"]+)"', c.get(path).text)[1]
def post(c, path, data, page=None):
    data = dict(data); data.setdefault("csrf", csrf(c, page or path if c.get(page or path).status_code == 200 else "/"))
    return c.post(path, data=data)
def user(tag, admin=False, dept=""):
    c = httpx.Client(base_url=B, follow_redirects=True, timeout=30)
    email = "admin@audit.test" if admin else f"{tag}{R}@example.com"
    if admin and q(f"select count(*) from \\\"user\\\" where email='{email}'") != "0":
        c.post("/login", data=dict(csrf=csrf(c, "/login"), email=email, password=PW)); return c, int(q(f"select id from \\\"user\\\" where email='{email}'"))
    d = dict(csrf=csrf(c), role="student", email=email, name=f"Test {tag.capitalize()}", student_id=str(R * 1000 + sum(map(ord, tag)))[-9:].rjust(9, "1"),
             password=PW, password2=PW, agree="1", dept_sel=dept, degree="bachelor")
    c.post("/signup", data=d)
    uid = q(f"select id from \\\"user\\\" where email='{email}'")
    assert uid, f"signup failed for {tag}"
    return c, int(uid)
L, lid = user("lead", dept="eecs-cs"); A, aid = user("amy", dept="eecs-cs"); Bm, bid = user("ben", dept="tm-qf"); O, oid = user("olly", dept="lsm-ls")
AD, adid = user("admin", admin=True)
ok(q(f"select is_admin from \\\"user\\\" where id={adid}") == "t", "admin account is admin")
# profiles: Amy wants backend work on ML; Olly has nothing
r = post(A, "/profile", dict(name="Test Amy", bio="", skills="python, sql, react", interests="machine learning, health", roles_wanted="backend developer", hours="8", dept_sel="eecs-cs"))
ok(q(f"select interests||'|'||roles_wanted from \\\"user\\\" where id={aid}") == "machine learning,health|backend developer", "profile saves interests and roles wanted")
r = post(A, "/profile", dict(name="Test Amy", skills="python", interests=", ".join(f"topic{i}" for i in range(12)), hours="8"))
ok("at most 10" in r.text and q(f"select interests from \\\"user\\\" where id={aid}") == "machine learning,health", "more than 10 interests refused, old ones kept")
post(A, "/profile", dict(name="Test Amy", bio="", skills="python, sql, react", interests="machine learning, health", roles_wanted="backend developer", hours="8", dept_sel="eecs-cs"))
# data: Lead's ML project with a backend seat; an unrelated one; Ben's (other college) health project; competitions; a research position
p1 = ins(f"insert into project (owner_id,title,description,kind,category,tags,hours_per_week,deadline,status,created) values ({lid},'ML triage {R}','We use machine learning to sort clinic messages','Side project','','ML:purple',6,'','open',now()) returning id")
p1 = p1.splitlines()[0]
s1 = ins(f"insert into role (project_id,name,skills,filled) values ({p1},'Backend developer','python,sql',false) returning id").splitlines()[0]
s1b = ins(f"insert into role (project_id,name,skills,filled) values ({p1},'Designer','figma',false) returning id").splitlines()[0]
p2 = ins(f"insert into project (owner_id,title,description,kind,hours_per_week,deadline,status,created) values ({lid},'Bake sale {R}','Selling cakes for the club','Club or event',3,'','open',now()) returning id").splitlines()[0]
ins(f"insert into role (project_id,name,skills,filled) values ({p2},'Baker','baking',false)")
p3 = ins(f"insert into project (owner_id,title,description,kind,hours_per_week,deadline,status,created) values ({bid},'Health app {R}','Health tracking app for students','Startup',5,'','open',now()) returning id").splitlines()[0]
ins(f"insert into role (project_id,name,skills,filled) values ({p3},'Backend developer','python,django',false)")
p4 = ins(f"insert into project (owner_id,title,description,kind,hours_per_week,deadline,status,created) values ({bid},'Heavy ML {R}','machine learning research needing python and sql','Research',20,'','open',now()) returning id").splitlines()[0]
ins(f"insert into role (project_id,name,skills,filled) values ({p4},'Backend developer','python,sql',false)")
c_ok = ins(f"insert into competition (title,url,deadline,needs_review,category,description) values ('Machine learning cup {R}','https://example.org/ml{R}',to_char(now()+interval '30 day','YYYY-MM-DD'),false,'Tech & Data','') returning id").splitlines()[0]
c_old = ins(f"insert into competition (title,url,deadline,needs_review,category,description) values ('Old machine learning cup {R}','https://example.org/old{R}','2020-01-01',false,'Tech & Data','') returning id").splitlines()[0]
c_nodate = ins(f"insert into competition (title,url,deadline,needs_review,category,description) values ('Undated machine learning cup {R}','https://example.org/nd{R}','',false,'Tech & Data','') returning id").splitlines()[0]
prof = ins(f"insert into \\\"user\\\" (email,handle,name,role,is_faculty,banned,skills,bio,hours,created,email_verified,dept_id) values ('prof{R}@example.com','prof-{R}','Prof Test','faculty',true,false,'','',4,now(),true,'lsm-ms') returning id").splitlines()[0]
op = ins(f"insert into opening (owner_id,title,description,skills,hours,positions,deadline,status,created) values ({prof},'Machine learning for health records','Use python to study health data','python,statistics','8',1,'','open',now()) returning id").splitlines()[0]
# --- For you on the home page
def fy_cards(c):
    h = c.get("/").text
    return {int(m[1]): m[2] for m in re.finditer(r'href="/projects/(\d+)">[^<]*</a></h2>', h) for _ in [0]} , h
h = A.get("/").text
def card(h, pid):
    i = h.find(f'href="/projects/{pid}"'); j = h.rfind('<article', 0, i); return h[j:i]
ok('class="fytag"' in card(h, p1) and "Matches 2 of your skills: python, sql" in card(h, p1) and "Needs a Backend developer, a role you want" in card(h, p1), "For you on a matching project, with real reasons")
ok('class="fytag"' not in card(h, p2), "no For you on an unrelated project")
ok('class="fytag"' in card(h, p3) and "From another college" in card(h, p3), "cross-college pick says so")
ok('class="fytag"' not in card(h, p4), "20 h/week project not For you for an 8 h/week student")
order = [int(x) for x in re.findall(r'<article class="card link pcard[^>]*?data-fy="(\d)"', h)]
ok(order == sorted(order, reverse=True), "For you cards come first")
ok('data-fy="1"' in h and h.count('class="fytag"') >= 2, "tags present")
ok(f"ml{R}" in h and 'data-fy="1"' in h[h.find(f'example.org/ml{R}')-2500:h.find(f'example.org/ml{R}')], "open competition matching an interest is For you")
seg = lambda u: h[h.rfind('<article', 0, h.find(u)):h.find(u)]
ok('class="fytag"' not in seg(f"example.org/old{R}"), "expired competition never For you")
ok('class="fytag"' not in seg(f"example.org/nd{R}"), "competition without a confirmed date not For you")
hl = L.get("/").text
ok('class="fytag"' not in card(hl, p1), "no For you on your own project")
ho = O.get("/").text
ok('class="fytag"' not in ho and "To get “For you” picks" in ho, "empty profile: no tags, hint how to get them")
hr = A.get("/research").text
ok("Machine learning for health records" in hr and 'class="fytag"' in hr, "research position For you")
ok(f"{R}@example.com" not in h, "no emails on the home page")
# apply -> not recommended any more
post(A, f"/roles/{s1}/apply", dict(message="I have built two Flask backends with SQL."), f"/projects/{p1}")
ok('class="fytag"' not in card(A.get("/").text, p1), "after applying, the project is no longer For you")
# --- completion
ins(f"update application set status='accepted' where role_id={s1} and user_id={aid}")
ins(f"insert into application (role_id,user_id,message,status,at) values ({s1b},{bid},'design help please consider me','removed',now())")
r = post(A, f"/projects/{p1}/complete", {}, f"/projects/{p1}"); ok(r.status_code == 403, "a member cannot mark completed", r.status_code)
r = post(L, f"/projects/{p2}/complete", {}, f"/projects/{p2}"); ok("at least one person has joined" in r.text and q(f"select status from project where id={p2}") == "open", "no team: cannot complete")
appA = q(f"select id from application where role_id={s1} and user_id={aid}")
r = post(L, f"/projects/{p1}/complete", {"lead_note": "planned it", f"in_{appA}": "1", f"note_{appA}": "built the API"}, f"/projects/{p1}")
ok(q(f"select status from project where id={p1}") == "completed", "lead marks completed")
rows = q(f"select user_id||':'||lead_status||':'||member_status||':'||is_lead from contribution where project_id={p1} order by id")
ok(rows == f"{lid}:confirmed:confirmed:true\n{aid}:confirmed:pending:false\n{bid}:not_included:pending:false", "rows: lead, member pending, removed member listed as not included", rows)
r = post(L, f"/projects/{p1}/complete", {}, f"/projects/{p1}"); ok(q(f"select count(*) from contribution where project_id={p1}") == "3", "completing twice adds nothing")
ok(int(q(f"select count(*) from notification where user_id in ({aid},{bid}) and kind='completion'")) >= 2, "members notified")
pub = O.get(f"/u/{q(f'select handle from \\\"user\\\" where id={aid}')}").text
ok("Track record" in pub and "Confirmed by lead and member" not in pub, "pending: nothing shown as confirmed yet")
cA = q(f"select id from contribution where project_id={p1} and user_id={aid}"); cB = q(f"select id from contribution where project_id={p1} and user_id={bid}"); cL = q(f"select id from contribution where project_id={p1} and user_id={lid}")
r = post(O, f"/contributions/{cA}/confirm", {}, f"/projects/{p1}"); ok(r.status_code == 403, "someone else cannot confirm my part")
r = post(L, f"/contributions/{cL}/dispute", {"reason": "x" * 20}, f"/projects/{p1}"); ok(r.status_code == 403, "the lead cannot answer for the lead row")
r = post(Bm, f"/contributions/{cB}/confirm", {}, f"/projects/{p1}"); ok(q(f"select member_status from contribution where id={cB}") == "pending", "not-included member cannot simply confirm")
r = post(L, f"/projects/{p1}/endorse", {"to": aid, "tag": "q:reliable"}, f"/projects/{p1}"); ok(r.status_code == 403, "no endorsing before the member confirms")
post(A, f"/contributions/{cA}/confirm", {}, f"/projects/{p1}")
ok(q(f"select member_status from contribution where id={cA}") == "confirmed", "member confirms")
r = post(A, f"/contributions/{cA}/dispute", {"reason": "changed my mind about it"}, f"/projects/{p1}"); ok(q(f"select member_status from contribution where id={cA}") == "confirmed", "a confirmed answer cannot be flipped")
r = post(L, f"/projects/{p1}/complete/cancel", {}, f"/projects/{p1}"); ok(q(f"select status from project where id={p1}") == "completed", "cannot undo after a teammate confirmed")
r = post(L, f"/projects/{p1}/delete", {}, f"/projects/{p1}"); ok(q(f"select count(*) from project where id={p1}") == "1", "lead cannot delete a completed project")
r = post(Bm, f"/contributions/{cB}/dispute", {"reason": "short"}, f"/projects/{p1}"); ok(q(f"select member_status from contribution where id={cB}") == "pending", "dispute needs a real reason")
post(Bm, f"/contributions/{cB}/dispute", {"reason": "I designed every screen before I was removed"}, f"/projects/{p1}")
ok(q(f"select member_status from contribution where id={cB}") == "disputed", "removed member disputes")
# endorsements
r = post(A, f"/projects/{p1}/endorse", {"to": lid, "tag": ["q:reliable", "q:coord", "q:helpful", "q:design", "q:bogus"]}, f"/projects/{p1}")
ok(q(f"select string_agg(tag, ',' order by tag) from endorsement where from_id={aid} and to_id={lid}") == "q:coord,q:helpful,q:reliable", "max 3, only known strengths")
post(A, f"/projects/{p1}/endorse", {"to": lid, "tag": "q:reliable"}, f"/projects/{p1}")
ok(q(f"select count(*) from endorsement where from_id={aid} and to_id={lid}") == "3", "no duplicate endorsements")
r = post(A, f"/projects/{p1}/endorse", {"to": aid, "tag": "q:reliable"}, f"/projects/{p1}"); ok(r.status_code == 403, "no self-endorsement")
r = post(O, f"/projects/{p1}/endorse", {"to": aid, "tag": "q:reliable"}, f"/projects/{p1}"); ok(r.status_code == 403, "outsiders cannot endorse")
r = post(Bm, f"/projects/{p1}/endorse", {"to": aid, "tag": "q:reliable"}, f"/projects/{p1}"); ok(r.status_code == 403, "a disputed member cannot endorse")
post(L, f"/projects/{p1}/endorse", {"to": aid, "tag": ["s:python", "q:technical"]}, f"/projects/{p1}")
ok(q(f"select count(*) from endorsement where from_id={lid} and to_id={aid}") == "2", "lead endorses a seat skill and a strength")
# public profiles
pubA = O.get(f"/u/{q(f'select handle from \\\"user\\\" where id={aid}')}").text
ok("Confirmed by lead and member" in pubA and f"ML triage {R}" in pubA and "Strong technical work" in pubA and "built the API" in pubA, "member profile: confirmed project, note, endorsements")
ok(re.search(r"<b>1</b><span>project joined", pubA) and re.search(r"<b>1</b><span>completed", pubA), "counts: 1 joined, 1 completed")
ok(f"amy{R}@example.com" not in pubA, "no email on the public profile")
pubL = O.get(f"/u/{q(f'select handle from \\\"user\\\" where id={lid}')}").text
ok("Confirmed by the team" in pubL and "Reliable communication" in pubL, "lead profile: lead row counts after a teammate confirmed")
pubB = O.get(f"/u/{q(f'select handle from \\\"user\\\" where id={bid}')}").text
ok(f"ML triage {R}" not in pubB, "disputed contribution not on the profile")
pp = O.get(f"/projects/{p1}").text
ok("I designed every screen" not in pp, "dispute reason hidden from outsiders")
# admin
r = post(L, f"/admin/contribution/{cB}/count", {}, "/"); ok(r.status_code == 403, "non-admin cannot decide disputes")
r = post(L, f"/admin/completion/{p1}/verify", {}, "/"); ok(r.status_code == 403, "non-admin cannot verify")
r = A.post(f"/contributions/{cA}/confirm", data={"csrf": "wrong"}); ok(r.status_code == 403, "CSRF checked")
ah = AD.get("/admin").text
ok("I designed every screen" in ah and f"ML triage {R}" in ah, "admin queue lists the dispute")
post(AD, f"/admin/contribution/{cB}/count", {}, "/admin")
ok(q(f"select lead_status||member_status||admin_status from contribution where id={cB}") == "confirmedconfirmedresolved", "admin counts the removed member's contribution")
post(AD, f"/admin/completion/{p1}/verify", {}, "/admin")
ok(q(f"select count(*) from contribution where project_id={p1} and admin_status='verified'") == "3", "admin verifies the completion")
ok("Admin-verified" in O.get(f"/u/{q(f'select handle from \\\"user\\\" where id={aid}')}").text, "profile shows Admin-verified")
# false completion: Ben's project, Ben completes, admin reopens
ins(f"insert into application (role_id,user_id,message,status,at) select id,{oid},'hello hello hello hello','accepted',now() from role where project_id={p3}")
appO = q(f"select a.id from application a join role r on r.id=a.role_id where r.project_id={p3} and a.user_id={oid}")
post(Bm, f"/projects/{p3}/complete", {f"in_{appO}": "1"}, f"/projects/{p3}")
cO = q(f"select id from contribution where project_id={p3} and user_id={oid}")
post(O, f"/contributions/{cO}/dispute", {"reason": "We never finished this, the project was abandoned"}, f"/projects/{p3}")
post(AD, f"/admin/completion/{p3}/reopen", {}, "/admin")
ok(q(f"select status||':'||(select count(*) from contribution where project_id={p3}) from project where id={p3}") == "closed:0", "admin reopens an abandoned project: nothing stays")
# undo before anyone confirms
ins(f"insert into application (role_id,user_id,message,status,at) select id,{oid},'hello hello hello hello','accepted',now() from role where project_id={p2}")
appO2 = q(f"select a.id from application a join role r on r.id=a.role_id where r.project_id={p2} and a.user_id={oid}")
post(L, f"/projects/{p2}/complete", {f"in_{appO2}": "1"}, f"/projects/{p2}")
post(L, f"/projects/{p2}/complete/cancel", {}, f"/projects/{p2}")
ok(q(f"select status||':'||(select count(*) from contribution where project_id={p2}) from project where id={p2}") == "closed:0", "lead can undo before anyone confirms")
print("FAILS", [m for c, m in res if not c]); print(sum(c for c, _ in res), "/", len(res))
