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
DAYS = 7             # the README shows this week; fields/<track>.md hold every open role
PAGE_BYTES = 420_000 # GitHub stops rendering a markdown file not far past this
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


def slug(name):
    return name.lower().replace(",", "").replace(" ", "-")


def row(r, prev, rich, now):
    """One table row. rich: logo and the Apply button; plain rows (older roles
    on a field page that would otherwise be too big for GitHub) keep a text link."""
    logo = r.get("logo") or r.get("mark")
    mark = f'<img src="{logo}" width="20" height="20" align="middle">&nbsp; ' if rich and logo else ""
    company = "↳" if r["company"] == prev else f'{mark}**{cell(r["company"])}**'
    title = cell(r["title"]) + (f" {marks(r)}" if marks(r) else "")
    pay = "" if r.get("payEst") else cell(r.get("pay"))
    p = ts(r.get("posted") or r.get("found"))
    age = (now - p).days if p else None
    when = (f"{age}d" if age else "today") if age is not None else ""
    lag = lag_minutes(r)
    if lag is not None:
        when += f" ⚡{lag}m" if lag else " ⚡<1m"
    url = escape(r["url"])
    go = f'<a href="{url}"><img src="{IMG}apply.png" width="78" height="27" alt="Apply"></a>' if rich else f"[Apply]({url})"
    return f"| {company} | {title} | {cell(r.get('where'))} | {pay} | {when} | {go} |"


HEAD = ("| Company | Role | Location | Pay | Posted | &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Apply&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; |\n"
        "| --- | --- | --- | --- | --- | --- |")
IMG = "assets/"


def table(rows, now, budget):
    """Rows as a table, rich while it fits the byte budget, then plain."""
    out, prev, used = [HEAD], None, 0
    for r in rows:
        line = row(r, prev, used < budget, now)
        used += len(line.encode())
        out.append(line)
        prev = r["company"]
    return "\n".join(out)


LEGEND = ("<sub>🔥 Top company &nbsp; ✨ Not on the other public lists &nbsp; ⚡ Found within minutes of posting &nbsp; "
          "🛂 No visa sponsorship &nbsp; 🇺🇸 U.S. citizenship required &nbsp; 🎓 Advanced degree required</sub>")


def banner_html(meta):
    return [
        '<div align="center">',
        f'<a href="{utm("/", "banner")}"><picture>'
        f'<source media="(prefers-color-scheme: dark)" srcset="{IMG}banner-{LEVEL}-dark.png">'
        f'<img src="{IMG}banner-{LEVEL}-light.png" width="100%" alt="Boardsweep: {L["noun"]}"></picture></a>',
        "",
        f'<a href="{utm("/" + L["path"], "cta_email")}"><picture><source media="(prefers-color-scheme: dark)" srcset="{IMG}cta-email-dark.png">'
        f'<img src="{IMG}cta-email-light.png" height="44" alt="Get this list by email, free"></picture></a>&nbsp;&nbsp;'
        f'<a href="{utm("/#pricing", "cta_instant")}"><img src="{IMG}cta-instant.png" height="44" alt="Alerts the minute it is posted"></a>',
        ""]


