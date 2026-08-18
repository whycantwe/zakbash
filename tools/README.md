# tools/

## update-reels.py

Refreshes the Instagram reel embeds in `index.html` (the block between the
`REELS:START` / `REELS:END` markers).

```bash
python tools/update-reels.py --shortcodes "DYuj6RCxDPa,DZbT9jGp6Sf" --max 6 --commit --push
```

Newest first. Validates each shortcode against Instagram, skips dead or private
ones, refuses to empty the section if all of them fail, and no-ops when the set
already matches.

### Why it takes shortcodes as input instead of scraping

`instagram.com/<user>/` over plain HTTP returns a ~600KB login-walled shell with
zero permalinks in it. Discovery needs an actual renderer — a headless browser,
an Instagram Graph API token, or an agent with a rendering fetch. That fragile
step is kept out of this script on purpose: a scraper that silently returns "no
new reels" every week is worse than no automation, because it looks like it works.

The weekly Sunday job (`~/.claude/scheduled-tasks/zakbash-weekly-reels/`) does
discovery with a rendering fetch and then calls this script.

### The User-Agent is load-bearing

Instagram serves a full Chrome UA the login shell for *every* shortcode, real or
fake — which makes validation pass everything. The shorter UA in the script gets
the real embed document, where `video_url` cleanly separates live from dead.
Don't "modernise" it.
