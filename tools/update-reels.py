#!/usr/bin/env python3
"""
Refresh the Instagram reel embeds in index.html.

    python tools/update-reels.py --shortcodes DYuj6RCxDPa,DZbT9jGp6Sf
    python tools/update-reels.py --from-file reels.txt --max 6 --commit

WHY THE SHORTCODES ARE AN INPUT AND NOT SCRAPED HERE
----------------------------------------------------
instagram.com/<user>/ served over plain HTTP returns a login-walled shell:
~600KB of HTML containing zero post permalinks. Verified with a real browser
User-Agent. So this script deliberately does NOT try to scrape the profile —
a scraper that silently returns "no new reels" every week is worse than no
automation at all, because it looks like it is working.

Getting the shortcodes requires a renderer (a logged-out headless browser, an
Instagram Graph API token, or an agent with a rendering fetch). That step is
the fragile one and is kept OUT of this script. Everything here — validating,
diffing, rewriting, committing — is deterministic and testable.

WHAT IT DOES
------------
1. Validates each shortcode by fetching its embed page and rejecting any that
   are unavailable, so a deleted or private reel never lands on the page.
2. Rewrites the block between the REELS:START / REELS:END markers, newest
   first, capped at --max.
3. Reports what changed. Exits 0 with "no change" when the set already matches,
   so a scheduled run is a no-op on a quiet week.
"""

import argparse
import re
import subprocess
import sys
import urllib.error
import urllib.request

HTML = "index.html"
START = "<!-- REELS:START"
END = "<!-- REELS:END -->"
# DO NOT "modernise" this User-Agent. Instagram serves two different responses:
# a full Chrome UA gets a ~607KB login-walled shell for EVERY shortcode, real or
# fake, which makes validation silently pass everything. This shorter UA gets the
# real ~250KB embed document. Verified both ways.
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
HANDLE = "@zakglosserman"

# The discriminator. A live reel's embed document contains video_url; a dead or
# nonexistent one returns a ~210KB page without it. Checking for the string
# "video" instead matches the login shell too — that was a real bug here.
LIVE_MARKER = "video_url"
DEAD = ("isn't available", "Page Not Found", "page-not-found")


def validate(code, timeout=25):
    """True if the embed renders a real post. Fails closed on any error."""
    url = f"https://www.instagram.com/reel/{code}/embed/"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "ignore")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"  ! {code}: fetch failed ({e}) — skipping", file=sys.stderr)
        return False
    if any(m in body for m in DEAD):
        print(f"  ! {code}: unavailable — skipping", file=sys.stderr)
        return False
    if LIVE_MARKER not in body:
        print(f"  ! {code}: no {LIVE_MARKER} in embed ({len(body)}B) — dead, private, "
              f"or Instagram served a login wall — skipping", file=sys.stderr)
        return False
    return True


def figure(code):
    """One clip card.

    NOTE: data-src, not src. The page holds the embed URL in data-src and swaps
    it in via IntersectionObserver 300px before the clip scrolls into view.
    Native loading="lazy" was measured to fetch 5 of 9 embeds before any scroll
    on a 390px viewport, because Chrome's threshold is ~3000px. If you change
    this back to src you silently undo that and every embed loads up front.
    """
    embed = f"https://www.instagram.com/reel/{code}/embed/"
    link = f"https://www.instagram.com/reel/{code}/"
    return (
        '    <figure class="clip">\n'
        f'      <div class="clip-media"><iframe data-src="{embed}" '
        f'title="Instagram reel by {HANDLE}" scrolling="no" allowfullscreen></iframe></div>\n'
        f'      <figcaption class="clip-cap"><span>{HANDLE}</span>'
        f'<a href="{link}" target="_blank" rel="noopener">Instagram ↗</a></figcaption>\n'
        "    </figure>\n"
    )


def current_codes(block):
    return re.findall(r"/reel/([A-Za-z0-9_-]+)/embed/", block)


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--shortcodes", help="comma/whitespace separated, newest first")
    src.add_argument("--from-file", help="file with one shortcode per line, newest first")
    ap.add_argument("--max", type=int, default=6, help="how many to keep (default 6)")
    ap.add_argument("--commit", action="store_true", help="git commit the change")
    ap.add_argument("--push", action="store_true", help="git push after committing")
    ap.add_argument("--skip-validate", action="store_true", help="skip the reachability check")
    args = ap.parse_args()

    raw = args.shortcodes if args.shortcodes else open(args.from_file, encoding="utf-8").read()
    incoming, seen = [], set()
    for c in re.split(r"[,\s]+", raw.strip()):
        c = c.strip()
        # accept a full URL as well as a bare shortcode
        m = re.search(r"/(?:reel|p)/([A-Za-z0-9_-]+)", c)
        if m:
            c = m.group(1)
        if c and c not in seen:
            seen.add(c)
            incoming.append(c)
    if not incoming:
        sys.exit("no shortcodes given")

    html = open(HTML, encoding="utf-8").read()
    i, j = html.find(START), html.find(END)
    if i == -1 or j == -1 or j < i:
        sys.exit(f"could not find REELS markers in {HTML} — was the block hand-edited?")
    head_end = html.find("\n", i) + 1
    existing = current_codes(html[head_end:j])

    print(f"on page now : {len(existing)} -> {', '.join(existing) or '(none)'}")
    print(f"incoming    : {len(incoming)} -> {', '.join(incoming)}")
    new = [c for c in incoming if c not in existing]
    print(f"new         : {', '.join(new) if new else '(none)'}")

    if not args.skip_validate:
        print("validating…")
        incoming = [c for c in incoming if validate(c)]
        if not incoming:
            sys.exit("every incoming shortcode failed validation — refusing to empty the section")

    keep = incoming[: args.max]
    if keep == existing:
        print("no change — page already matches")
        return 0

    block = "".join(figure(c) for c in keep)
    out = html[:head_end] + block + html[j:]
    open(HTML, "w", encoding="utf-8", newline="").write(out)

    dropped = [c for c in existing if c not in keep]
    print(f"\nwrote {len(keep)} reels; added {len([c for c in keep if c not in existing])}, "
          f"dropped {len(dropped)}{': ' + ', '.join(dropped) if dropped else ''}")

    if args.commit:
        added = [c for c in keep if c not in existing]
        msg = "Update Instagram reels\n\n" + (
            f"Added: {', '.join(added)}\n" if added else ""
        ) + (f"Dropped: {', '.join(dropped)}\n" if dropped else "")
        subprocess.run(["git", "add", HTML], check=True)
        subprocess.run(["git", "commit", "-q", "-m", msg], check=True)
        print("committed")
        if args.push:
            subprocess.run(["git", "push", "-q", "origin", "main"], check=True)
            print("pushed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
