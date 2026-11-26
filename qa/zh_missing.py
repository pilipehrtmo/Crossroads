"""List interface text that has no Traditional Chinese translation yet.   usage: python qa/zh_missing.py [template ...]
Runs each template through the same translation pass the site uses (app/i18n.py) and prints every English string
the pass looked up but did not find in app/zh.json."""
import os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from app import i18n
root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "templates")
names = sys.argv[1:] or sorted(f for f in os.listdir(root) if f.endswith(".html"))
total = 0
for n in names:
    miss = []
    def tr(s):
        if s and re.search(r"[A-Za-z]{2}", s) and i18n.lookup(s) is None and s not in miss: miss.append(s)
        return None
    i18n.walk(open(os.path.join(root, n), encoding="utf-8").read(), tr, lambda s: None)
    if miss:
        print(f"== {n}"); [print("  ", m) for m in miss]; total += len(miss)
print("missing:", total)
