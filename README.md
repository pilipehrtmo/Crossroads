# Crossroads (Team 22)

Students find teammates across faculties for competitions, startups, research and side projects.
Python (FastAPI, Jinja2, SQLModel) with Postgres on Supabase, hosted on Render.

## Run locally
    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt sentence-transformers
    set ADMIN_EMAILS=you@example.com
    uvicorn app.main:app --reload

Without `DB_URL` it uses a local SQLite file. Secrets (DB_URL, SECRET_KEY, SMTP_PASS) are set in Render, never in this repo.

## Universities and research rules

- Every person is shown with their **university and role** (Student, Professor, Researcher). Both come from the
  person's affiliation (set at sign-up or by an admin), never from their email or department, and can't be changed
  with an ordinary profile edit. No affiliation is shown as "University not set".
- **Professor-led research** (a research position, or a Research project marked "A professor") is for students of
  the professor's chosen university only. This is checked on the server when applying, inviting, accepting an
  application and accepting an invitation.
- **Student-led research** is open to students of every university in Taiwan.
- Older Research projects that nobody classified are marked `review`. They stay open, and admins classify them
  under Admin → Research to classify.
- Multi-university sign-up is switched by `MULTI_SCHOOL=1`.

Data migration (each step is a dry run unless `--apply`):

```
python -m app.academics import     # 139 institutions from the MOE directory (data/institutions_moe.csv)
python -m app.academics migrate    # give every existing account an NTHU affiliation, keeping department and student ID
python -m app.academics research   # mark unclassified Research projects "review"; give research positions their professor's university
python -m app.academics check      # counts that must match
```

## Bilingual university and department directory

`data/institutions_directory.csv` (139 schools, Chinese + English names with source and status, search abbreviations) and
`data/academic_units.csv` (3,585 official units from the MOE 114 department list, English only where a source pairs it)
are built by `scripts/build_directory.py` from the saved official sources in `data/sources/`. Coverage and the lists
of names still to check are in `data/research/`. Load them with the dry-run-first commands:

```
python -m app.academics names            # report; add --apply to fill EMPTY English names / abbreviations only
python -m app.academics units            # report; add --apply to add missing units (never deletes or renames)
```
