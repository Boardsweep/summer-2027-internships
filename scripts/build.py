"""Builds this repo's README.md, listings.json and assets/stats.svg from
Boardsweep's public role feed (the roles on boardsweep.io's free lists: a day
behind the alerts, every link the employer's own posting). Run on a schedule by
.github/workflows/update.yml; standard library only.

    LEVEL=internship python3 scripts/build.py      # or LEVEL=newgrad
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from html import escape

API = os.environ.get("BOARDSWEEP_API", "https://hotmail0102713010--boardsweep-api-web.modal.run")
LEVEL = os.environ.get("LEVEL", "internship")
SITE = "https://boardsweep.io"
DAYS = 14            # the README table; listings.json holds every open role
MAX_ROWS = 650       # keeps the README well under GitHub's render limit
TRACKS = [("software", "💻", "Software engineering"), ("aiml", "🤖", "AI, ML and data"), ("quant", "📈", "Quant"),
          ("hardware", "🔧", "Hardware"), ("product", "📱", "Product"), ("design", "🎨", "Design"), ("security", "🛡️", "Security")]
L = {"internship": dict(path="internships", noun="internships", one="internship", other="New grad roles",
                        other_url="https://github.com/Boardsweep/new-grad-2027"),
     "newgrad": dict(path="new-grad", noun="new grad and entry-level roles", one="role", other="Summer 2027 internships",
                     other_url="https://github.com/Boardsweep/summer-2027-internships")}[LEVEL]
EXACT = {"Greenhouse", "Lever", "Ashby"}      # boards that publish the posting's exact time


def utm(path, content):
    return f"{SITE}{path}{'&' if '?' in path else '?'}utm_source=github&utm_medium=readme&utm_campaign={L['path']}&utm_content={content}"


def get(path):
    for attempt in range(4):
        try:
            req = urllib.request.Request(API + path, headers={"User-Agent": "boardsweep-lists/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))


def fetch_roles():
    rows, offset, meta = [], 0, {}
    while offset < 12000:
        page = get(f"/public/roles?level={LEVEL}&limit=100&offset={offset}")
        meta = {k: v for k, v in page.items() if k != "roles"}
        got = page.get("roles") or []
        rows += got
        # Step by the page size, not by what came back: the API drops a few
        # non-US rows after paging, so a short page is not the last one.
        offset += 100
        if offset >= (meta.get("total") or 0) or (not got and offset > 300):
            break
    return rows, meta


def ts(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")) if iso else None


def cell(s):
    return escape(str(s or "")).replace("|", "&#124;").replace("\n", " ").strip()


def lag_minutes(r):
    """Minutes from the employer publishing to us finding it, where the board
    gives an exact time. None otherwise (a date alone proves nothing)."""
    if r.get("via") not in EXACT:
        return None
    p, f = ts(r.get("posted")), ts(r.get("found"))
    if not p or not f:
        return None
    m = (f - p).total_seconds() / 60
    return round(m) if 0 <= m <= 60 else None


def marks(r):
    out = []
    if r.get("top"): out.append("🔥")
    if r.get("notListed"): out.append("✨")
    if r.get("noVisa"): out.append("🛂")
    if r.get("citizen"): out.append("🇺🇸")
    if r.get("advanced"): out.append("🎓")
    return " ".join(out)


def stats_svg(meta, lead):
    cards = [(f"{meta.get('newToday', 0):,}", f"new {L['noun']} found in the last 24 hours"),
             (f"{meta.get('total', 0):,}", f"open {L['noun']}, all straight from company boards"),
             (f"{meta.get('notListed', 0):,}", "found this week that the other public lists don't have")]
    if lead and lead.get("roles") and lead.get("hours"):
        cards.append((f"{lead['hours']}h", f"how much earlier pass holders got {lead['roles']} top-company roles this week"))
    w = 1280 // len(cards)
    parts = []
    for i, (big, small) in enumerate(cards):
        x = i * w
        parts.append(f'<g transform="translate({x},0)"><text x="28" y="62" class="b">{escape(big)}</text>'
                     f'<foreignObject x="28" y="78" width="{w - 48}" height="60"><div xmlns="http://www.w3.org/1999/xhtml" class="s">{escape(small)}</div></foreignObject></g>')
        if i:
            parts.append(f'<line x1="{x}" y1="22" x2="{x}" y2="128" class="l"/>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="150" viewBox="0 0 1280 150">
<style>
.b{{font:600 40px Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;letter-spacing:-1.6px;fill:#181818}}
.s{{font:400 16px/1.4 Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;color:#686868}}
.f{{fill:#ffffff;stroke:#e1e4e8}} .l{{stroke:#ededed}}
@media (prefers-color-scheme: dark){{.b{{fill:#f2f4f7}} .s{{color:#9da7b3}} .f{{fill:#0d1117;stroke:#30363d}} .l{{stroke:#30363d}}}}
</style>
<rect x="0.5" y="0.5" width="1279" height="149" rx="12" class="f"/>
{''.join(parts)}
</svg>
"""


