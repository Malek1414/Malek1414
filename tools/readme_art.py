#!/usr/bin/env python3
"""Pixel-mascot README art for Malek's repos, generalised from nutcracker/scripts/build_art.py.

Every repo gets the same motion language as the Tryouts ant and the Nutcracker squirrel:
pixels pop in, the creature bobs, parts move on their own, a dashed frame marches around the
title, text rises. On top of that an aura: a soft glow in the accent colour breathes behind the
creature and a few pixel sparks twinkle around it.

    python3 readme_art.py spec.json --out <repo>/assets/readme

Writes logo.svg (animated, follows light/dark), banner-dark.svg, banner-light.svg,
divider-dark.svg, divider-light.svg and favicon.svg. Stdlib only.

spec.json
{
  "title": "Nutcracker",
  "tagline": "Shared tools, live events and one vault for every product.",
  "chips": ["MCP + HTTP", "event bus", "*rules + Claude", "one vault"],   # "*" marks the accent chip
  "footer_left": "Malek Hassan · Berlin · October 2026",
  "footer_right": "TypeScript · MCP",
  "alt": "Nutcracker: a pixel saber-toothed squirrel cracking an acorn",
  "accent": "fur",                                   # colour key for aura, frame and accent chip
  "colors": {"fur": ["#ff9a3c", "#d9600b"]},         # key: [dark theme, light theme]
  "legend": {"T": ["fur", "tail"], "E": ["eye", "head"]},   # sprite char: [colour key, group]
  "motions": {"tail": "sway", "head": "nod"},        # group: preset (see PRESETS)
  "origins": {"tail": "85% 95%"},                    # optional transform-origin per group
  "sprite": ["....TTTT....", "..."]                  # one char per pixel, "." is empty
}
"""
import argparse
import hashlib
import json
import random
from pathlib import Path

FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
BASE = {
    "dark": {"bg": "#0d1117", "ink": "#f0f3f6", "muted": "#9198a1", "track": "#1c2129", "spark": "#ffffff"},
    "light": {"bg": "#ffffff", "ink": "#1f2328", "muted": "#59636e", "track": "#f3f1ec", "spark": "#1f2328"},
}
# Motion presets a group can use. {px} is the pixel size, so motion scales with the sprite.
PRESETS = {
    "sway":    ("rotate", "3.2s ease-in-out infinite", "0%, 100% { transform: rotate(0deg); } 50% { transform: rotate(-6deg); }"),
    "rock":    ("rotate", "2.6s ease-in-out infinite", "0%, 100% { transform: rotate(-4deg); } 50% { transform: rotate(4deg); }"),
    "flap":    ("rotate", ".7s ease-in-out infinite", "0%, 100% { transform: rotate(0deg); } 50% { transform: rotate(-16deg); }"),
    "spin":    ("rotate", "4s linear infinite", "to { transform: rotate(360deg); }"),
    "nod":     ("move", "2.4s ease-in-out 1.4s infinite", "0%, 54%, 66%, 78%, 100% { transform: translateY(0); } 60%, 72% { transform: translateY({px}px); }"),
    "bounce":  ("move", ".9s cubic-bezier(.5,0,.5,1) infinite", "0%, 100% { transform: translateY(0); } 50% { transform: translateY({px3}px); }"),
    "pump":    ("move", ".9s cubic-bezier(.5,0,.5,1) infinite", "0%, 100% { transform: translateY({px}px); } 50% { transform: translateY(0); }"),
    "float":   ("move", "2.2s ease-in-out infinite", "0%, 100% { transform: translateY(0); } 50% { transform: translateY(-{px}px); }"),
    "shake":   ("move", "3s ease-in-out infinite", "0%, 80%, 100% { transform: translateX(0); } 84%, 92% { transform: translateX(-{half}px); } 88%, 96% { transform: translateX({half}px); }"),
    "slide":   ("move", "2.8s ease-in-out infinite", "0%, 100% { transform: translateX(0); } 50% { transform: translateX({px2}px); }"),
    "pulse":   ("scale", "1.8s ease-in-out infinite", "0%, 100% { transform: scale(1); } 50% { transform: scale(1.1); }"),
    "blink":   ("scale", "4.2s ease-in-out infinite", "0%, 92%, 100% { transform: scaleY(1); } 95% { transform: scaleY(.1); }"),
    "flicker": ("fade", "1.3s steps(2, end) infinite", "0%, 100% { opacity: 1; } 40% { opacity: .45; } 70% { opacity: .85; }"),
    "glow":    ("fade", "2.4s ease-in-out infinite", "0%, 100% { opacity: 1; } 50% { opacity: .55; }"),
    "none":    ("none", "", ""),
}


