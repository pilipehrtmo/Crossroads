import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import common as QA
import subprocess, sys
DB=sys.argv[1]
def q(s): return QA.q(s, DB)
print("users",q('select count(*) from \\"user\\"'),"projects",q("select count(*) from project"),"roles",q("select count(*) from role"),"apps",q("select count(*) from application"),
 "| new cols",q("select count(*) from information_schema.columns where (table_name,column_name) in (('user','interests'),('user','roles_wanted'),('project','completed_at'))"),
 "| new tables",q("select count(*) from information_schema.tables where table_name in ('contribution','endorsement')"))
print("fp", q('select md5(string_agg(u.id::text||coalesce(u.faculty,\'\')||coalesce(u.skills,\'\')||u.email||coalesce(u.bio,\'\'),\'|\' order by u.id)) from \\"user\\" u'), q("select md5(string_agg(id::text||title||status||coalesce(description,''),'|' order by id)) from project"))
