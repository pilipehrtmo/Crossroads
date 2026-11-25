"""Shared settings for the QA scripts. Everything comes from environment variables, so the same scripts run on a
laptop, in this sandbox and in GitHub Actions.

  QA_PORT      port of the running server (default 8040)
  QA_DB        Postgres database the server uses (default qa)
  QA_PG        how to reach Postgres: "su" (run psql as the postgres user, local sandbox) or "env" (psql with the
               standard PGHOST/PGPORT/PGUSER/PGPASSWORD variables, used in CI). Default: su
  QA_PGPORT    Postgres port for QA_PG=su (default 5433)
  QA_LOG_DIR   where qa/run_server.sh writes server logs (default /var/tmp/lt); the scripts read emailed links there
  QA_SHOTS     folder for screenshots (default <QA_LOG_DIR>/shots)
"""
import os, subprocess

PORT = int(os.getenv("QA_PORT", "8040"))
DB = os.getenv("QA_DB", "qa")
B = f"http://localhost:{PORT}"
LOG_DIR = os.getenv("QA_LOG_DIR", "/var/tmp/lt")
SHOTS = os.getenv("QA_SHOTS", os.path.join(LOG_DIR, "shots"))
os.makedirs(SHOTS, exist_ok=True)
PW = "Tr0ub4dor&3xyz"   # test-only password used by every QA account


def log(port=None):
    """Path of the server log for a port (emails are printed there when no mail service is configured)."""
    return os.path.join(LOG_DIR, f"srv_{port or PORT}.log")


def q(sql, db=None):
    """Run one SQL statement against the test database and return its text output (never use on production)."""
    db = db or DB
    sql = sql.replace('\\"', '"')   # older scripts pre-escaped quotes for the shell; undo that here
    if os.getenv("QA_PG", "su") == "env":
        cmd = ["psql", "-d", db, "-tAc", sql]
    else:
        esc = sql.replace('"', '\\"')
        cmd = ["su", "postgres", "-c", f"psql -p {os.getenv('QA_PGPORT', '5433')} -d {db} -tAc \"{esc}\""]
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