def load(path):
    spec = json.loads(Path(path).read_text())
    sprite = spec["sprite"]
    width = len(sprite[0])
    bad = [i for i, row in enumerate(sprite) if len(row) != width]
    assert not bad, f"sprite rows {bad} are not {width} wide"
    used = {ch for row in sprite for ch in row if ch != "."}
    missing = used - set(spec["legend"])
    assert not missing, f"sprite uses chars with no legend entry: {sorted(missing)}"
    for ch, (color, _group) in spec["legend"].items():
        assert color in spec["colors"], f"legend {ch!r} uses unknown colour {color!r}"
    assert spec["accent"] in spec["colors"], "accent must be a colour key"
    for g, m in spec.get("motions", {}).items():
        assert m in PRESETS, f"group {g!r}: unknown motion {m!r} (choose from {sorted(PRESETS)})"
    return spec


def runs(spec):
    """Horizontal runs of one char, so a row of eight fur pixels is one rect."""
    out = []
    for y, row in enumerate(spec["sprite"]):
        x = 0
        while x < len(row):
            ch = row[x]
            if ch == ".":
                x += 1
                continue
            start = x
            while x < len(row) and row[x] == ch:
                x += 1
            out.append((ch, start, y, x - start))
    return out


def groups_in_order(spec):
    order = []
    for row in spec["sprite"]:
        for ch in row:
            if ch != "." and spec["legend"][ch][1] not in order:
                order.append(spec["legend"][ch][1])
    return order


def sprite_svg(spec, px, ox, oy, animate=True):
    parts = {g: [] for g in groups_in_order(spec)}
    ov = 0.5 if px >= 4 else 0  # a hair of overlap hides seams between separately animated rects
    for ch, x, y, w in runs(spec):
        color, group = spec["legend"][ch]
        delay = f' style="animation-delay:{0.03 * x + 0.02 * y:.2f}s"' if animate else ""
        parts[group].append(f'<rect class="px c-{color}" x="{ox + x * px:g}" y="{oy + y * px:g}" '
                            f'width="{w * px + ov:g}" height="{px + ov:g}"{delay}/>')
    body = "".join(f'<g class="g-{g}">{"".join(r)}</g>' for g, r in parts.items())
    return f'<g class="bob">{body}</g>' if animate else body


def color_vars(spec, theme):
    i = 0 if theme == "dark" else 1
    return " ".join(f"--{k}: {v[i]};" for k, v in spec["colors"].items())


def fills(spec):
    return " ".join(f".c-{k} {{ fill: var(--{k}); }}" for k in spec["colors"])


