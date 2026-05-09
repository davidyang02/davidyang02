#!/usr/bin/env python3
"""Patch banner.svg and chart.svg with the latest GitHub stats."""
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
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount date } }
      }
    }
    pullRequests { totalCount }
    repositories(ownerAffiliations: OWNER, isFork: false) { totalCount }
    followers { totalCount }
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
    return {
        "total": cal["totalContributions"],
        "high": high,
        "avg": avg,
        "active": active,
        "streak": streak,
        "longest": longest,
        "prs": u["pullRequests"]["totalCount"],
        "repos": u["repositories"]["totalCount"],
        "follow": u["followers"]["totalCount"],
        "ts": datetime.datetime.utcnow().strftime("%Y-%m-%d  %H:%M:%S UTC"),
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
    # The big "560" next to the green last-point dot
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

    # VOL bar (max width 900 px, max value 365 days)
    width = round(st["active"] / 365 * 900)
    pct = round(st["active"] / 365 * 100)
    s = re.sub(
        r'(<rect x="70" y="332" width=")\d+(" height="14" fill="#FF7700"[^/]*/>)',
        rf'\g<1>{width}\g<2>', s, count=1,
    )
    s = re.sub(
        r'(<text x="990" y="342"[^>]*font-weight="700">)\d+%(</text>)',
        rf'\g<1>{pct}%\g<2>', s, count=1,
    )
    return s


def main():
    st = stats(fetch())
    print(json.dumps(st, indent=2))

    for path, fn in (("banner.svg", update_banner), ("chart.svg", update_chart)):
        p = ROOT / path
        s = p.read_text(encoding="utf-8")
        p.write_text(fn(s, st), encoding="utf-8")


if __name__ == "__main__":
    main()
