#!/usr/bin/env python3
"""Build the animated token-spend chart and the Dune card for the profile README.

Reads local Claude Code transcripts through token_stats.py, keeps public repos by name and folds
private ones into one bar, then writes:
  assets/tokens-dark.svg, assets/tokens-light.svg   bars grow in, a light sweep runs along them
  assets/dune-dark.svg,   assets/dune-light.svg     a pixel sandworm and the "how many Dunes" stat
  assets/commits-dark.svg, assets/commits-light.svg  commits per repo on default branches, mine and others'
  assets/tokens.json, assets/commits.json           the numbers behind them (no private repo names)

    python3 tools/build_profile.py          # needs `gh` logged in, to know which repos are public
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import readme_art as art  # noqa: E402
import token_stats  # noqa: E402

ASSETS = ROOT / "assets"
FONT = art.FONT
# Dune (Frank Herbert, 1965): published estimates run from about 175,000 to 188,000 words.
# At roughly 1.3 tokens per English word that is about 244,000 tokens for the 188k figure.
DUNE_WORDS = 188_000
TOKENS_PER_WORD = 1.3
DUNE_TOKENS = DUNE_WORDS * TOKENS_PER_WORD
THEMES = {
    "dark": {"bg": "#0d1117", "ink": "#f0f3f6", "muted": "#9198a1", "track": "#1c2129", "accent": "#ff6a2b",
             "accent2": "#ffb347", "private": "#8957e5", "general": "#3d444d", "sand": "#d9a55b", "sand2": "#b7833f"},
    "light": {"bg": "#ffffff", "ink": "#1f2328", "muted": "#59636e", "track": "#f3f1ec", "accent": "#e0531a",
              "accent2": "#f08c1a", "private": "#8250df", "general": "#c9ced4", "sand": "#d19a4c", "sand2": "#a8742f"},
}


LEDGER = Path.home() / ".local" / "share" / "claude-profile" / "ledger.json"
STATS_CACHE = Path.home() / ".claude" / "stats-cache.json"


def update_ledger(days):
    """Keep per-day, per-repo totals after Claude Code deletes old transcripts (about 30 days).

    Each run adds what the transcripts still show; a day/repo pair keeps the larger of the old
    and new numbers, so nothing shrinks when its transcript is cleaned up. Stays on this Mac."""
    ledger = json.loads(LEDGER.read_text()) if LEDGER.exists() else {"days": {}}
    for day, repos in days.items():
        slot = ledger["days"].setdefault(day, {})
        for repo, v in repos.items():
            if v["total"] >= slot.get(repo, {}).get("total", 0):
                slot[repo] = v
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(ledger, indent=1, sort_keys=True))
    return ledger["days"]


def model_name(m):
    parts = m.removeprefix("claude-").split("-")
    family = parts[0].capitalize()
    nums = [p for p in parts[1:] if p.isdigit() and len(p) < 3]
    return f"{family} {'.'.join(nums)}".strip()


def collect():
    """All-time numbers from Claude Code's /stats cache, per-repo numbers from the transcript ledger."""
    t = token_stats.collect()
    days = update_ledger(t["days"])
    listing = json.loads(subprocess.run(
        ["gh", "repo", "list", "Malek1414", "--limit", "300", "--json", "name,visibility"],
        capture_output=True, text=True, check=True).stdout)
    public = {r["name"] for r in listing if r["visibility"] == "PUBLIC"}

    # Per repo, over every day the ledger has seen.
    per = {}
    for repos in days.values():
        for repo, v in repos.items():
            agg = per.setdefault(repo, {"total": 0, "output": 0})
            agg["total"] += v["total"]
            agg["output"] += v["output"]
    rows, private, general = [], {"total": 0, "output": 0, "count": 0}, None
    for repo, v in per.items():
        if repo == "(no repo)":
            general = {"label": "general sessions", "kind": "general", **v}
        elif repo in public:
            rows.append({"label": repo, "kind": "public", **v})
        else:
            private["total"] += v["total"]
            private["output"] += v["output"]
            private["count"] += 1
    rows.sort(key=lambda r: r["total"], reverse=True)
    shown, rest = rows[:9], rows[9:]
    if rest:
        shown.append({"label": f"{len(rest)} more public repos", "kind": "public",
                      "total": sum(r["total"] for r in rest), "output": sum(r["output"] for r in rest)})
    if private["count"]:
        shown.append({"label": f"{private['count']} private repos", "kind": "private",
                      "total": private["total"], "output": private["output"]})
    shown.sort(key=lambda r: r["total"], reverse=True)
    if general:
        shown.append(general)
    window = {"first": min(days), "last": max(days), "total": sum(r["total"] for r in shown),
              "output": sum(r["output"] for r in shown)}

    # All time: the /stats cache up to its last computed day, the ledger after that.
    cache = json.loads(STATS_CACHE.read_text())
    cut = cache["lastComputedDate"]
    daily = {x["date"]: sum(x["tokensByModel"].values()) for x in cache["dailyModelTokens"]}
    for day, repos in days.items():
        if day > cut:
            daily[day] = sum(v["total"] for v in repos.values())
    models = {}
    for m, u in cache["modelUsage"].items():
        name = model_name(m)
        models[name] = models.get(name, 0) + u["inputTokens"] + u["outputTokens"] + u["cacheReadInputTokens"] + u["cacheCreationInputTokens"]
    after = [v for day, repos in days.items() if day > cut for v in repos.values()]
    total = sum(models.values()) + sum(v["total"] for v in after)
    output = sum(u["outputTokens"] for u in cache["modelUsage"].values()) + sum(v["output"] for v in after)
    return {
        "built": datetime.now().strftime("%Y-%m-%d"), "since": min(daily), "last": max(daily),
        "total": total, "output": output, "sessions": cache["totalSessions"], "messages": cache["totalMessages"],
        "daily": dict(sorted(daily.items())), "models": dict(sorted(models.items(), key=lambda kv: -kv[1])),
        "window": window, "rows": shown, "dune_tokens": DUNE_TOKENS,
    }


