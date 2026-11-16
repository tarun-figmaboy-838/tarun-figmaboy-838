#!/usr/bin/env python3
"""Render an animated, magical-theme "player stats" card for the profile README.

Runs daily in GitHub Actions (see .github/workflows/profile-assets.yml) and
writes dist/stats.svg, which is published to the `output` branch.

Env:  GH_TOKEN  token for the GitHub GraphQL API (the Actions GITHUB_TOKEN works)
      GH_LOGIN  GitHub username (defaults to the repository owner)
Usage: python scripts/generate_stats.py [output-path]

Standard library only. It embeds assets/bg/sky-small.jpg (night-sky render) and the
"Player Stats" lettering from assets/bg/lettering.json, both made by the asset build.
"""
import base64
import datetime as dt
import html
import json
import math
import os
import random
import sys
import urllib.request
from pathlib import Path

LOGIN = os.environ.get("GH_LOGIN") or "tarun-figmaboy-838"
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/stats.svg")
BG = Path(__file__).resolve().parent.parent / "assets" / "bg"

QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false, first: 100) {
      totalCount
      nodes {
        name
        homepageUrl
        languages(first: 8, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

SERIF = ("'Cormorant Garamond','EB Garamond',Garamond,'Palatino Linotype',Palatino,"
         "'Book Antiqua',Georgia,serif")
NUMBER = "Georgia,'Palatino Linotype',Palatino,serif"


def fetch():
    if not TOKEN:
        sys.exit("GH_TOKEN is not set")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json",
                 "User-Agent": "profile-stats-card"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if payload.get("errors"):
        sys.exit(f"GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def streaks(days):
    counts = [d["contributionCount"] for d in days]
    longest = run = 0
    for c in counts:
        run = run + 1 if c else 0
        longest = max(longest, run)
    current, i = 0, len(counts) - 1
    if i >= 0 and counts[i] == 0:  # today may simply not have activity yet
        i -= 1
    while i >= 0 and counts[i]:
        current += 1
        i -= 1
    return current, longest


def odometer(value, x, y, delay, digit_w=26, line_h=46):
    """Rolling-digit number; the resting position is the real value, so it reads
    correctly even where animation is off."""
    clips, cols = [], []
    for i, ch in enumerate(str(value)):
        d = int(ch)
        cx = x + i * digit_w
        cid = f"n{x}_{i}"
        clips.append(f'<clipPath id="{cid}"><rect x="{cx}" y="{y - 38}" width="{digit_w}" height="{line_h}"/></clipPath>')
        digits = "".join(f'<text x="{cx + digit_w / 2:.1f}" y="{y + k * line_h}" text-anchor="middle" class="num">{k}</text>'
                         for k in range(10))
        dur = delay + 1.2 + i * .25
        cols.append(f'<g clip-path="url(#{cid})"><g transform="translate(0 {-d * line_h})">'
                    f'<animateTransform attributeName="transform" type="translate" values="0 0;0 0;0 {-d * line_h}" '
                    f'keyTimes="0;{delay / dur:.3f};1" dur="{dur:.2f}s" fill="freeze" calcMode="spline" '
                    f'keySplines="0 0 1 1;.2 .8 .2 1"/>{digits}</g></g>')
    return "".join(clips), "".join(cols)


def warp(n, vx, vy, reach, seed=7):
    """Stars flying out of a vanishing point toward the viewer."""
    rnd = random.Random(seed)
    css, els = [], []
    for i in range(n):
        a = rnd.uniform(0, 2 * math.pi)
        dist = reach * rnd.uniform(.65, 1)
        d = rnd.uniform(9, 15)
        css.append("@keyframes w%d{0%%{transform:translate(0,0) scale(.12);opacity:0}25%%{opacity:.7}"
                   "100%%{transform:translate(%.0fpx,%.0fpx) scale(2.3);opacity:0}}"
                   % (i, math.cos(a) * dist, math.sin(a) * dist))
        els.append(f'<circle cx="{vx + math.cos(a) * 20:.0f}" cy="{vy + math.sin(a) * 20:.0f}" '
                   f'r="{rnd.uniform(1, 2.2):.1f}" fill="url(#{"gd" if i % 4 == 0 else "sg"})" opacity=".3" '
                   f'style="transform-box:fill-box;transform-origin:center;animation:w{i} {d:.1f}s '
                   f'cubic-bezier(.55,0,.95,.55) {-rnd.uniform(0, d):.1f}s infinite"/>')
    return "".join(css), "".join(els)


def render(user):
    repos = user["repositories"]
    cal = user["contributionsCollection"]["contributionCalendar"]
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]
    current, longest = streaks(days)
    # the profile repo (named after the user) links to the portfolio, not a demo
    live = sum(1 for n in repos["nodes"]
               if (n.get("homepageUrl") or "").strip() and n["name"].lower() != LOGIN.lower())

    langs = {}
    for n in repos["nodes"]:
        for e in n["languages"]["edges"]:
            name = e["node"]["name"]
            size, color = langs.get(name, (0, e["node"]["color"] or "#8B8B8B"))
            langs[name] = (size + e["size"], color)
    total = sum(s for s, _ in langs.values()) or 1
    top = [kv for kv in sorted(langs.items(), key=lambda kv: -kv[1][0]) if kv[1][0] / total >= .01][:5]

    W, H = 1200, 408
    defs, parts = [], []

    # night-sky backdrop and lettering produced by the asset build (optional)
    sky = BG / "sky-small.jpg"
    if sky.exists():
        data = base64.b64encode(sky.read_bytes()).decode()
        defs.append(f'<image id="sky" width="{W}" height="{H}" preserveAspectRatio="xMaxYMid slice" '
                    f'href="data:image/jpeg;base64,{data}"/>')
        parts.append('<g class="drift"><use href="#sky" opacity=".5"/></g>')
    parts.append(f'<rect width="{W}" height="{H}" fill="url(#dim)"/>')
    star_css, stars = warp(20, W / 2, H / 2, 760)
    parts.append(stars)
    lettering = BG / "lettering.json"
    if lettering.exists():
        t = json.loads(lettering.read_text())["player_stats"]
        k = 26 / t["size"]
        parts.append(f'<path transform="translate(40 60) scale({k:.4f})" fill="url(#foil)" d="{t["d"]}"/>')
    else:
        parts.append('<text x="40" y="60" class="hud">PLAYER STATS</text>')
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    parts.append(f'<text x="{W - 40}" y="56" text-anchor="end" class="upd">AUTO-UPDATED DAILY · {today}</text>')

    tiles = [
        (cal["totalContributions"], "CONTRIBUTIONS", "in the last year"),
        (repos["totalCount"], "PUBLIC REPOS", "games & experiments"),
        (live, "LIVE DEMOS", "playable in the browser"),
        (longest, "LONGEST STREAK", f"days · current {current}"),
    ]
    tw, tg, ty = 265, 20, 84
    for i, (value, label, sub) in enumerate(tiles):
        x = 40 + i * (tw + tg)
        c, num = odometer(value, x + 24, ty + 56, .25 + i * .15)
        defs.append(c)
        parts.append(f'<g class="pop" style="animation-delay:{.1 + i * .12:.2f}s">'
                     f'<rect x="{x}" y="{ty}" width="{tw}" height="106" rx="18" fill="url(#glass)" '
                     f'stroke="#F2C66D" stroke-opacity=".3"/>{num}'
                     f'<text x="{x + 24}" y="{ty + 80}" class="lab">{label}</text>'
                     f'<text x="{x + 24}" y="{ty + 97}" class="sub">{html.escape(sub)}</text></g>')

    # languages
    lx, ly, lw = 40, 246, 520
    parts.append(f'<text x="{lx}" y="{ly - 16}" class="hud">TOP LANGUAGES</text>'
                 f'<rect x="{lx}" y="{ly}" width="{lw}" height="14" rx="7" fill="#fff" fill-opacity=".07" '
                 f'stroke="#F2C66D" stroke-opacity=".25"/>')
    defs.append(f'<clipPath id="lbar"><rect x="{lx}" y="{ly}" width="{lw}" height="14" rx="7"/></clipPath>')
    seg, cx = [], lx
    for i, (name, (size, color)) in enumerate(top):
        w = lw * size / total
        seg.append(f'<rect class="grow" style="animation-delay:{.4 + i * .15:.2f}s" x="{cx:.1f}" y="{ly}" '
                   f'width="{w:.1f}" height="14" fill="{color}"/>')
        cx += w
    parts.append(f'<g clip-path="url(#lbar)">{"".join(seg)}</g>')
    for i, (name, (size, color)) in enumerate(top):
        x, y = lx + (i % 3) * 178, ly + 46 + (i // 3) * 30
        parts.append(f'<circle cx="{x + 6}" cy="{y - 5}" r="6" fill="{color}"/>'
                     f'<text x="{x + 20}" y="{y}" class="leg">{html.escape(name)} '
                     f'<tspan class="pct">{100 * size / total:.1f}%</tspan></text>')

    # the last 26 weeks as a star map: brighter, bigger stars on busier days
    weeks = cal["weeks"][-26:]
    hx, hy, cell = 650, 246, 20
    parts.append(f'<text x="{hx - 6}" y="{hy - 16}" class="hud">LAST 26 WEEKS</text>')
    peak = max([d["contributionCount"] for w in weeks for d in w["contributionDays"]] + [1])
    rnd = random.Random(1)
    for wi, w in enumerate(weeks):
        for d in w["contributionDays"]:
            wd = dt.date.fromisoformat(d["date"]).isoweekday() % 7  # Sunday = 0
            c = d["contributionCount"]
            lvl = 0 if c == 0 else min(4, 1 + int(3 * c / peak))
            x, y = hx + wi * cell, hy + 8 + wd * cell
            tip = f'<title>{d["date"]}: {c} contributions</title>'
            if lvl == 0:
                parts.append(f'<circle cx="{x}" cy="{y}" r="1.1" fill="#fff" fill-opacity=".16">{tip}</circle>')
                continue
            r = [0, 4.4, 6, 7.4, 9][lvl]
            fill = "url(#sv)" if lvl <= 2 else "url(#gd)"
            twinkle = (f"animation:cell .6s cubic-bezier(.2,.8,.2,1) {.3 + wi * .035:.3f}s backwards"
                       + (f",tw {rnd.uniform(2.4, 4):.1f}s ease-in-out {rnd.uniform(0, 3):.1f}s infinite" if lvl >= 3 else ""))
            parts.append(f'<circle class="st" cx="{x}" cy="{y}" r="{r}" fill="{fill}" style="{twinkle}">{tip}</circle>')

    css = f"""
.lab,.sub,.leg,.hud,.upd,.pct{{font-family:{SERIF}}}.num{{font-family:{NUMBER}}}
.hud{{font-size:12.5px;font-weight:700;letter-spacing:3px;fill:#C9B98F}}
.upd{{font-size:11.5px;font-weight:700;letter-spacing:2px;fill:#9790B5}}
.num{{font-size:40px;font-weight:700;fill:url(#foil)}}
.lab{{font-size:12px;font-weight:700;letter-spacing:2.2px;fill:#F6F0E1}}
.sub{{font-size:13.5px;font-style:italic;fill:#CBC4DE}}
.leg{{font-size:15px;font-weight:600;fill:#EDE6D4}}.pct{{font-size:13px;fill:#CBC4DE}}
.pop{{animation:pop .8s cubic-bezier(.2,.8,.2,1) backwards}}
@keyframes pop{{from{{opacity:0;transform:translateY(16px)}}}}
.grow{{transform-box:fill-box;transform-origin:left center;animation:grow 1.4s cubic-bezier(.2,.8,.2,1) backwards}}
@keyframes grow{{from{{transform:scaleX(0)}}}}
.st{{transform-box:fill-box;transform-origin:center}}
@keyframes cell{{from{{opacity:0;transform:scale(.2)}}}}
@keyframes tw{{0%,100%{{opacity:1}}50%{{opacity:.45}}}}
.drift{{animation:drift 46s ease-in-out infinite alternate}}
@keyframes drift{{from{{transform:translate(0,0) scale(1.08)}}to{{transform:translate(-36px,-10px) scale(1.16)}}}}
.beam{{animation:beam 9s linear infinite}}@keyframes beam{{to{{stroke-dashoffset:-1000}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
""" + star_css
    defs.append(
        '<radialGradient id="sg"><stop offset="0" stop-color="#fff"/><stop offset=".3" stop-color="#fff" stop-opacity=".8"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
        '<radialGradient id="gd"><stop offset="0" stop-color="#FFF6D6"/><stop offset=".35" stop-color="#F2C66D" stop-opacity=".9"/>'
        '<stop offset="1" stop-color="#F2C66D" stop-opacity="0"/></radialGradient>'
        '<radialGradient id="sv"><stop offset="0" stop-color="#F1EBFF"/><stop offset=".35" stop-color="#A78BFA" stop-opacity=".85"/>'
        '<stop offset="1" stop-color="#A78BFA" stop-opacity="0"/></radialGradient>'
        '<linearGradient id="dim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#060423" stop-opacity=".45"/>'
        '<stop offset="1" stop-color="#060423" stop-opacity=".8"/></linearGradient>'
        '<linearGradient id="glass" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".09"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity=".025"/></linearGradient>'
        '<linearGradient id="foil" x1="0" y1="0" x2="1" y2=".55" spreadMethod="reflect">'
        '<stop offset="0" stop-color="#9C6E25"/><stop offset=".22" stop-color="#E8BE62"/><stop offset=".42" stop-color="#FFF2C6"/>'
        '<stop offset=".58" stop-color="#E9BD5C"/><stop offset=".8" stop-color="#A4742A"/><stop offset="1" stop-color="#F0C46A"/>'
        '<animateTransform attributeName="gradientTransform" type="translate" from="-1 -.55" to="1 .55" dur="6s" '
        'repeatCount="indefinite"/></linearGradient>'
        '<linearGradient id="beamg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFF2C6"/>'
        '<stop offset=".5" stop-color="#F2C66D"/><stop offset="1" stop-color="#A78BFA"/></linearGradient>'
        f'<clipPath id="outer"><rect width="{W}" height="{H}" rx="28"/></clipPath>'
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t d">
<title id="t">GitHub stats for {LOGIN}</title>
<desc id="d">{cal['totalContributions']} contributions in the last year, {repos['totalCount']} public repos, {live} live demos, longest streak {longest} days, current streak {current} days.</desc>
<defs>{''.join(defs)}</defs>
<style>{css}</style>
<g clip-path="url(#outer)">
<rect width="{W}" height="{H}" fill="#060423"/>
{''.join(parts)}
</g>
<rect x=".75" y=".75" width="{W - 1.5}" height="{H - 1.5}" rx="27.25" fill="none" stroke="#F2C66D" stroke-opacity=".3"/>
<rect class="beam" x="1" y="1" width="{W - 2}" height="{H - 2}" rx="27.25" fill="none" stroke="url(#beamg)" stroke-width="2" pathLength="1000" stroke-dasharray="140 860" stroke-linecap="round"/>
</svg>
"""


def main():
    svg = render(fetch())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(svg, encoding="utf-8")
    print(f"wrote {OUT} ({len(svg) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
