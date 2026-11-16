#!/usr/bin/env python3
"""Render an animated "player stats" card for the profile README.

Runs daily in GitHub Actions (see .github/workflows/profile-assets.yml) and
writes dist/stats.svg, which is published to the `output` branch.

Env:  GH_TOKEN  token for the GitHub GraphQL API (the Actions GITHUB_TOKEN works)
      GH_LOGIN  GitHub username (defaults to the repository owner)
Usage: python scripts/generate_stats.py [output-path]
Standard library only, so nothing needs installing.
"""
import datetime as dt
import html
import json
import os
import sys
import urllib.request
from pathlib import Path

LOGIN = os.environ.get("GH_LOGIN") or "tarun-figmaboy-838"
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/stats.svg")

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

SANS = "Inter,'Segoe UI',-apple-system,BlinkMacSystemFont,'Helvetica Neue',Arial,sans-serif"
MONO = "'JetBrains Mono','SF Mono',SFMono-Regular,ui-monospace,Menlo,Consolas,'Liberation Mono',monospace"
LEVELS = ["#1C1932", "#3B2A7A", "#5B3FD0", "#8B5CF6", "#FF4FD8"]


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
    current = 0
    i = len(counts) - 1
    if i >= 0 and counts[i] == 0:  # today may simply not have activity yet
        i -= 1
    while i >= 0 and counts[i]:
        current += 1
        i -= 1
    return current, longest


def odometer(value, x, y, delay, digit_w=27, line_h=46):
    """Rolling-digit number: each digit column scrolls up to its value."""
    out = []
    digits = str(value)
    for i, ch in enumerate(digits):
        d = int(ch)
        cx = x + i * digit_w
        col = "".join(
            f'<text x="{cx + digit_w / 2:.1f}" y="{y + k * line_h}" text-anchor="middle" class="num">{k}</text>'
            for k in range(10)
        )
        # The resting transform is the final digit, so renderers without SMIL still show
        # the right number; the animation rolls from 0 after a short delay.
        dur = delay + 1.2 + i * .25
        out.append(
            f'<g clip-path="url(#numclip{i}_{x})"><g transform="translate(0 {-d * line_h})">'
            f'<animateTransform attributeName="transform" type="translate" '
            f'values="0 0;0 0;0 {-d * line_h}" keyTimes="0;{delay / dur:.3f};1" dur="{dur:.2f}s" '
            f'fill="freeze" calcMode="spline" keySplines="0 0 1 1;.2 .8 .2 1"/>{col}</g></g>'
        )
    clips = "".join(
        f'<clipPath id="numclip{i}_{x}"><rect x="{x + i * digit_w}" y="{y - 38}" width="{digit_w}" '
        f'height="{line_h}"/></clipPath>'
        for i in range(len(digits))
    )
    return clips, "".join(out)


