# QA scripts

End-to-end checks that run against a real server and a real (throw-away) Postgres database.
They never touch production. Settings come from environment variables, see `common.py`.

Start a server first:

```
qa/run_server.sh 8040 <test-db>            # VERIFY=1 to require email confirmation, DEMO=1 for demo projects
```

| Script | What it checks | Needs a browser |
| --- | --- | --- |
| `smoke.py <port> <db>` | Every page, logged in and out, answers without a server error | No |
| `abuse.py` | Logged-out and student access to admin pages, CSRF, script injection, junk ids, huge input, login rate limit | No |
| `race.py`, `race2.py`, `race3.py` | Simultaneous sign-ups, applications and accepts: one winner per seat | No |
| `rep_flow.py <port> <db>` | Track record: confirmation, disagreements, admin decisions | No |
| `deg_flow.py <port> <db>` | Degree field rules | No |
| `migcheck.py <db>` | Department migration left every row consistent | No |
| `bugs.py` | Tutorial bugs B1 to B12 stay fixed (needs `VERIFY=1`) | Yes (Playwright) |
| `five.py` | Five full sign-up-to-application journeys (refresh, Back, Chinese, fast) | Yes |
| `run_one.py`, `journey.py` | One journey; shared helpers | Yes |
| `eye.py` | The password eye button works on the first click | Yes |
| `admintour.py` | The admin tour in English and Chinese, laptop and phone | Yes |
| `layout.py` | No horizontal scroll, cut text or tiny tap targets | Yes |
| `rep_ui.py`, `deg_ui.py`, `tour_new.py` | Track record, degree and new-feature tour screens | Yes |

GitHub Actions (`.github/workflows/test.yml`) runs the unit tests, `smoke.py` and `abuse.py` on every push.
The browser checks need Playwright and are run before each release.