def motion_css(spec, px, pop_loop):
    pop = ("animation: pop 12s cubic-bezier(.2,.9,.3,1.4) infinite;" if pop_loop
           else "animation: pop-in .5s cubic-bezier(.2,.9,.3,1.4) both;")
    css = [
        fills(spec),
        f".px {{ opacity: 0; transform-box: fill-box; transform-origin: center; {pop} }}",
        "@keyframes pop { 0% { opacity: 0; transform: scale(0); } 5% { opacity: 1; transform: scale(1); } 92% { opacity: 1; } 100% { opacity: 0; } }",
        "@keyframes pop-in { from { opacity: 0; transform: scale(0); } to { opacity: 1; transform: scale(1); } }",
        ".bob { animation: bob 1.6s ease-in-out infinite; }",
        f"@keyframes bob {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-{px * 0.4:g}px); }} }}",
    ]
    names = []
    subs = {"{px}": f"{px:g}", "{px2}": f"{px * 2:g}", "{px3}": f"{px * 3:g}", "{half}": f"{px * 0.5:g}"}
    for g, m in spec.get("motions", {}).items():
        if m == "none" or g not in groups_in_order(spec):
            continue
        _kind, timing, frames = PRESETS[m]
        for k, v in subs.items():
            frames = frames.replace(k, v)
        origin = spec.get("origins", {}).get(g, "50% 100%" if m in ("sway", "rock", "flap") else "center")
        css.append(f".g-{g} {{ transform-box: fill-box; transform-origin: {origin}; animation: m-{g} {timing}; }}")
        css.append(f"@keyframes m-{g} {{ {frames} }}")
        names.append(f".g-{g}")
    still = ", ".join([".bob", ".aura", ".spark"] + names)
    css.append(f"@media (prefers-reduced-motion: reduce) {{ .px {{ animation: none; opacity: 1; transform: none; }} {still} {{ animation: none; }} }}")
    return "\n  ".join(css)


def aura_css():
    return "\n  ".join([
        ".aura { transform-box: fill-box; transform-origin: center; animation: breathe 4.2s ease-in-out infinite; }",
        "@keyframes breathe { 0%, 100% { opacity: .55; transform: scale(.94); } 50% { opacity: 1; transform: scale(1.06); } }",
        ".spark { opacity: 0; transform-box: fill-box; transform-origin: center; animation: twinkle 3.6s ease-in-out infinite; }",
        "@keyframes twinkle { 0%, 100% { opacity: 0; transform: scale(.2) rotate(0deg); } 45% { opacity: 1; transform: scale(1) rotate(45deg); } 60% { opacity: .9; } }",
    ])


def aura_svg(spec, theme, px, ox, oy, uid):
    """Glow ellipse behind the sprite, plus pixel sparks that twinkle around it."""
    w, h = len(spec["sprite"][0]) * px, len(spec["sprite"]) * px
    cx, cy = ox + w / 2, oy + h / 2
    accent = spec["colors"][spec["accent"]][0 if theme == "dark" else 1]
    strength = ".55" if theme == "dark" else ".32"
    grad = (f'<defs><radialGradient id="aura-{uid}" cx="50%" cy="50%" r="50%">'
            f'<stop offset="0%" stop-color="{accent}" stop-opacity="{strength}"/>'
            f'<stop offset="55%" stop-color="{accent}" stop-opacity=".12"/>'
            f'<stop offset="100%" stop-color="{accent}" stop-opacity="0"/></radialGradient></defs>')
    glow = (f'<ellipse class="aura" cx="{cx:g}" cy="{cy:g}" rx="{w * 0.78:g}" ry="{h * 0.72:g}" '
            f'fill="url(#aura-{uid})"/>')
    rnd = random.Random(int(hashlib.sha1(spec["title"].encode()).hexdigest(), 16))
    sparks = []
    s = max(2.0, px * 0.75)
    for i in range(8):
        # Spread the sparks around the sprite's outline, never on top of it.
        side = i % 4
        t = rnd.random()
        x = {0: ox - px * 2.5, 1: ox + w + px * 1.5, 2: ox + t * w, 3: ox + t * w}[side]
        y = {0: oy + t * h, 1: oy + t * h, 2: oy - px * 2.5, 3: oy + h + px * 1.2}[side]
        x += rnd.uniform(-px, px)
        y += rnd.uniform(-px, px)
        fill = accent if i % 3 else BASE[theme]["spark"]
        sparks.append(f'<rect class="spark" x="{x:.1f}" y="{y:.1f}" width="{s:g}" height="{s:g}" fill="{fill}" '
                      f'style="animation-delay:{i * 0.45:.2f}s"/>')
    return grad + glow, "".join(sparks)