def render(user):
    repos = user["repositories"]
    cal = user["contributionsCollection"]["contributionCalendar"]
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]
    current, longest = streaks(days)
    # The profile repo (named after the user) links to the portfolio, not a demo.
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

    tiles = [
        (cal["totalContributions"], "CONTRIBUTIONS", "in the last year"),
        (repos["totalCount"], "PUBLIC REPOS", "games & experiments"),
        (live, "LIVE DEMOS", "playable in the browser"),
        (longest, "LONGEST STREAK", f"days · current {current}"),
    ]

    W, H = 1200, 404
    clips, parts = [], []
    tw, tg, tx0, ty0 = 265, 20, 40, 72
    for i, (value, label, sub) in enumerate(tiles):
        x = tx0 + i * (tw + tg)
        c, num = odometer(value, x + 24, ty0 + 58, .25 + i * .15)
        clips.append(c)
        parts.append(
            f'<g class="pop" style="animation-delay:{.1 + i * .12:.2f}s">'
            f'<rect x="{x}" y="{ty0}" width="{tw}" height="104" rx="18" fill="#15122A" stroke="#fff" stroke-opacity=".08"/>'
            f'{num}'
            f'<text x="{x + 24}" y="{ty0 + 80}" class="lab">{label}</text>'
            f'<text x="{x + 24}" y="{ty0 + 96}" class="sub">{html.escape(sub)}</text></g>'
        )

    # languages
    lx, ly, lw = 40, 236, 520
    parts.append(f'<text x="{lx}" y="{ly - 14}" class="hud">TOP LANGUAGES</text>')
    parts.append(f'<rect x="{lx}" y="{ly}" width="{lw}" height="14" rx="7" fill="#1C1932"/>')
    clips.append(f'<clipPath id="lbar"><rect x="{lx}" y="{ly}" width="{lw}" height="14" rx="7"/></clipPath>')
    seg, cx = [], lx
    for i, (name, (size, color)) in enumerate(top):
        w = lw * size / total
        seg.append(f'<rect class="grow" style="animation-delay:{.4 + i * .15:.2f}s" x="{cx:.1f}" y="{ly}" '
                   f'width="{w:.1f}" height="14" fill="{color}"/>')
        cx += w
    parts.append(f'<g clip-path="url(#lbar)">{"".join(seg)}</g>')
    for i, (name, (size, color)) in enumerate(top):
        col, row = i % 3, i // 3
        x, y = lx + col * 178, ly + 44 + row * 30
        parts.append(f'<circle cx="{x + 6}" cy="{y - 5}" r="6" fill="{color}"/>'
                     f'<text x="{x + 20}" y="{y}" class="leg">{html.escape(name)} '
                     f'<tspan class="pct">{100 * size / total:.1f}%</tspan></text>')

    # last 26 weeks heat strip
    weeks = cal["weeks"][-26:]
    hx, hy, cell, gap = 640, 236, 16, 4
    parts.append(f'<text x="{hx}" y="{hy - 14}" class="hud">LAST 26 WEEKS</text>')
    peak = max([d["contributionCount"] for w in weeks for d in w["contributionDays"]] + [1])
    for wi, w in enumerate(weeks):
        for d in w["contributionDays"]:
            wd = dt.date.fromisoformat(d["date"]).isoweekday() % 7  # Sunday = 0
            c = d["contributionCount"]
            lvl = 0 if c == 0 else min(4, 1 + int(3 * c / peak))
            parts.append(
                f'<rect class="cell" style="animation-delay:{.3 + wi * .035:.3f}s" x="{hx + wi * (cell + gap)}" '
                f'y="{hy + wd * (cell + gap)}" width="{cell}" height="{cell}" rx="4" fill="{LEVELS[lvl]}">'
                f'<title>{d["date"]}: {c} contributions</title></rect>'
            )

    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    css = f"""
.sans,.lab,.sub,.leg{{font-family:{SANS}}}.hud,.upd,.num,.pct{{font-family:{MONO}}}
.hud{{font-size:13px;font-weight:700;letter-spacing:3px;fill:#A7A3C7}}
.upd{{font-size:12px;fill:#6F6B92}}
.num{{font-size:40px;font-weight:800;fill:url(#ng)}}
.lab{{font-size:12px;font-weight:800;letter-spacing:2px;fill:#F4F2FF}}
.sub{{font-size:12.5px;fill:#A7A3C7}}
.leg{{font-size:14px;font-weight:600;fill:#E6E3FA}}.pct{{font-size:12.5px;fill:#A7A3C7}}
.pop{{animation:pop .8s cubic-bezier(.2,.8,.2,1) backwards}}
@keyframes pop{{from{{opacity:0;transform:translateY(16px)}}}}
.grow{{transform-box:fill-box;transform-origin:left center;animation:grow 1.4s cubic-bezier(.2,.8,.2,1) backwards}}
@keyframes grow{{from{{transform:scaleX(0)}}}}
.cell{{transform-box:fill-box;transform-origin:center;animation:cell .6s cubic-bezier(.2,.8,.2,1) backwards}}
@keyframes cell{{from{{opacity:0;transform:scale(.3)}}}}
.beam{{animation:beam 9s linear infinite}}@keyframes beam{{to{{stroke-dashoffset:-1000}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
"""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t d">
<title id="t">GitHub stats for {LOGIN}</title>
<desc id="d">{cal['totalContributions']} contributions in the last year, {repos['totalCount']} public repos, {live} live demos, longest streak {longest} days, current streak {current} days.</desc>
<defs>
<clipPath id="outer"><rect width="{W}" height="{H}" rx="28"/></clipPath>
<linearGradient id="ng" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#C4B5FF"/><stop offset=".5" stop-color="#FF4FD8"/><stop offset="1" stop-color="#3DE0FF"/></linearGradient>
<linearGradient id="beamg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FF4FD8"/><stop offset=".5" stop-color="#7C5CFF"/><stop offset="1" stop-color="#3DE0FF"/></linearGradient>
<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1.5" cy="1.5" r="1.1" fill="#fff" fill-opacity=".07"/></pattern>
{''.join(clips)}
</defs>
<style>{css}</style>
<g clip-path="url(#outer)">
<rect width="{W}" height="{H}" fill="#0E0C1A"/><rect width="{W}" height="{H}" fill="url(#dots)"/>
<text x="40" y="47" class="hud">PLAYER STATS</text>
<text x="{W - 40}" y="47" text-anchor="end" class="upd">auto-updated daily · {today}</text>
{''.join(parts)}
</g>
<rect x=".75" y=".75" width="{W - 1.5}" height="{H - 1.5}" rx="27.25" fill="none" stroke="#fff" stroke-opacity=".09"/>
<rect class="beam" x="1" y="1" width="{W - 2}" height="{H - 2}" rx="27.25" fill="none" stroke="url(#beamg)" stroke-width="2" pathLength="1000" stroke-dasharray="150 850" stroke-linecap="round"/>
</svg>
"""


def main():
    svg = render(fetch())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(svg, encoding="utf-8")
    print(f"wrote {OUT} ({len(svg) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
