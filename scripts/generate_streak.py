#!/usr/bin/env python3
"""Generate a GitHub-style contribution heatmap + streak card as a static SVG.

Reads contribution data from the GitHub GraphQL API and writes assets/streak.svg.
No third-party services and no dependencies beyond the Python standard library.
"""
import datetime as dt
import json
import os
import sys
import urllib.request

API = "https://api.github.com/graphql"
OUT = os.environ.get("OUT_PATH", "assets/streak.svg")

# GitHub dark-theme palette
BG, BORDER = "#0d1117", "#30363d"
TEXT, MUTED, ACCENT = "#c9d1d9", "#8b949e", "#58a6ff"
LEVELS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]


def gql(query, variables, token):
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "streak-card"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if "errors" in data:
        sys.exit(f"GraphQL error: {data['errors']}")
    return data["data"]


def fetch_days(user, token):
    """Return {date: count} for the whole life of the account (one call per year)."""
    created = gql("query($u:String!){user(login:$u){createdAt}}", {"u": user}, token)["user"]["createdAt"]
    start_year = int(created[:4])
    today = dt.date.today()
    q = """query($u:String!,$from:DateTime!,$to:DateTime!){
      user(login:$u){contributionsCollection(from:$from,to:$to){
        contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}"""
    days = {}
    for year in range(start_year, today.year + 1):
        frm = f"{year}-01-01T00:00:00Z"
        to = f"{year}-12-31T23:59:59Z"
        d = gql(q, {"u": user, "from": frm, "to": to}, token)
        weeks = d["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
        for w in weeks:
            for day in w["contributionDays"]:
                days[dt.date.fromisoformat(day["date"])] = day["contributionCount"]
    return days


def streaks(days):
    today = dt.date.today()
    total = sum(days.values())
    # longest
    longest = run = 0
    longest_end = None
    prev = None
    for d in sorted(days):
        if d > today:
            continue
        if days[d] > 0:
            run = run + 1 if prev and (d - prev).days == 1 and days.get(prev, 0) > 0 else 1
            if run > longest:
                longest, longest_end = run, d
        else:
            run = 0
        prev = d
    # current (today may still be empty, so allow starting from yesterday)
    cur = 0
    d = today if days.get(today, 0) > 0 else today - dt.timedelta(days=1)
    while days.get(d, 0) > 0:
        cur += 1
        d -= dt.timedelta(days=1)
    return total, cur, longest


def level(count, mx):
    if count <= 0:
        return 0
    return min(4, max(1, -(-count * 4 // mx)))  # ceil(count*4/mx)


def render(user, days):
    total, cur, longest = streaks(days)
    today = dt.date.today()
    # grid: 53 columns, Sunday-first like GitHub
    end_sunday = today - dt.timedelta(days=(today.weekday() + 1) % 7)
    first = end_sunday - dt.timedelta(weeks=52)
    window = [first + dt.timedelta(days=i) for i in range(53 * 7)]
    window = [d for d in window if d <= today]
    mx = max([days.get(d, 0) for d in window] + [1])
    year_total = sum(days.get(d, 0) for d in window)

    cell, gap = 11, 3
    step = cell + gap
    left, top = 40, 128
    W, H = left + 53 * step + 24, top + 7 * step + 46
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif">',
         f'<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="8" fill="{BG}" stroke="{BORDER}"/>']

    # stat columns
    cols = [(total, "Total Contributions", "All time"),
            (cur, "Current Streak", "days"),
            (longest, "Longest Streak", "days")]
    cw = (W - 48) / 3
    for i, (val, label, sub) in enumerate(cols):
        cx = 24 + cw * i + cw / 2
        color = ACCENT if i == 1 else TEXT
        o.append(f'<text x="{cx}" y="52" text-anchor="middle" font-size="32" font-weight="700" fill="{color}">{val:,}</text>')
        o.append(f'<text x="{cx}" y="76" text-anchor="middle" font-size="14" font-weight="600" fill="{TEXT}">{label}</text>')
        o.append(f'<text x="{cx}" y="94" text-anchor="middle" font-size="12" fill="{MUTED}">{sub}</text>')
        if i:
            o.append(f'<line x1="{24+cw*i}" y1="24" x2="{24+cw*i}" y2="100" stroke="{BORDER}"/>')
    o.append(f'<line x1="24" y1="108" x2="{W-24}" y2="108" stroke="{BORDER}"/>')

    # month labels + cells
    labels, last_month = [], None
    for idx, d in enumerate(window):
        if idx % 7 == 0 and d.month != last_month:
            last_month = d.month
            labels.append((idx // 7, d.strftime("%b")))
    if len(labels) > 1 and labels[1][0] - labels[0][0] < 3:
        labels.pop(0)  # avoid overlapping labels at the left edge
    for col, name in labels:
        o.append(f'<text x="{left+col*step}" y="{top-8}" font-size="10" fill="{MUTED}">{name}</text>')
    for idx, d in enumerate(window):
        col, row = idx // 7, idx % 7
        c = days.get(d, 0)
        o.append(f'<rect x="{left+col*step}" y="{top+row*step}" width="{cell}" height="{cell}" rx="2" '
                 f'fill="{LEVELS[level(c, mx)]}"><title>{c} contributions on {d.isoformat()}</title></rect>')
    for row, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        o.append(f'<text x="{left-8}" y="{top+row*step+9}" text-anchor="end" font-size="10" fill="{MUTED}">{name}</text>')

    # footer
    fy = top + 7 * step + 26
    o.append(f'<text x="{left}" y="{fy}" font-size="12" fill="{MUTED}">{year_total:,} contributions in the last year · @{user}</text>')
    lx = W - 24 - (5 * step) - 60
    o.append(f'<text x="{lx}" y="{fy}" text-anchor="end" font-size="10" fill="{MUTED}">Less</text>')
    for i, c in enumerate(LEVELS):
        o.append(f'<rect x="{lx+8+i*step}" y="{fy-10}" width="{cell}" height="{cell}" rx="2" fill="{c}"/>')
    o.append(f'<text x="{lx+16+5*step}" y="{fy}" font-size="10" fill="{MUTED}">More</text>')
    o.append("</svg>")
    return "\n".join(o)


def main():
    user = os.environ["GH_USER"]
    token = os.environ["GH_TOKEN"]
    svg = render(user, fetch_days(user, token))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