COMMITS_QUERY = """query($owner: String!, $uid: ID!) {
  user(login: $owner) { repositories(first: 100, ownerAffiliations: OWNER, isFork: false) { nodes {
    name visibility
    defaultBranchRef { target { ... on Commit { mine: history(author: {id: $uid}) { totalCount } all: history { totalCount } } } }
  } } }
}"""


def collect_commits():
    """Commits on each repo's default branch: mine (author linked to my account) and everyone else's."""
    uid = subprocess.run(["gh", "api", "user", "--jq", ".node_id"], capture_output=True, text=True, check=True).stdout.strip()
    raw = json.loads(subprocess.run(
        ["gh", "api", "graphql", "-F", "owner=Malek1414", "-F", f"uid={uid}", "-f", f"query={COMMITS_QUERY}"],
        capture_output=True, text=True, check=True).stdout)
    rows, private = [], {"mine": 0, "others": 0, "count": 0}
    for n in raw["data"]["user"]["repositories"]["nodes"]:
        t = (n.get("defaultBranchRef") or {}).get("target") or {}
        mine, total = t.get("mine", {}).get("totalCount", 0), t.get("all", {}).get("totalCount", 0)
        if n["name"].endswith("-repochad") or total == 0:  # private mirrors would count the same commits twice
            continue
        if n["visibility"] == "PUBLIC":
            rows.append({"label": n["name"], "kind": "public", "mine": mine, "others": total - mine})
        else:
            private["mine"] += mine
            private["others"] += total - mine
            private["count"] += 1
    rows.sort(key=lambda r: r["mine"], reverse=True)
    shown, rest = rows[:11], rows[11:]
    if rest:
        shown.append({"label": f"{len(rest)} more public repos", "kind": "public",
                      "mine": sum(r["mine"] for r in rest), "others": sum(r["others"] for r in rest)})
    shown.append({"label": f"{private['count']} private repos", "kind": "private", "mine": private["mine"], "others": private["others"]})
    shown.sort(key=lambda r: r["mine"], reverse=True)
    mine_total = sum(r["mine"] for r in shown)
    others_total = sum(r["others"] for r in shown)
    return {"built": datetime.now().strftime("%Y-%m-%d"), "mine": mine_total, "others": others_total,
            "repos": len(rows) + private["count"], "rows": shown}


GREEN = {"dark": ("#2ea043", "#56d364", "#8957e5", "#2d333b"), "light": ("#1a7f37", "#2da44e", "#8250df", "#d0d7de")}


