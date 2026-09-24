#!/usr/bin/env python3
"""prepush_secret.py — push 前に公開リポジトリへ漏れる秘密情報を内容ベースで検出する。

ファイル拡張子でなく、ファイルの中身のパターン（既知トークン書式・高エントロピー）
から credential っぽい値を推測する。

モード:
  既定    : git diff (未pushコミット分) の追加行のみ検査 → push 直前に必要な最小スキャン
  --all   : 作業ツリー全体を検査（既存repoの棚卸し用。.git 等は除外）

使い方:
  python3 prepush_secret.py [repo] [--all] [--json] [--limit N] [--min-entropy E] [--min-length N]
exit code: 0 = PASS / 1 = 検出あり / 2 = 実行環境エラー
"""
import argparse
import math
import os
import re
import subprocess
import sys

# ---------------------------------------------------------------- 既知トークン書式
KNOWN_PATTERNS = [
    ("GoogleGeminiKey", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("OpenAIKey",       re.compile(r"\bsk-(?:proj-)?[0-9A-Za-z_\-]{20,}\b")),
    ("AnthropicKey",    re.compile(r"\bsk-ant-[0-9A-Za-z_\-]{20,}\b")),
    ("GitHubPAT",       re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36,}\b")),
    ("GitHubFinePat",   re.compile(r"\bgithub_pat_[0-9A-Za-z_]{22,}\b")),
    ("AWSAccessKey",    re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("AWSLegacyKey",    re.compile(r"\b(?:A3T[A-Z0-9]|AGPA[A-Z0-9]|AIDA[A-Z0-9]|AROA[A-Z0-9])[A-Z0-9]{12}\b")),
    ("AWSSecretKeyCtx", re.compile(r"(?i)(?:aws_secret_access_key|aws_secret_key|secret_access_key)\s*[=:]\s*(?:[\"'])?(\S{40})\b")),
    ("SlackToken",      re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}\b")),
    ("SlackWebhook",    re.compile(r"https://hooks\.slack\.com/services/[A-Z0-9]+/[A-Z0-9]+/[A-Za-z0-9]+")),
    ("DiscordWebhook",  re.compile(r"https://discord(?:app)?\.com/api/webhooks/[0-9]+/[A-Za-z0-9_\-]+")),
    ("StripeLiveKey",   re.compile(r"\b(?:sk|rk)_live_[0-9A-Za-z]{16,}\b")),
    ("SquareToken",     re.compile(r"\bEAAA[A-Za-z0-9\-_]{20,}\b")),
    ("SendGridKey",     re.compile(r"\bSG\.[0-9A-Za-z_\-]{20,}\.[0-9A-Za-z_\-]{20,}\b")),
    ("JWT",             re.compile(r"\beyJ[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]{10,}\b")),
    ("PrivateKeyBlock", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("BasicAuthURL",    re.compile(r"https?://[^\s:@/]+:[^\s:@/]+@[^\s:@/]+\.[^\s/]{2,}")),
]

# key っぽい変数名（値が長ければ中一致で HIGH）とその中身を取り出す
KEY_CTX = re.compile(
    r"(?i)(?:api[_-]?key|apikey|secret|token|passwd|password|pwd|client[_-]?secret|"
    r"access[_-]?key|credential|auth[_-]?key|private[_-]?key)\s*[=:]\s*(?:[\"'])?([^\"'\s,:;\]}>]{12,})"
)

# 高エントロピー用の文脈外除外（日付・UUID・hex の 8-8-4 等）
LOW_INFO = re.compile(
    r"(?i)^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|"
    r"[0-9a-f]{24,32}|[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,3}(\.[0-9]{1,3}){3}|"
    r"git[0-9a-f]{40}|commit [0-9a-f]{7,40})$"
)

# 走査除外ディレクトリ（.git 等。拡張子での除外はしない）
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".next",
             "dist", "build", "target", ".cache", "vendor", ".terraform"}
# デフォルトで見ないエントリ（秘密そのものを収める専用場所。--include-hidden で解除）
SEEN_FILES_EXCLUDE = {".env", ".env.*", "*.pem", "*.key", "id_rsa", "id_ed25519",
                      "credentials.json", "client_secret*.json", "key.json", "*.p12", "*.jks"}

_LINE_CACHE = {}


def shannon(s):
    if not s:
        return 0.0
    n = len(s)
    freq = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    h = 0.0
    for f in freq.values():
        p = f / n
        h -= p * math.log2(p)
    return h


def git(args, cwd):
    return subprocess.run(["git"] + args, capture_output=True, text=True,
                          cwd=cwd).stdout


def upstream_base(cwd):
    """未pushコミットの base を返す。無ければ None。"""
    out = git(["rev-parse", "--abbrev-ref", "@{upstream}"], cwd) if subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "@{upstream}"], capture_output=True,
        cwd=cwd).returncode == 0 else ""
    return out.strip() or None


def unpush_changed_files(cwd):
    base = upstream_base(cwd)
    if not base:
        return None, []
    files = git(["diff", "--name-only", "--diff-filter=ACMRT", base + "...HEAD"], cwd)
    return base, [f for f in files.splitlines() if f]


