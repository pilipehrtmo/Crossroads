"""Every test run uses its own throw-away SQLite file, never a real database (set before the app is imported)."""
import os, tempfile
os.environ["DB_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(prefix="mm-test-"), "test.db")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("KEEP_AWAKE", "0")