def main():
    rows, meta = fetch_roles()
    if len(rows) < 20:
        sys.exit(f"only {len(rows)} roles returned; leaving the files as they are")
    try:
        lead = (get("/stats") or {}).get("passLead")
    except Exception:
        lead = None
    rows.sort(key=lambda r: r.get("posted") or r.get("found") or "", reverse=True)

    with open("listings.json", "w") as f:
        json.dump([{"company": r["company"], "title": r["title"], "location": r.get("where"),
                    "pay": None if r.get("payEst") else r.get("pay"), "tracks": r.get("tracks") or [],
                    "url": r["url"], "date_posted": r.get("posted"), "date_found": r.get("found"),
                    "top_company": bool(r.get("top")), "no_sponsorship": bool(r.get("noVisa")),
                    "citizenship_required": bool(r.get("citizen")), "advanced_degree": bool(r.get("advanced"))}
                   for r in rows], f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.makedirs("assets", exist_ok=True)
    with open("assets/stats.svg", "w") as f:
        f.write(stats_svg(meta, lead))

    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS)
    recent = [r for r in rows if (ts(r.get("posted") or r.get("found")) or cutoff) >= cutoff][:MAX_ROWS]
    first = lambda r: (r.get("tracks") or ["software"])[0]
    groups = [(k, e, n, [r for r in recent if first(r) == k]) for k, e, n in TRACKS]
    groups = [g for g in groups if g[3]]
    now = datetime.now(timezone.utc)

    o = []
    a = o.append
    a('<div align="center">')
    a(f'<a href="{utm("/", "banner")}"><picture>'
      f'<source media="(prefers-color-scheme: dark)" srcset="assets/banner-{LEVEL}-dark.png">'
      f'<img src="assets/banner-{LEVEL}-light.png" width="100%" alt="Boardsweep: {L["noun"]}"></picture></a>')
    a("")
    a(f'<a href="{utm("/" + L["path"], "cta_email")}"><picture><source media="(prefers-color-scheme: dark)" srcset="assets/cta-email-dark.png">'
      f'<img src="assets/cta-email-light.png" height="44" alt="Get this list by email, free"></picture></a>&nbsp;&nbsp;'
      f'<a href="{utm("/#pricing", "cta_instant")}"><img src="assets/cta-instant.png" height="44" alt="Alerts the minute it is posted"></a>')
    a("")
    a(f'<img src="assets/stats.svg" width="100%" alt="{meta.get("newToday", 0)} new in the last 24 hours, {meta.get("total", 0)} open">')
    a("</div>")
    a("")
    a(f"> [!TIP]")
    a(f"> **This list runs a day behind.** The {meta.get('newToday', 0):,} {L['noun']} we found in the last 24 hours are already in subscribers' inboxes, "
      f"and appear here tomorrow. [Get a free daily email]({utm('/' + L['path'], 'tip_email')}), "
      f"or [get each one the minute the company posts it]({utm('/#pricing', 'tip_instant')}) with the season pass (7 days free).")
    a("")
    a("### Browse by field")
    a("")
    a(" · ".join(f"{e} **[{n}](#{n.lower().replace(',', '').replace(' ', '-')})** ({len(g):,})" for k, e, n, g in groups))
    a("")
    a("<sub>🔥 Top company &nbsp; ✨ Not on the other public lists &nbsp; ⚡ Found within minutes of posting &nbsp; "
      "🛂 No visa sponsorship &nbsp; 🇺🇸 U.S. citizenship required &nbsp; 🎓 Advanced degree required</sub>")
    a("")
    for k, e, n, g in groups:
        a(f"## {n}")
        a("")
        a(f'<sub>Want only {n.lower()} {L["noun"]} in your inbox? <a href="{utm("/" + L["path"] + "/" + k, "track_" + k)}">Get them free by email</a></sub>')
        a("")
        a("| Company | Role | Location | Pay | Posted | |")
        a("| --- | --- | --- | --- | --- | --- |")
        prev = None
        for r in g:
            mark = f'<img src="{r["mark"]}" width="16" height="16" alt=""> ' if r.get("mark") else ""
            company = "↳" if r["company"] == prev else f'{mark}**{cell(r["company"])}**'
            prev = r["company"]
            title = cell(r["title"]) + (f" {marks(r)}" if marks(r) else "")
            pay = "" if r.get("payEst") else cell(r.get("pay"))
            p = ts(r.get("posted") or r.get("found"))
            age = (now - p).days if p else None
            when = (f"{age}d" if age else "today") if age is not None else ""
            lag = lag_minutes(r)
            if lag is not None:
                when += f" ⚡{lag}m" if lag else " ⚡<1m"
            a(f'| {company} | {title} | {cell(r.get("where"))} | {pay} | {when} | '
              f'<a href="{escape(r["url"])}"><img src="assets/apply.png" width="74" alt="Apply"></a> |')
        a("")
    a("---")
    a("")
    a('<div align="center">')
    a("")
    a(f"**Missing a role, or a link that's wrong?** [Tell us](../../issues/new/choose): every report helps us read more company boards.")
    a("")
    a(f"Also see: [{L['other']}]({L['other_url']}) · [Every {L['one']} on boardsweep.io]({utm('/' + L['path'], 'footer')})")
    a("")
    a(f"<sub>⚡ is measured from the time the company published the posting, where its job board gives one. "
      f"Updated {now:%b %d, %Y at %H:%M} UTC. Not affiliated with any company listed.</sub>")
    a("")
    a("</div>")
    a("")
    with open("README.md", "w") as f:
        f.write("\n".join(o))
    print(f"{len(rows)} roles · {len(recent)} in the README · {sum(1 for r in recent if r.get('mark'))} with logos")


if __name__ == "__main__":
    main()
