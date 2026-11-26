"""Mark existing users and projects as seed or demo from the hand-reviewed list in data/origin_review.json.

    python -m app.origin_tool            # dry run: prints what would change, writes nothing
    python -m app.origin_tool --apply    # writes the changes (back up the database first)

Only ids listed in the file change; titles are never looked at. Running it twice changes nothing the second time.
Rollback: set origin back to 'real' for the same ids (the printed list is the record of what changed).
"""
import json, os, sys
from sqlmodel import Session
from .models import User, Project

REVIEW = os.path.join(os.path.dirname(__file__), "..", "data", "origin_review.json")


def plan(s: Session, review: dict):
    """[(kind, id, old, new)] for every listed row whose origin differs; missing ids are reported as ('missing', ...)."""
    out = []
    for kind, model in (("users", User), ("projects", Project)):
        for origin, ids in review.get(kind, {}).items():
            if origin not in ("seed", "demo"): raise ValueError(f"unknown origin {origin!r}")
            for i in ids:
                row = s.get(model, i)
                if row is None: out.append(("missing", kind, i, origin))
                elif row.origin != origin: out.append((kind, i, row.origin, origin))
    return out


def apply(s: Session, changes):
    for c in changes:
        if c[0] == "missing": continue
        kind, i, _, new = c
        row = s.get(User if kind == "users" else Project, i); row.origin = new
    s.commit()


def main(argv):
    from .db import engine, init_db
    init_db()   # adds the origin columns if this database does not have them yet (additive only)
    review = json.load(open(REVIEW, encoding="utf-8"))
    with Session(engine) as s:
        changes = plan(s, review)
        for c in changes: print(*c)
        if not changes: print("nothing to change")
        if "--apply" in argv and changes:
            apply(s, changes); print("applied", sum(1 for c in changes if c[0] != "missing"))
        elif changes: print("dry run: nothing written (add --apply)")


if __name__ == "__main__": main(sys.argv[1:])