def text_width(text, size, bold=False):
    # Rough advance widths for the system UI font; good enough to fit the frame and chips.
    return sum((0.36 if c in "il.,:;|!' " else 0.66 if c.isupper() or c in "mwMW@" else 0.55) for c in text) * size * (1.04 if bold else 1)


def banner(spec, theme):
    t = BASE[theme]
    acc = spec["colors"][spec["accent"]][0 if theme == "dark" else 1]
    width, height = 1200, 340
    sw, sh = len(spec["sprite"][0]), len(spec["sprite"])
    px = max(3, min(8, 290 // sw, 220 // sh))
    ox = 50 + (310 - sw * px) / 2
    oy = 158 - sh * px / 2
    zone_x, zone_w = 392, 738
    title = spec["title"]
    fs = min(96, (zone_w - 44) / max(1, text_width(title, 1, bold=True)))
    frame_w = min(zone_w, text_width(title, fs, bold=True) + 44)
    base_y = 130 + fs * 0.35
    tag = spec["tagline"]
    tfs = min(24, (zone_w - 4) / max(1, text_width(tag, 1)))
    chips, cx = "", zone_x + 2
    labels = spec.get("chips", [])[:5]
    cfs = 16
    while labels and sum(22 + text_width(l.lstrip("*"), cfs) for l in labels) + 10 * (len(labels) - 1) > zone_w and cfs > 11:
        cfs -= 1
    for label in labels:
        hot = label.startswith("*")
        label = label.lstrip("*")
        cw = 22 + text_width(label, cfs)
        chips += (f'<rect x="{cx:.0f}" y="258" width="{cw:.0f}" height="34" rx="17" fill="{t["track"]}"/>'
                  f'<text x="{cx + cw / 2:.0f}" y="{275 + cfs * 0.38:.0f}" text-anchor="middle" font-size="{cfs}" '
                  f'style="fill:{acc if hot else t["ink"]}">{esc(label)}</text>')
        cx += cw + 10
    glow, sparks = aura_svg(spec, theme, px, ox, oy, f"b{theme}")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(spec['alt'])}">
<style>
  :root {{ {color_vars(spec, theme)} }}
  text {{ font-family: {FONT}; fill: {t['ink']}; }}
  .h {{ font-weight: 700; letter-spacing: -0.03em; }}
  .px {{ shape-rendering: crispEdges; }}
  .ants {{ fill: none; stroke: {acc}; stroke-width: 2.5; stroke-dasharray: 9 7; animation: march 1.2s linear infinite; }}
  @keyframes march {{ to {{ stroke-dashoffset: -32; }} }}
  .rise {{ opacity: 0; animation: rise 12s ease infinite; }}
  @keyframes rise {{ 0%, 8% {{ opacity: 0; transform: translateY(10px); }} 16% {{ opacity: 1; transform: none; }} 92% {{ opacity: 1; }} 100% {{ opacity: 0; }} }}
  .d1 {{ animation-delay: .25s; }} .d2 {{ animation-delay: .5s; }} .d3 {{ animation-delay: .75s; }}
  {aura_css()}
  {motion_css(spec, px, pop_loop=True)}
  @media (prefers-reduced-motion: reduce) {{ .rise {{ animation: none; opacity: 1; transform: none; }} .ants {{ animation: none; }} }}
</style>
<rect width="{width}" height="{height}" rx="18" fill="{t['bg']}"/>
{glow}
{sprite_svg(spec, px, ox, oy)}
{sparks}
<rect class="ants" x="{zone_x}" y="66" width="{frame_w:.0f}" height="128" rx="14"/>
<text class="h rise" x="{zone_x + 18}" y="{base_y:.0f}" font-size="{fs:.0f}">{esc(title)}</text>
<text class="rise d1" x="{zone_x + 2}" y="232" font-size="{tfs:.1f}" style="fill:{t['muted']}">{esc(tag)}</text>
<g class="rise d2">{chips}</g>
<text class="rise d3" x="70" y="318" font-size="15" style="fill:{t['muted']}">{esc(spec.get('footer_left', 'Malek Hassan · Berlin'))}</text>
<text class="rise d3" x="1130" y="318" text-anchor="end" font-size="15" style="fill:{t['muted']}">{esc(spec.get('footer_right', ''))}</text>
</svg>
"""


def logo(spec):
    sw, sh = len(spec["sprite"][0]), len(spec["sprite"])
    px, pad = 8, 32
    width, height = sw * px + 2 * pad, sh * px + 2 * pad
    glow_d, sparks_d = aura_svg(spec, "dark", px, pad, pad, "ld")
    glow_l, sparks_l = aura_svg(spec, "light", px, pad, pad, "ll")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" shape-rendering="crispEdges" role="img" aria-label="{esc(spec['alt'])}">
<style>
  :root {{ {color_vars(spec, "light")} }}
  .on-dark {{ display: none; }}
  @media (prefers-color-scheme: dark) {{ :root {{ {color_vars(spec, "dark")} }} .on-dark {{ display: inline; }} .on-light {{ display: none; }} }}
  {aura_css()}
  {motion_css(spec, px, pop_loop=False)}
</style>
<g class="on-light">{glow_l}</g><g class="on-dark">{glow_d}</g>
{sprite_svg(spec, px, pad, pad)}
<g class="on-light">{sparks_l}</g><g class="on-dark">{sparks_d}</g>
</svg>
"""


def favicon(spec):
    sw, sh = len(spec["sprite"][0]), len(spec["sprite"])
    side = max(sw, sh) + 2
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {side} {side}" shape-rendering="crispEdges">
<style>
  :root {{ {color_vars(spec, "light")} }}
  @media (prefers-color-scheme: dark) {{ :root {{ {color_vars(spec, "dark")} }} }}
  {fills(spec)}
</style>
{sprite_svg(spec, 1, (side - sw) / 2, (side - sh) / 2, animate=False)}
</svg>
"""


def divider(spec, theme):
    """A thin row of pixels in the accent colour with a light sweep running along it."""
    acc = spec["colors"][spec["accent"]][0 if theme == "dark" else 1]
    width, height, px = 1200, 20, 4
    cells = "".join(f'<rect x="{x}" y="8" width="{px}" height="{px}" style="animation-delay:{(x / width) * 2.4:.2f}s"/>'
                    for x in range(0, width, px * 3))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" shape-rendering="crispEdges" role="presentation">
<style>
  rect {{ fill: {acc}; opacity: .18; animation: sweep 2.4s ease-in-out infinite; }}
  @keyframes sweep {{ 0%, 100% {{ opacity: .18; }} 12% {{ opacity: 1; }} 30% {{ opacity: .18; }} }}
  @media (prefers-reduced-motion: reduce) {{ rect {{ animation: none; opacity: .5; }} }}
</style>
{cells}
</svg>
"""


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spec")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    spec = load(a.spec)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "logo.svg": logo(spec),
        "banner-dark.svg": banner(spec, "dark"),
        "banner-light.svg": banner(spec, "light"),
        "divider-dark.svg": divider(spec, "dark"),
        "divider-light.svg": divider(spec, "light"),
        "favicon.svg": favicon(spec),
    }
    for name, svg in files.items():
        (out / name).write_text(svg)
    print("wrote", ", ".join(str(out / n) for n in files))


if __name__ == "__main__":
    main()
