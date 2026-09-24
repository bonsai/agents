#!/usr/bin/env python3
"""triage_gh.py — GitHub (bonsai) の統合 issue 収集・構造化・タスク化。

Codec: UTF-8 前提。
mode: sync | triage | report | tasks | all
  sync   : GitHub Search API で open issue を収集し triage.db へ upsert
  triage : body メタデータ (Type/Project/Agent/Weight) + labels で priority 再計算
  report : 短い日本語で要約
  tasks  : data/tasks.md を生成
"""
import json
import os
import re
import subprocess
import sys
import time
import sqlite3
from urllib.parse import quote

HOME = os.path.expanduser("~")
AGENT_DIR = os.path.join(HOME, ".opencode", "agents")
DB_PATH = os.path.join(AGENT_DIR, "data", "triage.db")
TASKS_PATH = os.path.join(AGENT_DIR, "data", "tasks.md")

ORG = "bonsai"
MIN_CORE = 50
MIN_SEARCH = 5
PAGE_CAP = 10  # search API 上限 1000 results

# AGENTS.md 優先順位 → 基準 priority
REPO_RANK = [
    (re.compile(r"eki-ben"), 0),
    (re.compile(r"extreme-norikae"), 0),
    (re.compile(r"game-portal"), 1),
    (re.compile(r"\.py$"), 1),   # python 系 repo → 1
]
DEFAULT_RANK = 2

TITLE_PREFIX = re.compile(r"^\[([^\]]+)\]\s*(.*)$")


def sh(args: list[str]) -> str:
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"CMD FAIL: {' '.join(args)}\n{r.stderr}\n")
        sys.exit(1)
    return r.stdout


def rate_left(resource: str) -> int:
    out = sh(["gh", "api", "rate_limit", "--jq", f".resources.{resource}.remaining"])
    return int(out.strip())