def added_lines_for(files, cwd):
    """未pushコミットで追加された行だけを file -> [(lineno, text)] で返す。"""
    result = {}
    if not files:
        return result
    diff = git(["diff", "--unified=0", "--", *files], cwd)
    cur = None
    newline = 0
    for line in diff.splitlines():
        if line.startswith("+++"):
            cur = line[6:] or None
            newline = 0
        elif line.startswith("@@") and cur is not None:
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            newline = int(m.group(1)) if m else 0
        elif line.startswith("+") and not line.startswith("+++") and cur:
            result.setdefault(cur, []).append((newline, line[1:]))
            newline += 1
        elif line.startswith("-") and not line.startswith("---"):
            pass
        elif line.startswith(" ") and cur is not None:
            newline += 1
    return result


def walk_files(root, include_hidden_seen_files):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            if not include_hidden_seen_files and _seen_excluded(fn):
                continue
            yield full, rel


def _seen_excluded(fn):
    import fnmatch
    return any(fnmatch.fnmatch(fn, pat) for pat in SEEN_FILES_EXCLUDE)


def is_text(path):
    try:
        with open(path, "rb") as f:
            raw = f.read(8192)
        return b"\x00" not in raw
    except OSError:
        return False


def context_scan(ctx_pattern, text, min_length, min_entropy):
    hits = []
    for m in ctx_pattern.finditer(text):
        val = m.group(1)
        ln = len(val)
        if ln < min_length:
            continue
        ent = shannon(val)
        if ent < min_entropy:
            # 既知書式（AKIA 等）は文脈パターンに含まれないので許容
            continue
        if LOW_INFO.match(val):
            continue
        hits.append((val, ent, "HIGH" if ln >= 32 and ent >= 3.8 else "MEDIUM-HIGH"))
    return hits


def known_scan(text):
    hits = []
    for name, pat in KNOWN_PATTERNS:
        for m in pat.finditer(text):
            hits.append((name, m.group(0)))
    return hits


def scan_line(line, min_length, min_entropy):
    """1行を内容ベースで検査 → [{detector,value,severity,entropy}]（既知書式優先・重複排除）"""
    findings = []
    seen = set()
    for name, val in known_scan(line):
        if (name, val) not in seen:
            seen.add((name, val))
            findings.append({"detector": name, "value": val[:48], "severity": "HIGH"})
    known_vals = {f["value"] for f in findings}
    for val, ent, sev in context_scan(KEY_CTX, line, min_length, min_entropy):
        if ("KeyCtxHighEntropy", val) in seen:
            continue
        if any(val.startswith(k) for k in known_vals):
            continue
        seen.add(("KeyCtxHighEntropy", val))
        findings.append({"detector": "KeyCtxHighEntropy",
                         "value": val[:48], "severity": sev,
                         "entropy": round(ent, 2)})
    return findings[:5]


def scan_text(text, min_length, min_entropy):
    """全行を走査 → [(lineno, col, detector, entropy, severity, value)]"""
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for row in scan_line(line, min_length, min_entropy):
            col = max(line.find(row["value"]), 0)
            out.append((lineno, col, row["detector"], row.get("entropy"),
                        row["severity"], row["value"]))
    return out


def main():
    ap = argparse.ArgumentParser(description="pre-push secret scan (content-based)")
    ap.add_argument("repo", nargs="?", default=".", help="git repo path")
    ap.add_argument("--all", action="store_true", help="scan whole working tree, not just unpushed diff")
    ap.add_argument("--include-hidden", action="store_true", help="also scan .env / key.json / *.pem 等")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--min-length", type=int, default=16)
    ap.add_argument("--min-entropy", type=float, default=3.2)
    args = ap.parse_args()

    root = os.path.abspath(args.repo)
    if not os.path.isdir(os.path.join(root, ".git")):
        print(f"ERROR: {root} は git repo ではない", file=sys.stderr)
        return 2

    findings = []

    if args.all:
        for full, rel in walk_files(root, args.include_hidden):
            if not is_text(full):
                continue
            try:
                with open(full, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError:
                continue
            for lineno, col, det, ent, sev, val in scan_text(text, args.min_length, args.min_entropy):
                findings.append((rel, lineno, col, det, ent, sev, val))
    else:
        base, files = unpush_changed_files(root)
        if base is None:
            print("NO-UPSTREAM: 未pushの比べる先がない。--all で全体スキャンしてから push。", file=sys.stderr)
            return 2
        added = added_lines_for(files, root)
        for rel, lines in added.items():
            for lineno, line in lines:
                for row in scan_line(line, args.min_length, args.min_entropy):
                    findings.append((rel, lineno,
                                     max(line.find(row["value"]), 0),
                                     row["detector"], row.get("entropy"),
                                     row["severity"], row["value"]))

    findings = findings[: args.limit]
    if args.json:
        import json
        payload = {
            "repo": root,
            "mode": "all" if args.all else "diff",
            "count": len(findings),
            "blocker": any(f[5].startswith("HIGH") for f in findings),
            "findings": [
                {"file": f[0], "line": f[1], "col": f[2], "detector": f[3],
                 "entropy": f[4], "severity": f[5], "value": f[6]} for f in findings
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if not findings:
            print("PASS: 秘密っぽい値は検出されなかった")
            return 0
        print(f"BLOCKER: {sum(1 for f in findings if f[5].startswith('HIGH'))} HIGH / "
              f"{sum(1 for f in findings if not f[5].startswith('HIGH'))} MEDIUM")
        for rel, lineno, col, det, ent, sev, val in findings:
            ent_s = f" ent={ent}" if ent is not None else ""
            print(f"  [{sev}]{ent_s} {rel}:{lineno}:{col} <{det}> {val}")
    return 1 if any(f[5].startswith("HIGH") for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())