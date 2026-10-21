#!/usr/bin/env python3
"""Claude Code token usage per GitHub repo, from local transcripts (~/.claude/projects/**/*.jsonl).

Each assistant message carries `usage` and the `cwd` it ran in. The cwd is mapped to the git repo
that contains it (origin remote name). Messages are de-duplicated by (message.id, requestId),
because resumed and forked sessions repeat earlier lines.

    python3 token_stats.py [--out stats.json]
"""
import argparse, json, os, re, subprocess, sys
from collections import defaultdict
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
_repo_cache: dict[str, str | None] = {}
# Folders and repos that were renamed after the transcripts were written.
PATH_ALIASES = {str(Path.home() / "Desktop/Projects/code hackathon project"): str(Path.home() / "Desktop/Projects/hoopergpt")}
NAME_ALIASES = {"code-hackathon-project": "hoopergpt"}


def repo_of(cwd: str) -> str | None:
    if cwd in _repo_cache:
        return _repo_cache[cwd]
    key = cwd
    for old, new in PATH_ALIASES.items():
        if cwd == old or cwd.startswith(old + "/"):
            cwd = new + cwd[len(old):]
    p, name = Path(cwd), None
    while p != p.parent and not p.exists():
        p = p.parent
    for d in [p, *p.parents]:
        if (d / ".git").exists():
            try:
                url = subprocess.run(["git", "-C", str(d), "remote", "get-url", "origin"],
                                     capture_output=True, text=True, timeout=5).stdout.strip()
            except Exception:
                url = ""
            if "github.com" in url and "Malek1414/" in url:
                name = url.rstrip("/").removesuffix(".git").split("Malek1414/")[-1]
                name = NAME_ALIASES.get(name, name)
            break
        if d == Path.home():
            break
    _repo_cache[key] = name
    return name


def collect() -> dict:
    """Totals and per-repo usage: {"first", "last", "totals", "repos": [...]}, biggest repo first."""
    seen = set()
    per = defaultdict(lambda: defaultdict(int))
    days = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))  # date -> repo -> field
    first, last = None, None
    path_re = re.compile(r"/Users/[^\s\"'`]+")
    for f in PROJECTS.rglob("*.jsonl"):
        session_repo = None  # last repo this transcript touched through a tool call
        try:
            fh = f.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                m = e.get("message") or {}
                u = m.get("usage")
                if e.get("type") != "assistant" or not isinstance(u, dict):
                    continue
                key = (m.get("id"), e.get("requestId"))
                if key[0] and key in seen:
                    continue
                seen.add(key)
                ts = e.get("timestamp")
                if ts:
                    first = ts if first is None or ts < first else first
                    last = ts if last is None or ts > last else last
                touched = None
                for c in m.get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "tool_use":
                        for hit in path_re.findall(json.dumps(c.get("input") or {})):
                            r = repo_of(hit.rstrip(".,);:"))
                            if r:
                                touched = r
                repo = repo_of(e.get("cwd") or "") or touched or session_repo or "(no repo)"
                if touched or repo_of(e.get("cwd") or ""):
                    session_repo = touched or repo_of(e.get("cwd") or "")
                b = per[repo]
                b["input"] += u.get("input_tokens") or 0
                b["output"] += u.get("output_tokens") or 0
                b["cache_write"] += u.get("cache_creation_input_tokens") or 0
                b["cache_read"] += u.get("cache_read_input_tokens") or 0
                b["messages"] += 1
                if ts:
                    dd = days[ts[:10]][repo]
                    dd["total"] += sum((u.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
                    dd["output"] += u.get("output_tokens") or 0
    rows = []
    for repo, b in per.items():
        b = dict(b)
        b["total"] = b["input"] + b["output"] + b["cache_write"] + b["cache_read"]
        b["fresh"] = b["input"] + b["output"] + b["cache_write"]
        rows.append({"repo": repo, **b})
    rows.sort(key=lambda r: r["total"], reverse=True)
    tot = {k: sum(r[k] for r in rows) for k in ("input", "output", "cache_write", "cache_read", "total", "fresh", "messages")}
    by_day = {d: {r: dict(v) for r, v in reps.items()} for d, reps in sorted(days.items())}
    return {"first": first, "last": last, "totals": tot, "repos": rows, "days": by_day}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    result = collect()
    first, last, tot, rows = result["first"], result["last"], result["totals"], result["repos"]
    if args.out:
        args.out.write_text(json.dumps(result, indent=2))
    print(json.dumps({"first": first, "last": last, "totals": tot}, indent=1))
    for r in rows[:40]:
        print(f"{r['repo'][:34]:34} total={r['total']:>15,} fresh={r['fresh']:>13,} out={r['output']:>11,} msgs={r['messages']:>7,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