def open_db():
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS issues (
      id         TEXT PRIMARY KEY,
      repo       TEXT NOT NULL,
      number     INTEGER NOT NULL,
      state      TEXT NOT NULL,
      title      TEXT,
      url        TEXT,
      created_at TEXT,
      updated_at TEXT,
      labels     TEXT,
      author     TEXT,
      comments   INTEGER DEFAULT 0,
      body       TEXT,
      type       TEXT,
      project    TEXT,
      agent      TEXT,
      weight     REAL,
      local_path TEXT,
      priority   INTEGER DEFAULT 2,
      note       TEXT,
      fetched_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS deps (
      id TEXT NOT NULL, number INTEGER NOT NULL,
      depends_on INTEGER NOT NULL,
      PRIMARY KEY (id, depends_on)
    );
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS repos (
      repo TEXT PRIMARY KEY, pushed_at TEXT, private INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS feedback (
      repo TEXT, typ TEXT, done INTEGER DEFAULT 0, open INTEGER DEFAULT 0,
      PRIMARY KEY (repo, typ)
    );
    """)
    return con


def meta_get(con, key, default=None):
    row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def meta_set(con, key, value):
    con.execute("INSERT INTO meta(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    con.commit()


def repo_from_url(repository_url: str) -> str:
    parts = repository_url.rstrip("/").split("/")
    return parts[-1]


def search_pages(query: str):
    page = 1
    pages = []
    while page <= PAGE_CAP:
        q = quote(query)
        url = f"/search/issues?q={q}&sort=updated&order=desc&per_page=100&page={page}"
        data = json.loads(sh(["gh", "api", url]))
        items = data.get("items", [])
        pages.append(data)
        if len(items) < 100:
            break
        page += 1
        time.sleep(2.5)  # search 30/min 対策
    return pages


def upsert_issue(con, repo, it):
    labels = ",".join(l["name"] for l in (it.get("labels") or []))
    user = (it.get("user") or {}).get("login", "")
    iid = f"{repo}#{it['number']}"
    con.execute("""
      INSERT INTO issues
        (id, repo, number, state, title, url, created_at, updated_at,
         labels, author, comments, body, fetched_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?, datetime('now'))
      ON CONFLICT(id) DO UPDATE SET
        state=excluded.state, title=excluded.title, url=excluded.url,
        created_at=excluded.created_at, updated_at=excluded.updated_at,
        labels=excluded.labels, author=excluded.author,
        comments=excluded.comments, body=excluded.body,
        fetched_at=excluded.fetched_at
    """, (iid, repo, it["number"], it.get("state", "open"), it.get("title", ""),
          it.get("html_url", ""), it.get("created_at", ""), it.get("updated_at", ""),
          labels, user, it.get("comments", 0) or 0, it.get("body") or ""))
    return iid


# ---------- metadata ----------

META_KEYS = ["type", "project", "agent", "weight", "local_path"]
_META_PAT = {k: re.compile(rf"^\*?\*?{k}\*?\*?\s*:\s*(.+)$", re.I | re.M)
             for k in META_KEYS}
_META_TITLE = re.compile(r"Type\s*:\s*(\S+)")
_DEPEND_LINK = re.compile(r"depends?\s+on\s+#?(\d+)", re.I)


def parse_meta(body: str):
    m = {k: None for k in META_KEYS}
    if not body:
        return m
    for k in META_KEYS:
        mm = _META_PAT[k].search(body)
        if mm:
            val = mm.group(1).strip()
            if k == "weight":
                try:
                    m[k] = float(val)
                except ValueError:
                    pass
            else:
                m[k] = val
    return m


def parse_deps(body: str, iid: str):
    return sorted(int(x) for x in _DEPEND_LINK.findall(body or ""))


def repo_base_priority(repo: str) -> int:
    for pat, rank in REPO_RANK:
        if pat.search(repo):
            return rank
    return DEFAULT_RANK


def infer_type(title: str, meta_type) -> str:
    if meta_type:
        return meta_type.lower()
    pm = TITLE_PREFIX.match(title or "")
    if pm:
        return pm.group(1).lower()
    return None


def repo_activity_offset(con, repo):
    """repo の最終 push からの日数で補正。活発(≤7日)=-1, 放置(>180日)=+1。"""
    row = con.execute("SELECT pushed_at FROM repos WHERE repo=?", (repo,)).fetchone()
    if not row or not row[0]:
        return 0
    try:
        from datetime import datetime, timezone
        pushed = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
        days = (datetime.now(timezone.utc) - pushed).days
    except Exception:
        return 0
    if days <= 7:
        return -1
    if days <= 45:
        return 0
    if days <= 180:
        return 0
    return 1


def score_priority(con, repo, row, labels):
    p = repo_base_priority(repo)
    lab = (labels or "").lower().split(",")
    has_bug = any("bug" in x for x in lab)
    has_weight = bool(row.get("weight") and row.get("weight") >= 0.6)
    # repo活動: 直近pushは bug/weight のある work のみ前倒し (機械的P0洪水を防ぐ)
    act = repo_activity_offset(con, repo)
    if act == -1 and (has_bug or has_weight):
        p -= 1
    elif act == 1:
        p += 1
    if has_bug:
        p -= 1
    if has_weight:
        p -= 1
    updated = (row.get("updated_at") or "")
    if updated:
        try:
            from datetime import datetime, timezone
            upd = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - upd).days
            if age >= 90:
                p += 1
            elif age <= 7:
                p -= 1
        except Exception:
            pass
    typ = row.get("type")
    if typ in ("memory", "doc") and not row.get("weight"):
        p += 1
    return max(0, min(3, p))


# ---------- modes ----------

def fetch_issue(it, con):
    """search / issue REST の item を DB へ upsert。PR は除外。"""
    if "pull_request" in it:   # issues endpoint は PR を含む場合がある
        return None
    repo = repo_from_url(it["repository_url"])
    iid = upsert_issue(con, repo, it)
    deps = parse_deps(it.get("body") or "", iid)
    for d in deps:
        con.execute("INSERT OR IGNORE INTO deps(id,number,depends_on) VALUES(?,?,?)",
                    (iid, it["number"], d))
    return iid


def cmd_sync_deep():
    """per-repo REST で全 open issue を回収 (search上限1000を超える場合用)。"""
    con = open_db()
    if rate_left("core") < MIN_CORE:
        print("core rate limit 残少 → 取得中止")
        return
    repo_names = sh(["gh", "repo", "list", ORG, "--limit", "1000",
                     "--json", "name", "--jq", ".[].name"]).split()
    print(f"repos: {len(repo_names)}")
    total = 0
    for i, name in enumerate(repo_names):
        page = 1
        while True:
            data = json.loads(sh(["gh", "api",
                                  f"/repos/{ORG}/{name}/issues?state=open&per_page=100&page={page}"]))
            items = [it for it in data if "pull_request" not in it]
            total += len(items)
            for it in items:
                fetch_issue(it, con)
            con.commit()
            if len(data) < 100:
                break
            page += 1
        if (i + 1) % 200 == 0:  # 暴走ガード: 200 repoごとに残量確認
            if rate_left("core") < MIN_CORE:
                print(f"rate limit 残少 → {name} で停止 (partial)")
                break
    meta_set(con, "last_sync", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    print(f"deep sync: {total} issues upserted ({len(repo_names)} repos)")


def cmd_sync_repo_activity(con):
    """/user/repos (全repo, private含む) を一括取得して pushed_at を記録。10ページ程度で安価。"""
    if rate_left("core") < MIN_CORE:
        print("core rate limit 残少 → repo activity 取得中止")
        return
    total = 0
    page = 1
    while True:
        data = json.loads(sh(["gh", "api",
                              f"/user/repos?affiliation=owner&per_page=100&page={page}"]))
        if not data:
            break
        for r in data:
            con.execute("INSERT INTO repos(repo, pushed_at, private) VALUES(?,?,?) "
                        "ON CONFLICT(repo) DO UPDATE SET pushed_at=excluded.pushed_at, "
                        "private=excluded.private", (r["name"], r.get("pushed_at", ""),
                                                     r.get("private", False) and 1 or 0))
            total += 1
        if len(data) < 100:
            break
        page += 1
        time.sleep(1)
    con.commit()
    print(f"repo activity: {total} repos")


def read_feedback_from_tasks(con):
    """tasks.md の [x] (完了) を feedback テーブルへ学習。"""
    try:
        with open(TASKS_PATH, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return
    done = {"#": {}}
    for line in text.splitlines():
        m = re.match(r"- \[x\] `([^`#]+)#(\d+)`", line)
        if m:
            con.execute("UPDATE issues SET note='done-by-user' "
                        "WHERE repo=? AND number=?", (m.group(1), int(m.group(2))))
    con.commit()


def learn_feedback(con):
    """完了済み vs 未完了 の比率から repo×type の補正係数を学習。"""
    read_feedback_from_tasks(con)
    rows = con.execute(
        "SELECT repo, type, "
        "  SUM(CASE WHEN note='done-by-user' THEN 1 ELSE 0 END) AS done, "
        "  SUM(CASE WHEN note IS NULL OR note != 'done-by-user' THEN 1 ELSE 0 END) AS open "
        "FROM issues WHERE type IS NOT NULL GROUP BY repo, type").fetchall()
    learned = 0
    for repo, typ, d, o in rows:
        d = d or 0
        o = o or 0
        ratio = d / (d + o + 1)
        con.execute("INSERT INTO feedback(repo, typ, done, open) VALUES(?,?,?,?) "
                    "ON CONFLICT(repo, typ) DO UPDATE SET done=excluded.done, open=excluded.open",
                    (repo, typ, d, o))
        # 同じ repo×type 体系が人間に消化されている → 残りも前倒し
        if ratio >= 0.5 and o > 0:
            con.execute("UPDATE issues "
                        "SET priority = CASE WHEN priority > 0 THEN priority-1 ELSE 0 END "
                        "WHERE repo=? AND type=? AND (note IS NULL OR note != 'done-by-user')",
                        (repo, typ))
            learned += 1
    con.commit()
    if learned:
        print(f"learn: {learned} 件をフィードバックで前倒し")


def cmd_sync(cache_only=False, deep=False):
    con = open_db()
    if cache_only:
        print("cache-only")
    elif deep:
        cmd_sync_repo_activity(con)
        cmd_sync_deep()
    else:
        if rate_left("core") < MIN_CORE:
            print("core rate limit 残少 → 取得中止 (cache で運用)")
            return
        if rate_left("search") < MIN_SEARCH:
            print("search rate limit 残少 → 取得中止 (cache で運用)")
            return
        q = f"user:{ORG} is:issue is:open"
        since = meta_get(con, "last_sync")
        if since:
            q += f" updated:>{since}"
        pages = search_pages(q)
        total = 0
        for data in pages:
            items = data.get("items", [])
            total += len(items)
            for it in items:
                fetch_issue(it, con)
        con.commit()
        meta_set(con, "last_sync", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        print(f"sync: {total} issues upserted")
    cmd_triage(con=con)


def cmd_triage(con=None, print_summary=True):
    own = con is None
    con = con or open_db()
    learn_feedback(con)
    rows = con.execute("SELECT id, repo, number, title, body, labels, updated_at, type, weight "
                       "FROM issues").fetchall()
    stats = {"0高": 0, "1中": 0, "2低": 0, "3保": 0, "type?": 0}
    for (iid, repo, num, title, body, labels, updated, typ, weight) in rows:
        m = parse_meta(body)
        itype = infer_type(title, typ or m.get("type"))
        meta = {"type": itype, "project": m.get("project"), "agent": m.get("agent"),
                "weight": m.get("weight"), "local_path": m.get("local_path"),
                "updated_at": updated}
        p = score_priority(con, repo, meta, labels)
        con.execute("UPDATE issues SET type=?, project=?, agent=?, weight=?, local_path=?, priority=? "
                    "WHERE id=?", (itype, m.get("project"), m.get("agent"),
                                   m.get("weight"), m.get("local_path"), p, iid))
        if itype is None:
            stats["type?"] += 1
        stats[f"{p}高" if p == 0 else f"{p}中" if p == 1 else f"{p}低" if p == 2 else "3保"] += 1
    con.commit()
    if print_summary:
        print(f"triage: {len(rows)} issues  → 優先度 {stats}")
    if own:
        con.close()


def cmd_report():
    cmd_triage(print_summary=False)
    con = open_db()
    total, repos = con.execute("SELECT count(*), count(DISTINCT repo) FROM issues").fetchone()
    by_prio = con.execute("SELECT priority, count(*) FROM issues GROUP BY priority ORDER BY priority").fetchall()
    p0_all = next((c for p, c in by_prio if p == 0), 0)
    prio_s = " / ".join(f"P{i}:{c}" for i, c in by_prio)
    print(f"## 要約  {total} issues / {repos} repos   ({prio_s})")
    hot = con.execute(
        "SELECT repo, SUM(CASE WHEN priority<=1 THEN 1 ELSE 0 END) c FROM issues "
        "GROUP BY repo ORDER BY c DESC LIMIT 8").fetchall()
    print("## ホットrepo  " + ", ".join(f"{r}:{c}" for r, c in hot))
    rows = con.execute(
        "SELECT repo, number, title, labels, updated_at FROM issues WHERE priority=0 "
        "ORDER BY CASE WHEN labels LIKE '%bug%' THEN 0 ELSE 1 END, updated_at DESC LIMIT 10").fetchall()
    print("## 今やる (P0)  TOP10  ※全件は tasks.md")
    for repo, num, title, labels, _u in rows:
        short = title[:52] + ("…" if len(title) > 52 else "")
        tag = " bug" if "bug" in (labels or "") else ""
        print(f"  {repo}#{num} {short}{tag}")
    print(f"  （P0 残り {p0_all - len(rows)} 件 / 全体 {total} 件は data/tasks.md）")
    con.close()


def cmd_tasks():
    con = open_db()
    prio_names = {0: "🔴 今やる", 1: "🟡 近いうち", 2: "🟢 積む", 3: "⚪ 保留"}
    out = ["# Tasks (triage.md 生成)", "",
           f"> 生成: {time.strftime('%Y-%m-%d %H:%M', time.localtime())} | 元: data/triage.db",
           ]
    rows = con.execute("SELECT repo, number, title, priority, type, weight, labels "
                       "FROM issues ORDER BY priority, repo, number").fetchall()
    for p in (0, 1, 2, 3):
        group = [r for r in rows if r[3] == p]
        if not group:
            continue
        out.append(f"## {prio_names[p]} ({len(group)})")
        for repo, num, title, _p, typ, weight, labels in group:
            meta = " / ".join(x for x in [typ, f"w{weight}" if weight else "", labels] if x)
            out.append(f"- [ ] `{repo}#{num}` {title}  {meta}")
        out.append("")
    with open(TASKS_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"tasks.md 更新: {TASKS_PATH} ({len(rows)} tasks)")


def cmd_all(deep=False):
    if deep:
        cmd_sync(deep=True)
    else:
        cmd_sync()
    cmd_triage()
    cmd_report()
    cmd_tasks()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    cache_only = "--cache-only" in sys.argv
    deep = "--deep" in sys.argv
    if mode == "sync":
        cmd_sync(cache_only=cache_only, deep=deep)
    elif mode == "triage":
        cmd_triage()
    elif mode == "report":
        cmd_report()
    elif mode == "tasks":
        cmd_tasks()
    elif mode == "all":
        cmd_all(deep=deep)
    else:
        sys.stderr.write(f"unknown mode: {mode}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()