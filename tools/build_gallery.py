#!/usr/bin/env python3
"""Copy each featured repo's pixel logo into assets/logos/ and rewrite the gallery in README.md.

The logos come from local clones that already have assets/readme/{art.json,logo.svg}
(made with tools/readme_art.py). Only public repos are featured.

    python3 tools/build_gallery.py [--src ~/Desktop/Projects/readme-upgrade]
"""
import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FEATURED = [
    "nightcrawler", "social-chrome", "MOZCODE", "keychat", "code-hackathon-project", "f1-predictions",
    "Offerprofi", "starry", "slack-mcp-code", "SCIO", "taxfix-cursor-hackathon", "ORACLE",
    "prince-of-bel-hair", "finance-wizz", "vidbridge-public-video-demo", "stowage-dist", "Malek1414.github.io",
]
COLS = 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=Path.home() / "Desktop/Projects/readme-upgrade")
    a = ap.parse_args()
    out = ROOT / "assets" / "logos"
    out.mkdir(parents=True, exist_ok=True)
    cells = []
    for repo in FEATURED:
        art = a.src / repo / "assets" / "readme"
        spec = json.loads((art / "art.json").read_text())
        shutil.copyfile(art / "logo.svg", out / f"{repo}.svg")
        cells.append(
            f'<td align="center" valign="top" width="33%">'
            f'<a href="https://github.com/Malek1414/{repo}"><img src="assets/logos/{repo}.svg" height="96" alt="{spec["alt"]}"><br>'
            f'<b>{spec["title"]}</b></a><br><sub>{spec["tagline"]}</sub></td>')
    rows = ["<tr>" + "".join(cells[i:i + COLS]) + "</tr>" for i in range(0, len(cells), COLS)]
    table = "<table>\n" + "\n".join(rows) + "\n</table>"
    readme = ROOT / "README.md"
    text = readme.read_text()
    start, end = "<!-- gallery:start -->", "<!-- gallery:end -->"
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    readme.write_text(f"{head}{start}\n{table}\n{end}{tail}")
    print(f"{len(cells)} repos in the gallery")


if __name__ == "__main__":
    main()