def commits_chart(d, theme):
    t = THEMES[theme]
    g1, g2, priv, other = GREEN[theme]
    rows = d["rows"]
    width, top, rh = 1200, 150, 34
    height = top + rh * len(rows) + 56
    bar_x, bar_max = 290, 760
    # Scale to my biggest public repo. A bar longer than `cap` is drawn shortened, with a break
    # mark on the part that was shortened (the private total, or a collaborator's commits).
    cap = bar_max - 200
    peak = max(r["mine"] for r in rows if r["kind"] != "private")
    out, defs = [], []
    for i, r in enumerate(rows):
        y = top + i * rh
        wm = cap * r["mine"] / peak
        wo = cap * r["others"] / peak
        brk = None
        if wm > cap:                      # my own commits don't fit: shorten them, keep others' share
            share = r["others"] / (r["mine"] + r["others"])
            wm, wo = cap * (1 - share), cap * share
            brk = 0.62 * wm
        elif wm + wo > cap:               # someone else's commits don't fit: shorten only those
            wo = cap - wm
            brk = wm + 0.5 * wo
        wm = max(4, wm) if r["mine"] else 0
        fill = priv if r["kind"] == "private" else f"url(#cg-{theme})"
        delay = 0.15 + i * 0.09
        defs.append(f'<clipPath id="cc{i}-{theme}"><rect x="{bar_x}" y="{y}" width="{wm:.1f}" height="22" rx="5"/></clipPath>')
        label = f"{r['mine']:,}" + (f" <tspan style=\"fill:{t['muted']}\" font-weight=\"400\">+ {r['others']:,} by others</tspan>" if r["others"] else "")
        out.append(
            f'<text class="lbl" x="{bar_x - 16}" y="{y + 16}" text-anchor="end" style="animation-delay:{delay:.2f}s">{art.esc(r["label"])}</text>'
            + (f'<rect class="bar" x="{bar_x + wm:.1f}" y="{y}" width="{wo:.1f}" height="22" rx="5" fill="{other}" style="animation-delay:{delay + 0.35:.2f}s"/>' if wo else "")
            + f'<rect class="bar" x="{bar_x}" y="{y}" width="{wm:.1f}" height="22" rx="5" fill="{fill}" style="animation-delay:{delay:.2f}s"/>'
            f'<g clip-path="url(#cc{i}-{theme})"><rect class="sheen" x="{bar_x - 120}" y="{y}" width="90" height="22" fill="url(#s-{theme})" style="animation-delay:{1.4 + i * 0.12:.2f}s"/></g>'
            + (f'<path class="bar" d="M{bar_x + brk - 4:.1f} {y + 25} l8 -28 M{bar_x + brk + 3:.1f} {y + 25} l8 -28" stroke="{t["bg"]}" stroke-width="3.5" style="animation-delay:{delay + 0.35:.2f}s"/>' if brk is not None else "")
            + f'<text class="val" x="{bar_x + wm + wo + 10:.1f}" y="{y + 16}" style="animation-delay:{delay + 0.5:.2f}s">{label}</text>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Commits by repo: {d['mine']:,} of mine across {d['repos']} repos">
<defs>
  <linearGradient id="cg-{theme}" x1="0" x2="1"><stop offset="0" stop-color="{g1}"/><stop offset="1" stop-color="{g2}"/></linearGradient>
  <linearGradient id="s-{theme}" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".55"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
  {''.join(defs)}
</defs>
<style>
  text {{ font-family: {FONT}; fill: {t['ink']}; }}
  .h {{ font-weight: 700; letter-spacing: -0.02em; }}
  .lbl {{ font-size: 15px; fill: {t['muted']}; opacity: 0; animation: fade .6s ease both; }}
  .val {{ font-size: 15px; font-weight: 600; opacity: 0; animation: fade .6s ease both; }}
  .bar {{ transform-box: fill-box; transform-origin: left center; transform: scaleX(0); animation: grow 1.1s cubic-bezier(.2,.9,.3,1) both; }}
  .sheen {{ animation: sweep 3.6s ease-in-out infinite; }}
  @keyframes grow {{ to {{ transform: scaleX(1); }} }}
  @keyframes fade {{ to {{ opacity: 1; }} }}
  @keyframes sweep {{ 0% {{ transform: translateX(0); }} 60%, 100% {{ transform: translateX({bar_max + 240}px); }} }}
  .ants {{ fill: none; stroke: {g1}; stroke-width: 2; stroke-dasharray: 8 6; animation: march 1.2s linear infinite; }}
  @keyframes march {{ to {{ stroke-dashoffset: -28; }} }}
  @media (prefers-reduced-motion: reduce) {{ .bar {{ animation: none; transform: none; }} .lbl, .val {{ animation: none; opacity: 1; }} .sheen, .ants {{ animation: none; }} .sheen {{ display: none; }} }}
</style>
<rect width="{width}" height="{height}" rx="18" fill="{t['bg']}"/>
<text class="h" x="48" y="64" font-size="30">Commits, by repo</text>
<text x="48" y="96" font-size="16" style="fill:{t['muted']}">All time, default branches · {d['repos']} repos · <tspan style="fill:{g1}">■</tspan> mine  <tspan style="fill:{other}">■</tspan> collaborators and upstream</text>
<rect class="ants" x="{width - 318}" y="34" width="270" height="78" rx="12"/>
<text class="h" x="{width - 183}" y="84" font-size="38" text-anchor="middle" style="fill:{g1}">{d['mine']:,}</text>
<text x="{width - 183}" y="104" font-size="13" text-anchor="middle" style="fill:{t['muted']}">commits of mine</text>
{''.join(out)}
<text x="48" y="{height - 22}" font-size="13" style="fill:{t['muted']}">From the GitHub API: commits on each repo's default branch, split by author. Forks and private mirrors left out. Rebuilt {d['built']}.</text>
</svg>
"""


def human(n):
    for unit, size in (("B", 1e9), ("M", 1e6), ("k", 1e3)):
        if n >= size:
            v = n / size
            return f"{v:.2f} {unit}" if v < 10 else f"{v:.1f} {unit}" if v < 100 else f"{v:.0f} {unit}"
    return str(n)


def day(iso):
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%b %-d")


def chart(d, theme):
    t = THEMES[theme]
    rows = d["rows"]
    width, top, rh = 1200, 150, 34
    height = top + rh * len(rows) + 56
    label_w, bar_x, bar_max = 250, 290, 760
    peak = max(r["total"] for r in rows)
    bars, defs = [], []
    for i, r in enumerate(rows):
        y = top + i * rh
        w = max(6, bar_max * r["total"] / peak)
        fill = {"public": f"url(#g-{theme})", "private": t["private"], "general": t["general"]}[r["kind"]]
        delay = 0.15 + i * 0.09
        defs.append(f'<clipPath id="c{i}-{theme}"><rect x="{bar_x}" y="{y}" width="{w:.1f}" height="22" rx="5"/></clipPath>')
        bars.append(
            f'<text class="lbl" x="{bar_x - 16}" y="{y + 16}" text-anchor="end" style="animation-delay:{delay:.2f}s">{art.esc(r["label"])}</text>'
            f'<rect class="bar" x="{bar_x}" y="{y}" width="{w:.1f}" height="22" rx="5" fill="{fill}" style="animation-delay:{delay:.2f}s"/>'
            f'<g clip-path="url(#c{i}-{theme})"><rect class="sheen" x="{bar_x - 120}" y="{y}" width="90" height="22" '
            f'fill="url(#s-{theme})" style="animation-delay:{1.4 + i * 0.12:.2f}s"/></g>'
            f'<text class="val" x="{bar_x + w + 10:.1f}" y="{y + 16}" style="animation-delay:{delay + 0.5:.2f}s">{human(r["total"])}</text>')
    w_ = d["window"]
    period = f"{day(w_['first'])} – {day(w_['last'])}, {w_['last'][:4]}"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Claude Code tokens by repo: {human(w_['total'])} tokens from {period}">
<defs>
  <linearGradient id="g-{theme}" x1="0" x2="1"><stop offset="0" stop-color="{t['accent']}"/><stop offset="1" stop-color="{t['accent2']}"/></linearGradient>
  <linearGradient id="s-{theme}" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".55"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
  {''.join(defs)}
</defs>
<style>
  text {{ font-family: {FONT}; fill: {t['ink']}; }}
  .h {{ font-weight: 700; letter-spacing: -0.02em; }}
  .lbl {{ font-size: 15px; fill: {t['muted']}; opacity: 0; animation: fade .6s ease both; }}
  .val {{ font-size: 15px; font-weight: 600; opacity: 0; animation: fade .6s ease both; }}
  .bar {{ transform-box: fill-box; transform-origin: left center; transform: scaleX(0); animation: grow 1.1s cubic-bezier(.2,.9,.3,1) both; }}
  .sheen {{ animation: sweep 3.6s ease-in-out infinite; }}
  @keyframes grow {{ to {{ transform: scaleX(1); }} }}
  @keyframes fade {{ to {{ opacity: 1; }} }}
  @keyframes sweep {{ 0% {{ transform: translateX(0); }} 60%, 100% {{ transform: translateX({bar_max + 240}px); }} }}
  .ants {{ fill: none; stroke: {t['accent']}; stroke-width: 2; stroke-dasharray: 8 6; animation: march 1.2s linear infinite; }}
  @keyframes march {{ to {{ stroke-dashoffset: -28; }} }}
  @media (prefers-reduced-motion: reduce) {{ .bar {{ animation: none; transform: none; }} .lbl, .val {{ animation: none; opacity: 1; }} .sheen, .ants {{ animation: none; }} .sheen {{ display: none; }} }}
</style>
<rect width="{width}" height="{height}" rx="18" fill="{t['bg']}"/>
<text class="h" x="48" y="64" font-size="30">Claude Code tokens, by repo</text>
<text x="48" y="96" font-size="16" style="fill:{t['muted']}">{period} · {human(w_['output'])} written by Claude · per-repo history starts when transcripts were kept</text>
<rect class="ants" x="{width - 318}" y="34" width="270" height="78" rx="12"/>
<text class="h" x="{width - 183}" y="84" font-size="38" text-anchor="middle" style="fill:{t['accent']}">{human(w_['total'])}</text>
<text x="{width - 183}" y="104" font-size="13" text-anchor="middle" style="fill:{t['muted']}">tokens in this window</text>
{''.join(bars)}
<text x="48" y="{height - 22}" font-size="13" style="fill:{t['muted']}">Counted from local Claude Code transcripts (input, output and cache) and attributed to a repo by working directory or the files each call touched. Rebuilt {d['built']}.</text>
</svg>
"""


MODEL_COLORS = ["#ff6a2b", "#ffb347", "#8957e5", "#2f81f7", "#3fb950", "#8b949e"]


def timeline(d, theme):
    """Tokens per day since the /stats cache starts, bars rising left to right, plus the model mix."""
    t = THEMES[theme]
    width, height = 1200, 360
    x0, x1, base, tall = 48, 1152, 300, 118
    start = datetime.strptime(d["since"], "%Y-%m-%d")
    end = datetime.strptime(d["last"], "%Y-%m-%d")
    n = (end - start).days + 1
    series = [d["daily"].get((start + timedelta(days=i)).strftime("%Y-%m-%d"), 0) for i in range(n)]
    peak = max(series) or 1
    step = (x1 - x0) / n
    bw = max(2.0, step - 2)
    bars, ticks = [], []
    for i, v in enumerate(series):
        h = max(1.5, tall * v / peak) if v else 0
        if h:
            bars.append(f'<rect class="day" x="{x0 + i * step:.1f}" y="{base - h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="1.5" '
                        f'fill="url(#tl-{theme})" style="animation-delay:{0.2 + i * 0.012:.2f}s"/>')
        dte = start + timedelta(days=i)
        if dte.day == 1 or i == 0:
            ticks.append(f'<text x="{x0 + i * step:.1f}" y="{base + 22}" font-size="13" style="fill:{t["muted"]}">{dte.strftime("%b %Y" if i == 0 or dte.month == 1 else "%b")}</text>')
    pi = series.index(peak)
    peak_day = (start + timedelta(days=pi)).strftime("%b %-d")
    px = x0 + pi * step + bw / 2
    # Model mix as one stacked bar.
    models = list(d["models"].items())
    top, rest = models[:5], sum(v for _, v in models[5:])
    if rest:
        top.append(("other", rest))
    total = sum(v for _, v in top)
    mix, legend, cx, lx = [], [], x0, x0
    for i, (name, v) in enumerate(top):
        w = (x1 - x0) * v / total
        col = MODEL_COLORS[i % len(MODEL_COLORS)]
        mix.append(f'<rect class="mix" x="{cx:.1f}" y="128" width="{max(w - 2, 1):.1f}" height="12" rx="3" fill="{col}" style="animation-delay:{0.1 + i * 0.12:.2f}s"/>')
        label = f"{name} {100 * v / total:.0f}%"
        legend.append(f'<rect x="{lx:.0f}" y="152" width="10" height="10" rx="2" fill="{col}"/><text x="{lx + 16:.0f}" y="161" font-size="13" style="fill:{t["muted"]}">{label}</text>')
        lx += 30 + 7.4 * len(label)
        cx += w
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Claude Code tokens per day since {day(d['since'])}: {human(d['total'])} in total">
<defs><linearGradient id="tl-{theme}" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="{t['accent']}"/><stop offset="1" stop-color="{t['accent2']}"/></linearGradient></defs>
<style>
  text {{ font-family: {FONT}; fill: {t['ink']}; }}
  .h {{ font-weight: 700; letter-spacing: -0.02em; }}
  .day {{ transform-box: fill-box; transform-origin: center bottom; transform: scaleY(0); animation: rise 0.9s cubic-bezier(.2,.9,.3,1) both; }}
  .mix {{ transform-box: fill-box; transform-origin: left center; transform: scaleX(0); animation: grow .8s cubic-bezier(.2,.9,.3,1) both; }}
  .pk {{ opacity: 0; animation: fade .6s ease 2.2s both; }}
  @keyframes rise {{ to {{ transform: scaleY(1); }} }}
  @keyframes grow {{ to {{ transform: scaleX(1); }} }}
  @keyframes fade {{ to {{ opacity: 1; }} }}
  .ants {{ fill: none; stroke: {t['accent']}; stroke-width: 2; stroke-dasharray: 8 6; animation: march 1.2s linear infinite; }}
  @keyframes march {{ to {{ stroke-dashoffset: -28; }} }}
  @media (prefers-reduced-motion: reduce) {{ .day, .mix {{ animation: none; transform: none; }} .pk {{ animation: none; opacity: 1; }} .ants {{ animation: none; }} }}
</style>
<rect width="{width}" height="{height}" rx="18" fill="{t['bg']}"/>
<text class="h" x="48" y="64" font-size="30">Claude Code, all time</text>
<text x="48" y="96" font-size="16" style="fill:{t['muted']}">Since {day(d['since'])}, {d['since'][:4]} · {d['sessions']:,} sessions · {d['messages']:,} messages · {human(d['output'])} written by Claude</text>
<rect class="ants" x="{width - 318}" y="34" width="270" height="78" rx="12"/>
<text class="h" x="{width - 183}" y="84" font-size="38" text-anchor="middle" style="fill:{t['accent']}">{human(d['total'])}</text>
<text x="{width - 183}" y="104" font-size="13" text-anchor="middle" style="fill:{t['muted']}">tokens through Claude</text>
{''.join(mix)}
{''.join(legend)}
<line x1="{x0}" y1="{base + 0.5}" x2="{x1}" y2="{base + 0.5}" stroke="{t['track']}" stroke-width="1"/>
{''.join(bars)}
{''.join(ticks)}
<g class="pk"><line x1="{px:.1f}" y1="{base - tall - 6}" x2="{px:.1f}" y2="{base - tall - 18}" stroke="{t['muted']}"/>
<text x="{min(px, x1 - 160):.1f}" y="{base - tall - 24}" font-size="13" style="fill:{t['muted']}">busiest day: {peak_day}, {human(peak)}</text></g>
<text x="48" y="{height - 16}" font-size="13" style="fill:{t['muted']}">From Claude Code's own usage stats (input, output and cache tokens). Older history wasn't recorded on this Mac. Rebuilt {d['built']}.</text>
</svg>
"""


WORM = [
    ".....................MMMMMMM......",
    "...................MMTTTTTTTMM....",
    "..................MTTDDDDDDDTTM...",
    ".................MTDDDDDDDDDDDTM..",
    ".................MTDDDDDDDDDDDTM..",
    ".................MTDDDDDDDDDDDTM..",
    "..................MTTDDDDDDDTTM...",
    "...................MMTTTTTTTMM....",
    "..................WWWMMMMMMMWW....",
    ".................WWWWWWWWWWWWW....",
    "................RRRRRRRRRRRRR.....",
    "...............WWWWWWWWWWWWW......",
    "..............WWWWWWWWWWWWW.......",
    ".............RRRRRRRRRRRRR........",
    "............WWWWWWWWWWWWW.........",
    "...........WWWWWWWWWWWWW..........",
    "..........RRRRRRRRRRRRR...........",
    ".........WWWWWWWWWWWWW............",
    "....ss..WWWWWWWWWWWWWss..s........",
    "..sssssssWWWWWWWWWWWsssssss.......",
    "ssssSSSSssssssssSSSSSSsssssssSSSss",
]


def dune(d, theme):
    t = THEMES[theme]
    i = 0 if theme == "dark" else 1
    spec = {
        "title": "dune", "accent": "worm",
        "colors": {"worm": ["#c9935a", "#a8742f"], "ring": ["#8a5a2b", "#6e4521"], "mouth": ["#e6b980", "#c58c45"],
                   "teeth": ["#f6efe0", "#fff7e8"], "throat": ["#2b1a0c", "#2b1a0c"],
                   "sand": [THEMES["dark"]["sand"], THEMES["light"]["sand"]], "sand2": [THEMES["dark"]["sand2"], THEMES["light"]["sand2"]]},
        "legend": {"W": ["worm", "worm"], "R": ["ring", "worm"], "M": ["mouth", "worm"], "T": ["teeth", "worm"],
                   "D": ["throat", "worm"], "s": ["sand", "sand"], "S": ["sand2", "sand"]},
        "motions": {"worm": "float"},
        "sprite": WORM,
    }
    px = 7
    ox, oy = 60, 28
    written = d["output"] / d["dune_tokens"]
    read = d["total"] / d["dune_tokens"]
    width, height = 1200, 220
    acc = t["accent"]
    glow, sparks = art.aura_svg(spec, theme, px, ox, oy, f"d{theme}")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Claude wrote about {written:.0f} copies of Dune for me and read about {read:,.0f}">
<style>
  :root {{ {art.color_vars(spec, theme)} }}
  text {{ font-family: {FONT}; fill: {t['ink']}; }}
  .h {{ font-weight: 800; letter-spacing: -0.03em; }}
  .px {{ shape-rendering: crispEdges; }}
  .rise {{ opacity: 0; animation: rise 12s ease infinite; }}
  @keyframes rise {{ 0%, 8% {{ opacity: 0; transform: translateY(10px); }} 16% {{ opacity: 1; transform: none; }} 92% {{ opacity: 1; }} 100% {{ opacity: 0; }} }}
  .d1 {{ animation-delay: .25s; }} .d2 {{ animation-delay: .5s; }}
  {art.aura_css()}
  {art.motion_css(spec, px, pop_loop=True)}
  @media (prefers-reduced-motion: reduce) {{ .rise {{ animation: none; opacity: 1; transform: none; }} }}
</style>
<rect width="{width}" height="{height}" rx="18" fill="{t['bg']}"/>
{glow}
{art.sprite_svg(spec, px, ox, oy)}
{sparks}
<text class="h rise" x="392" y="92" font-size="56">≈ {written:.0f} Dunes <tspan font-size="26" font-weight="600" style="fill:{t['muted']}">written by Claude</tspan></text>
<text class="rise d1" x="394" y="134" font-size="20" style="fill:{t['muted']}">{human(d['output'])} output tokens is about {written:.0f} copies of Frank Herbert's <tspan style="fill:{acc}">Dune</tspan>.</text>
<text class="rise d1" x="394" y="162" font-size="20" style="fill:{t['muted']}">Counting everything it read as well, {human(d['total'])} tokens, it is about <tspan font-weight="700" style="fill:{t['ink']}">{read:,.0f} Dunes</tspan>.</text>
<text class="rise d2" x="394" y="196" font-size="13" style="fill:{t['muted']}">Dune ≈ {DUNE_WORDS:,} words × {TOKENS_PER_WORD} tokens per word ≈ {DUNE_TOKENS:,.0f} tokens.</text>
</svg>
"""


def main():
    d = collect()
    c = collect_commits()
    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "commits.json").write_text(json.dumps(c, indent=2))
    (ASSETS / "tokens.json").write_text(json.dumps({k: v for k, v in d.items()}, indent=2))
    for theme in ("dark", "light"):
        (ASSETS / f"tokens-{theme}.svg").write_text(chart(d, theme))
        (ASSETS / f"dune-{theme}.svg").write_text(dune(d, theme))
        (ASSETS / f"commits-{theme}.svg").write_text(commits_chart(c, theme))
        (ASSETS / f"alltime-{theme}.svg").write_text(timeline(d, theme))
    print(f"{c['mine']:,} commits of mine (+{c['others']:,} by others) in {c['repos']} repos; "
          f"{human(d['total'])} tokens, {human(d['output'])} written, {len(d['rows'])} rows, "
          f"{d['output'] / d['dune_tokens']:.0f} Dunes written / {d['total'] / d['dune_tokens']:,.0f} read")


if __name__ == "__main__":
    main()
