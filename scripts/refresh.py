#!/usr/bin/env python3
"""Patch banner/chart/stats SVGs and regenerate langs.svg with latest GitHub data."""
import datetime
import json
import os
import pathlib
import re
import sys
import urllib.request

USER = "davidyang02"
ROOT = pathlib.Path(__file__).resolve().parent.parent

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount date } }
      }
    }
    pullRequests { totalCount }
    issues { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges {
            size
            node { name color }
          }
        }
      }
    }
  }
}
"""


def fetch():
    token = os.environ["GH_TOKEN"]
    body = json.dumps({"query": QUERY, "variables": {"login": USER}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"{USER}-profile-refresh",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.loads(r.read())
    if "errors" in payload:
        raise SystemExit(f"GraphQL errors: {payload['errors']}")
    return payload


def stats(data):
    u = data["data"]["user"]
    cal = u["contributionsCollection"]["contributionCalendar"]
    counts = [d["contributionCount"] for w in cal["weeks"] for d in w["contributionDays"]]
    high = max(counts) if counts else 0
    avg = round(sum(counts) / max(len(counts), 1), 1)
    active = sum(1 for c in counts if c > 0)
    streak = 0
    for c in reversed(counts):
        if c > 0:
            streak += 1
        else:
            break
    longest = run = 0
    for c in counts:
        if c > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0

    repos = u["repositories"]["nodes"]
    stars = sum(r["stargazerCount"] for r in repos)

    lang_bytes = {}
    lang_color = {}
    for r in repos:
        for e in r["languages"]["edges"]:
            n = e["node"]["name"]
            lang_bytes[n] = lang_bytes.get(n, 0) + e["size"]
            lang_color[n] = e["node"]["color"] or "#888888"

    return {
        "total": cal["totalContributions"],
        "high": high,
        "avg": avg,
        "active": active,
        "streak": streak,
        "longest": longest,
        "prs": u["pullRequests"]["totalCount"],
        "issues": u["issues"]["totalCount"],
        "repos": u["repositories"]["totalCount"],
        "follow": u["followers"]["totalCount"],
        "stars": stars,
        "commits_year": u["contributionsCollection"]["totalCommitContributions"],
        "languages": lang_bytes,
        "lang_colors": lang_color,
        "ts": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d  %H:%M:%S UTC"),
        "date": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d"),
    }


def replace_after_label(svg, label, new_value):
    """Replace the value of the <text> immediately following a labeled <text>."""
    pattern = (
        rf'(>{re.escape(label)}</text>\s*<text[^>]*?font-weight="700">)'
        r'[^<]+'
        r'(</text>)'
    )
    new_svg, n = re.subn(pattern, rf'\g<1>{new_value}\g<2>', svg, count=1)
    if n == 0:
        print(f"WARN: label {label!r} not matched", file=sys.stderr)
    return new_svg


def update_banner(s, st):
    s = re.sub(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+\w+', st["ts"], s, count=1)
    s = replace_after_label(s, "LAST", str(st["total"]))
    s = replace_after_label(s, "HIGH", f"{st['high']}/D")
    s = replace_after_label(s, "AVG", f"{st['avg']}/D")
    s = replace_after_label(s, "STREAK", f"{st['streak']}D")
    s = replace_after_label(s, "DAYS", f"{st['active']} / 365")
    return s


def update_chart(s, st):
    s = re.sub(
        r'(<circle cx="1180" cy="80"[^/]*/?>(?:\s*<animate[^/]*/>\s*)*\s*</circle>\s*<text[^>]*font-weight="700">)\d+(</text>)',
        rf'\g<1>{st["total"]}\g<2>', s, count=1,
    )
    # Fallback if circle is self-closed (no inner animations), or older shape
    s = re.sub(
        r'(<circle cx="1180" cy="80"[^/]*/>\s*<text[^>]*font-weight="700">)\d+(</text>)',
        rf'\g<1>{st["total"]}\g<2>', s, count=1,
    )
    s = replace_after_label(s, "LAST  1Y", str(st["total"]))
    s = replace_after_label(s, "HIGH", f"{st['high']} / D")
    s = replace_after_label(s, "AVG", f"{st['avg']} / D")
    s = replace_after_label(s, "STREAK", f"{st['streak']} D")
    s = replace_after_label(s, "LONGEST", f"{st['longest']} D")
    s = replace_after_label(s, "PRs", str(st["prs"]))
    s = replace_after_label(s, "REPOS", str(st["repos"]))
    s = replace_after_label(s, "DAYS ACTIVE", f"{st['active']} / 365")
    s = replace_after_label(s, "FOLLOW", str(st["follow"]))

    width = round(st["active"] / 365 * 900)
    pct = round(st["active"] / 365 * 100)
    s = re.sub(
        r'(<rect x="70" y="332" width=")\d+(" height="14" fill="#FF7700"[^/]*/?>(?:\s*<animate[^/]*/>\s*)*\s*</rect>)',
        rf'\g<1>{width}\g<2>', s, count=1,
    )
    s = re.sub(
        r'(<rect x="70" y="332" width=")\d+(" height="14" fill="#FF7700"[^/]*/>)',
        rf'\g<1>{width}\g<2>', s, count=1,
    )
    s = re.sub(
        r'(<text x="990" y="342"[^>]*font-weight="700">)\d+%(</text>)',
        rf'\g<1>{pct}%\g<2>', s, count=1,
    )
    return s


def update_stats(s, st):
    s = re.sub(r'\d{4}-\d{2}-\d{2}(?=</text>\s*</svg>)', st["date"], s, count=1)
    s = replace_after_label(s, "CONTRIB", str(st["total"]))
    s = replace_after_label(s, "STARS", str(st["stars"]))
    s = replace_after_label(s, "FOLLOWERS", str(st["follow"]))
    s = replace_after_label(s, "COMMITS", str(st["commits_year"]))
    s = replace_after_label(s, "PRs", str(st["prs"]))
    s = replace_after_label(s, "REPOS", str(st["repos"]))
    return s


def render_langs(st, top_n=6):
    langs = sorted(st["languages"].items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    total = sum(b for _, b in langs) or 1
    rows = []
    bar_x = 130
    bar_w_max = 290
    for i, (name, size) in enumerate(langs):
        y = 44 + i * 22
        pct = size / total * 100
        bar_w = round(size / total * bar_w_max, 1)
        color = st["lang_colors"].get(name, "#888888")
        # Truncate long names to 14 chars
        display_name = name if len(name) <= 14 else name[:13] + "…"
        rows.append(f"""
  <text x="14" y="{y + 9}" fill="#FFFFFF" font-size="11">{display_name}</text>
  <rect x="{bar_x}" y="{y}" width="{bar_w_max}" height="12" fill="#1A1A1A"/>
  <rect x="{bar_x}" y="{y}" width="{bar_w}" height="12" fill="{color}"/>
  <text x="466" y="{y + 9}" fill="#FFFFFF" font-size="11" text-anchor="end">{pct:.1f}%</text>""")

    body = "".join(rows) if rows else """
  <text x="240" y="100" fill="#888888" font-size="11" text-anchor="middle">no public language data</text>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 180" preserveAspectRatio="xMidYMid meet" font-family="ui-monospace, Consolas, 'Courier New', monospace">
  <rect width="480" height="180" fill="#000000"/>
  <rect x="0" y="0" width="480" height="22" fill="#FF7700"/>
  <text x="8" y="15" fill="#000000" font-size="11" font-weight="700">CRNCY · TOP LANGS</text>
  <text x="472" y="15" fill="#000000" font-size="11" font-weight="700" text-anchor="end">{len(langs)} OF {len(st['languages'])}</text>{body}
  <line x1="0" y1="170" x2="480" y2="170" stroke="#444444" stroke-width="0.5"/>
</svg>
"""


def main():
    st = stats(fetch())
    log = {k: v for k, v in st.items() if k not in ("languages", "lang_colors")}
    log["lang_count"] = len(st["languages"])
    log["top_langs"] = sorted(st["languages"].items(), key=lambda kv: kv[1], reverse=True)[:6]
    print(json.dumps(log, indent=2, default=str))

    for path, fn in (("banner.svg", update_banner), ("chart.svg", update_chart), ("stats.svg", update_stats)):
        p = ROOT / path
        s = p.read_text(encoding="utf-8")
        p.write_text(fn(s, st), encoding="utf-8")

    (ROOT / "langs.svg").write_text(render_langs(st), encoding="utf-8")


if __name__ == "__main__":
    main()
