#!/usr/bin/env python3
"""Patch banner/chart SVGs and regenerate equity.svg with latest GitHub data."""
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
    createdAt
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

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fmt_md(d):
    return f"{MONTHS[d.month - 1]} {d.day}"


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
    days = []
    for w in cal["weeks"]:
        for d in w["contributionDays"]:
            days.append((datetime.date.fromisoformat(d["date"]), d["contributionCount"]))
    days.sort(key=lambda t: t[0])
    counts = [c for _, c in days]
    high = max(counts) if counts else 0
    avg = round(sum(counts) / max(len(counts), 1), 1)
    active = sum(1 for c in counts if c > 0)

    # Current streak
    streak = 0
    streak_end = streak_start = None
    for date, c in reversed(days):
        if c > 0:
            streak += 1
            if streak_end is None:
                streak_end = date
            streak_start = date
        else:
            break

    # Longest streak
    longest = run = 0
    cur_start = best_start = best_end = None
    for date, c in days:
        if c > 0:
            if run == 0:
                cur_start = date
            run += 1
            if run > longest:
                longest = run
                best_start = cur_start
                best_end = date
        else:
            run = 0

    repos = u["repositories"]["nodes"]
    repo_stars = sum(r["stargazerCount"] for r in repos)

    lang_bytes = {}
    lang_color = {}
    for r in repos:
        for e in r["languages"]["edges"]:
            n = e["node"]["name"]
            lang_bytes[n] = lang_bytes.get(n, 0) + e["size"]
            lang_color[n] = e["node"]["color"] or "#888888"

    created = datetime.date.fromisoformat(u["createdAt"][:10])

    return {
        "total": cal["totalContributions"],
        "high": high,
        "avg": avg,
        "active": active,
        "streak": streak,
        "longest": longest,
        "streak_range": (fmt_md(streak_start), fmt_md(streak_end)) if streak_start else None,
        "longest_range": (fmt_md(best_start), fmt_md(best_end)) if best_start else None,
        "prs": u["pullRequests"]["totalCount"],
        "issues": u["issues"]["totalCount"],
        "repos": u["repositories"]["totalCount"],
        "follow": u["followers"]["totalCount"],
        "stars": repo_stars,
        "commits_year": u["contributionsCollection"]["totalCommitContributions"],
        "languages": lang_bytes,
        "lang_colors": lang_color,
        "created": created,
        "ts": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d  %H:%M:%S UTC"),
    }


def replace_after_label(svg, label, new_value):
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


