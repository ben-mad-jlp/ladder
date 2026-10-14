"""A small laddered repository to try Ladder Review on: an API and a client tree, linked, tagged and approved, then
changed the ways a review meets: an edited step (stale code, its caller told), a hand edit, an open question.
usage: python3 make_demo.py <out folder>    then: swift run LadderReview <out folder>"""
import json
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[3] / "plugins" / "ladder" / "tool" / "ladder.py"
out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True)
subprocess.run(["git", "init", "-q", str(out)], check=True)


def ladder(*args):
    return subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True, text=True).stdout


def write(rel, text):
    p = out / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


write("ladder.repo.json", json.dumps({"projects": ["ladder/**/ladder.json"]}, indent=2))
write("ladder/alerts/api/alerts.ladder", """\
data Alert
  id: the alert's number
  text: what it says
  createdUtc: when it was raised
  readBy: the users who have read it
  rule: an alert is never deleted, only read

[api.1] Alerts for the current user
  in: GET /alerts with the user's token
  out: the user's `Alert` list, newest first
  > answers the alerts that are not older than 30 days
  note: QUESTION: is a 30-day-old alert included, or only younger ones?

  [api.1.1] Read the token
    in: the request's Authorization header
    out: the user's id, or 401
    > answers 401 when the header is missing or the token has expired
    > otherwise answers the user id the token names

  [api.1.2] Load the alerts
    in: the user id
    out: the user's alerts, newest first
    > loads every `Alert` whose `createdUtc` is within 30 days
    > orders them by `createdUtc`, newest first

[api.2] Mark an alert read
  in: POST /alerts/{id}/read with the user's token
  out: 204, or 404 when there is no such alert
  effects: adds the user to the alert's `readBy`
  > answers 404 when no alert has that id
  > adds the user to `readBy` once; reading twice changes nothing
""")
write("ladder/alerts/api/ladder.json", json.dumps({"title": "Alerts API", "tree": "alerts.ladder", "builds": [
    {"name": "api", "lang": "typescript", "mode": "literal", "files": ["../../../src/api/alerts.ts"]}]}, indent=2))
write("ladder/alerts/client/alerts-client.ladder", """\
[c.1] Alerts screen
  in: the signed-in user
  out: the alerts, unread first
  calls: api [api.1]
  > loads the alerts from [api.1]
  > shows unread ones first, then the rest, each newest first
  note: DIFFERS: web shows a badge count, mobile does not

[c.2] Tap an alert
  in: the alert tapped
  out: the alert opened
  calls: api [api.2]
  > marks it read through [api.2], then opens it
""")
write("ladder/alerts/client/ladder.json", json.dumps({"title": "Alerts client", "tree": "alerts-client.ladder",
    "links": {"api": "../api/ladder.json"},
    "builds": [{"name": "web", "lang": "typescript", "mode": "literal", "files": ["../../../src/web/alerts.ts"]}]}, indent=2))


def hashes(pj):
    """{step id: hash} from `ladder hashes` ("  api.1.1@3f061f  Read the token")."""
    tokens = (line.split()[0] for line in ladder("hashes", pj).splitlines() if line.strip())
    return dict(t.split("@", 1) for t in tokens if "@" in t)


api_pj, client_pj = out / "ladder/alerts/api/ladder.json", out / "ladder/alerts/client/ladder.json"
h = hashes(api_pj)
write("src/api/alerts.ts", f"""\
// @support imports
import {{ db, verify }} from "./lib"
// @end
// @node api.1.1@{h['api.1.1']}
export function readToken(header?: string): string | 401 {{
  if (!header) return 401
  const t = verify(header.replace("Bearer ", ""))
  return t.expired ? 401 : t.userId
}}
// @end
// @node api.1.2@{h['api.1.2']}
export async function loadAlerts(userId: string) {{
  const since = Date.now() - 30 * 24 * 3600 * 1000
  const rows = await db.alerts.where({{ userId }})
  return rows.filter(a => a.createdUtc >= since).sort((a, b) => b.createdUtc - a.createdUtc)
}}
// @end
// @node api.2@{h['api.2']}
export async function markRead(userId: string, id: number): Promise<204 | 404> {{
  const a = await db.alerts.find(id)
  if (!a) return 404
  if (!a.readBy.includes(userId)) a.readBy.push(userId)
  await db.alerts.save(a)
  return 204
}}
// @end
""")
h = hashes(client_pj)
write("src/web/alerts.ts", f"""\
// @node c.1@{h['c.1']}
export async function alertsScreen(api: Api) {{
  const alerts = await api.get("/alerts")
  return [...alerts.filter(a => !a.read), ...alerts.filter(a => a.read)]
}}
// @end
// @node c.2@{h['c.2']}
export async function tapAlert(api: Api, id: number) {{
  await api.post(`/alerts/${{id}}/read`)
  return open(id)
}}
// @end
""")
for pj in (api_pj, client_pj):
    ladder("stamp", pj)
subprocess.run(["git", "-C", str(out), "add", "-A"], check=True)
subprocess.run(["git", "-C", str(out), "-c", "user.name=demo", "-c", "user.email=demo@example.com", "commit", "-qm",
                "approved alerts"], check=True)

# The review: one step's rule changed (its code is now stale, and the client that calls it is told),
# a hand edit to the client's code.
tree = out / "ladder/alerts/api/alerts.ladder"
tree.write_text(tree.read_text().replace("> loads every `Alert` whose `createdUtc` is within 30 days",
                                         "> loads every `Alert` whose `createdUtc` is within 14 days"))
web = out / "src/web/alerts.ts"
web.write_text(web.read_text().replace("return open(id)", "return open(id, { animate: true })"))
print(ladder("check", "--all", out))
print(f"demo repository: {out}")
