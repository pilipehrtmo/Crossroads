import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import common as QA
import sys, re, subprocess, httpx
B=f"http://localhost:{sys.argv[1]}"; DB=sys.argv[2]
def q(sql): return QA.q(sql, DB)
bad=[]; n=0
pids=q("select id from project order by id").split(); oids=q("select id from opening order by id").split(); cids=q("select id from competition order by id limit 5").split()
handles=q("select handle from \\\"user\\\" order by id").split()
pages=["/","/research","/funding","/discuss","/help","/privacy","/login","/signup","/forgot"]+[f"/projects/{p}" for p in pids]+[f"/openings/{o}" for o in oids]+[f"/competitions/{c}" for c in cids]+[f"/u/{h}" for h in handles]
authed=["/profile","/activity","/notifications","/admin","/projects/new","/verification","/advisor"]
for who in ("anon","amy","admin"):
    for lang in ("en","zh"):
        c=httpx.Client(base_url=B,follow_redirects=True,timeout=30,cookies={"lang":lang})
        if who!="anon":
            em=q("select email from \\\"user\\\" where name='Test Amy' limit 1") if who=="amy" else "admin@audit.test"
            tok=re.search(r'name="csrf" value="([^"]+)"',c.get("/login").text)[1]; c.post("/login",data=dict(csrf=tok,email=em,password="Tr0ub4dor&3xyz"))
        for p in pages+(authed if who!="anon" else []):
            r=c.get(p); n+=1
            if r.status_code>=500 or "Traceback" in r.text: bad.append((who,lang,p,r.status_code))
print("requests",n,"errors",bad[:10])