def render_equity(st):
    # ------- STATS column (x=0..400) -------
    stats_tiles = []
    tile_data = [
        (("CONTRIB", st["total"]), ("STARS", st["stars"]), ("FOLLOW", st["follow"])),
        (("COMMITS", st["commits_year"]), ("PRs", st["prs"]), ("REPOS", st["repos"])),
    ]
    for ri, row in enumerate(tile_data):
        label_y = 70 + ri * 64
        value_y = 100 + ri * 64
        for ci, (label, value) in enumerate(row):
            x = 20 + ci * 130
            stats_tiles.append(
                f'<text x="{x}" y="{label_y}" fill="#888888" font-size="9" font-weight="700">{label}</text>'
                f'<text x="{x}" y="{value_y}" fill="#FFFFFF" font-size="22" font-weight="700">{value}</text>'
            )
    stats_block = "\n  ".join(stats_tiles)

    # ------- LANGS column (x=400..800) -------
    langs = sorted(st["languages"].items(), key=lambda kv: kv[1], reverse=True)[:6]
    lang_total = sum(b for _, b in langs) or 1
    lang_rows = []
    bar_x, bar_w_max = 520, 240
    for i, (name, size) in enumerate(langs):
        y = 64 + i * 22
        pct = size / lang_total * 100
        bar_w = round(size / lang_total * bar_w_max, 1)
        color = st["lang_colors"].get(name, "#888888")
        display = name if len(name) <= 12 else name[:11] + "…"
        lang_rows.append(
            f'<text x="414" y="{y + 9}" fill="#FFFFFF" font-size="11">{display}</text>'
            f'<rect x="{bar_x}" y="{y}" width="{bar_w_max}" height="12" fill="#1A1A1A"/>'
            f'<rect x="{bar_x}" y="{y}" width="{bar_w}" height="12" fill="{color}"/>'
            f'<text x="780" y="{y + 9}" fill="#FFFFFF" font-size="11" text-anchor="end">{pct:.1f}%</text>'
        )
    langs_block = "\n  ".join(lang_rows) if lang_rows else (
        '<text x="600" y="100" fill="#888888" font-size="11" text-anchor="middle">no language data</text>'
    )

    # ------- STREAK column (x=800..1200) -------
    sr = st["streak_range"] or ("--", "--")
    lr = st["longest_range"] or ("--", "--")
    created_label = f"{MONTHS[st['created'].month - 1]} {st['created'].year} - Present"

    # ------- footer timestamp -------
    date = st["ts"][:10]

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 200" preserveAspectRatio="xMidYMid meet" font-family="ui-monospace, Consolas, 'Courier New', monospace">
  <rect width="1200" height="200" fill="#000000"/>

  <!-- Panel header -->
  <rect x="0" y="0" width="3" height="26" fill="#FF7700"/>
  <line x1="0" y1="26" x2="1200" y2="26" stroke="#444444" stroke-width="0.5"/>
  <text x="14" y="18" fill="#FF7700" font-size="13" font-weight="700">EQUITY · ACCT SUMMARY · DAVIDYANG02</text>
  <text x="1186" y="18" fill="#FF7700" font-size="13" font-weight="700" text-anchor="end">1Y</text>

  <!-- Column dividers -->
  <line x1="400" y1="26" x2="400" y2="200" stroke="#222222" stroke-width="1"/>
  <line x1="800" y1="26" x2="800" y2="200" stroke="#222222" stroke-width="1"/>

  <!-- Sub-headers -->
  <text x="14" y="46" fill="#888888" font-size="10" font-weight="700">STATS</text>
  <text x="414" y="46" fill="#888888" font-size="10" font-weight="700">TOP LANGS · {len(langs)} OF {len(st['languages'])}</text>
  <text x="814" y="46" fill="#888888" font-size="10" font-weight="700">STREAK</text>

  <!-- STATS -->
  {stats_block}

  <!-- LANGS -->
  {langs_block}

  <!-- STREAK: total | ring | longest -->
  <text x="870" y="110" fill="#FFFFFF" font-size="28" font-weight="700" text-anchor="middle">{st['total']}</text>
  <text x="870" y="138" fill="#888888" font-size="10" font-weight="700" text-anchor="middle">TOTAL CONTRIB</text>
  <text x="870" y="158" fill="#666666" font-size="9" text-anchor="middle">{created_label}</text>

  <circle cx="1000" cy="110" r="38" stroke="#AAAAAA" stroke-width="2" fill="none"/>
  <polygon points="998,68 1002,68 1000,60" fill="#00C853"/>
  <text x="1000" y="120" fill="#FFFFFF" font-size="28" font-weight="700" text-anchor="middle">{st['streak']}</text>
  <text x="1000" y="148" fill="#FF7700" font-size="10" font-weight="700" text-anchor="middle">CURRENT STREAK</text>
  <text x="1000" y="168" fill="#666666" font-size="9" text-anchor="middle">{sr[0]} - {sr[1]}</text>

  <text x="1130" y="110" fill="#FFFFFF" font-size="28" font-weight="700" text-anchor="middle">{st['longest']}</text>
  <text x="1130" y="138" fill="#888888" font-size="10" font-weight="700" text-anchor="middle">LONGEST STREAK</text>
  <text x="1130" y="158" fill="#666666" font-size="9" text-anchor="middle">{lr[0]} - {lr[1]}</text>

  <line x1="0" y1="186" x2="1200" y2="186" stroke="#222222" stroke-width="0.5"/>
  <text x="14" y="198" fill="#666666" font-size="9">DAVIDYANG02 US &lt;Equity&gt; GP &lt;Go&gt;</text>
  <text x="1186" y="198" fill="#666666" font-size="9" text-anchor="end">{date}</text>
</svg>
"""


def main():
    st = stats(fetch())
    log = {k: v for k, v in st.items() if k not in ("languages", "lang_colors")}
    log["lang_count"] = len(st["languages"])
    log["top_langs"] = sorted(st["languages"].items(), key=lambda kv: kv[1], reverse=True)[:6]
    print(json.dumps(log, indent=2, default=str))

    for path, fn in (("banner.svg", update_banner), ("chart.svg", update_chart)):
        p = ROOT / path
        s = p.read_text(encoding="utf-8")
        p.write_text(fn(s, st), encoding="utf-8")

    (ROOT / "equity.svg").write_text(render_equity(st), encoding="utf-8")


if __name__ == "__main__":
    main()