def main():
    global IMG
    rows, meta = fetch_roles()
    if len(rows) < 20:
        sys.exit(f"only {len(rows)} roles returned; leaving the files as they are")
    try:
        lead = (get("/stats") or {}).get("passLead")
    except Exception:
        lead = None
    rows.sort(key=lambda r: r.get("posted") or r.get("found") or "", reverse=True)
    now = datetime.now(timezone.utc)

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

    first = lambda r: (r.get("tracks") or ["software"])[0]
    by_field = [(k, e, n, [r for r in rows if first(r) == k]) for k, e, n in TRACKS]
    cutoff = now - timedelta(days=DAYS)
    fresh = lambda r: (ts(r.get("posted") or r.get("found")) or cutoff) >= cutoff

    # ── every open role, one field at a time, split into pages GitHub will render
    os.makedirs("fields", exist_ok=True)
    for old in os.listdir("fields"):
        os.remove(os.path.join("fields", old))
    IMG = "../assets/"
    pages = {}
    for k, e, n, g in by_field:
        site = utm(f"/{L['path']}/{k}", f"field_{k}")
        chunks, cur, size = [], [], 0
        for r in g:
            line = len(row(r, None, True, now).encode())
            if cur and size + line > PAGE_BYTES - 30_000:
                chunks.append(cur)
                cur, size = [], 0
            cur.append(r)
            size += line
        chunks.append(cur)
        names = [f"{k}.md"] + [f"{k}-{i}.md" for i in range(2, len(chunks) + 1)]
        pages[k] = len(names)
        nav = " · ".join(f"**Page {i}**" if j == i else f"[Page {i}]({names[i - 1]})" for i in range(1, len(names) + 1)
                         for j in [None]) if len(names) > 1 else ""
        for i, (name, chunk) in enumerate(zip(names, chunks), 1):
            nav = " · ".join(f"**{x}**" if x == i else f"[{x}]({names[x - 1]})" for x in range(1, len(names) + 1)) if len(names) > 1 else ""
            body = ([f"[← Back to the list](../README.md)", "", f"# {e} {n} {L['noun']}", ""])
            if g:
                body += [f"All {len(g):,} open {n.lower()} {L['noun']}, newest first, every link the company's own posting. "
                         f"Filter by city or keyword on [boardsweep.io]({site}), or [get them by email, free]({site}).", ""]
                if nav:
                    body += [f"Page {i} of {len(names)}: {nav}", ""]
                body += [LEGEND, "", table(chunk, now, PAGE_BYTES), ""]
                if nav:
                    body += [nav, ""]
            else:
                body += [f"> [!NOTE]",
                         f"> **No open {n.lower()} {L['noun']} right now.** They do open through the season, often without warning. "
                         f"[Get an email the day one is posted, free]({site}).", ""]
            body += [f"[← Back to the list](../README.md) · [Get these by email, free]({site})", ""]
            with open(f"fields/{name}", "w") as f:
                f.write("\n".join(body))
    IMG = "assets/"

    # ── README: this week, every field ──────────────────────────────────────
    o = banner_html(meta)
    a = o.append
    a(f'<img src="{IMG}stats.svg" width="100%" alt="{meta.get("newToday", 0)} new in the last 24 hours, {meta.get("total", 0)} open">')
    a("</div>")
    a("")
    a("> [!TIP]")
    a(f"> **This list runs a day behind.** The {meta.get('newToday', 0):,} {L['noun']} we found in the last 24 hours are already in subscribers' inboxes, "
      f"and appear here tomorrow. [Get a free daily email]({utm('/' + L['path'], 'tip_email')}), "
      f"or [get each one the minute the company posts it]({utm('/#pricing', 'tip_instant')}) with the season pass (7 days free).")
    a("")
    a("<br>")
    a("")
    a("## Browse by field")
    a("")
    a("| Field | Open now | New this week | |")
    a("| --- | ---: | ---: | --- |")
    for k, e, n, g in by_field:
        wk = sum(1 for r in g if fresh(r))
        site = utm(f"/{L['path']}/{k}", f"browse_{k}")
        if g:
            a(f"| {e} **[{n}](fields/{k}.md)** | {len(g):,} | {wk if wk else 'N/A'} | [Email me these, free]({site}) |")
        else:
            a(f"| {e} {n} | N/A | N/A | [Tell me when one opens]({site}) |")
    a("")
    a("<br>")
    a("")
    a(LEGEND)
    a("")
    budget = PAGE_BYTES - 60_000
    for k, e, n, g in by_field:
        week = [r for r in g if fresh(r)]
        if not week:
            a("<br>")
            a("")
            a(f"## {n}")
            a("")
            more = f'<a href="fields/{k}.md">See all {len(g):,} open</a> · ' if g else ""
            a(f'<sub>N/A: no new {n.lower()} {L["noun"]} this week. {more}<a href="{utm("/" + L["path"] + "/" + k, "empty_" + k)}">Email me when one is posted</a></sub>')
            a("")
            continue
        a("<br>")
        a("")
        a(f"## {n}")
        a("")
        a(f'<sub>This week\'s {len(week):,} of {len(g):,}. <a href="fields/{k}.md">See all {len(g):,}{" (" + str(pages[k]) + " pages)" if pages[k] > 1 else ""}</a> · '
          f'<a href="{utm("/" + L["path"] + "/" + k, "track_" + k)}">Get only {n.lower()} {L["noun"]} by email, free</a></sub>')
        a("")
        t = table(week, now, max(0, budget))
        budget -= len(t.encode())
        a(t)
        a("")
    a("---")
    a("")
    a('<div align="center">')
    a("")
    a("**Missing a role, or a link that's wrong?** [Tell us](../../issues/new/choose): every report helps us read more company boards.")
    a("")
    a("**Ask your AI assistant for roles:** add Boardsweep to Claude, ChatGPT or Claude Code with [our free connector](https://github.com/Boardsweep/mcp).")
    a("")
    a(f"Also see: [{L['other']}]({L['other_url']}) · [Every {L['one']}, filterable, on boardsweep.io]({utm('/' + L['path'], 'footer')})")
    a("")
    a(f"<sub>⚡ is measured from the time the company published the posting, where its job board gives one. "
      f"Updated {now:%b %d, %Y at %H:%M} UTC. Not affiliated with any company listed.</sub>")
    a("")
    a("</div>")
    a("")
    with open("README.md", "w") as f:
        f.write("\n".join(o))
    sizes = {f: os.path.getsize(f) for f in ["README.md"] + [f"fields/{k}.md" for k, *_ in by_field]}
    print(f"{len(rows)} roles · " + " · ".join(f"{f} {v // 1024}KB" for f, v in sizes.items()))


if __name__ == "__main__":
    main()
