# eraifarligt.dk — Worklog

## 2026-08-21 — Session 1: Discovery of the 2025 system

### What exists (the "2025 version")

**Files in `Old Project/`**

| File | What it is |
|---|---|
| `Er AI Farligt_ final.json` | The real, final n8n workflow (14 nodes). Danish. Monthly schedule. |
| `isAIdangerous_n8n_workflow_v1_FINAL_GEMINI.json` | Earlier v1 draft, English, weekly, 5 nodes, never finished (no output/publish nodes). |
| `ai_risk_monitor_workflow.json` | Broken — contains only the literal string `{{CANMORE_TEXT:...}}`, 49 bytes. Dead file. |
| `index.html` / `=verdict-july-2025.html` | Identical. A published verdict page from July 31, 2025 (English wording, verdict "maybe", 7 sources). |
| `index/index.html` | Pre-launch placeholder ("Automated verdicts coming soon"). |
| `gammel HTML kode.index.txt` | Early n8n Code-node snippet that built the HTML from `$json.date/verdict/reason/sources`. |

**Live site (checked 2026-08-21):** https://eraifarligt.dk still serves the verdict dated **1. August 2025** (updated 3. August 2025). Verdict "Måske", 15 sources. So the pipeline has been dead for ~12 months.

**Hosting:** `github.com/peterbrandgardmadsen/ai-verdict-site` (public, 42 commits) — but see the correction in part 6: the site is served by **Netlify**, not GitHub Pages. Repo root holds `index.html` plus stray files `verdict-july-2025.html`, `verdict-july-2025-1.html`, `verdict-july-2025-2.html`, `=verdict-july-2025.html` — the `=` prefix is a shell/naming accident. Custom domain eraifarligt.dk points at it.

### The 2025 architecture (from `Er AI Farligt_ final.json`)

```
Monthly Trigger (schedule, 08:00, every month)
   ├──> TechCrunch RSS  ──┐
   ├──> OpenAI Blog RSS ──┤ Merge (combineByPosition, 3 inputs)
   └──> Reddit /r/artificial RSS ──┘
                              └──> Aggregate RSS Items (aggregateAllItemData)
                                    └──> Code: "Combine RSS feeds to single text block"
                                          -> { rssText, sources }
                                          └──> AI Agent (langchain agent)
                                                 · LLM: OpenAI gpt-4.1-mini
                                                 · Memory: bufferWindow, key "monthly-risk-report"
                                                 · Output parser: structured JSON
                                                   { bedømmelse, ræsonnement, kilder }
                                                 └──> Set "Tilføj dato" (adds ISO date)
                                                       └──> Google Sheets append
                                                             (AI_danger_verdicts,
                                                              sheet id 1xGGYVTG-HixFfmBNyjqzD-5Wbx98jGz1cmkAr6GSWTo)
                                                             └──> Code "Create HTML" (inline-styled page)
                                                                   └──> GitHub node: edit file
                                                                        peterbrandgardmadsen/ai-verdict-site
                                                                        index.html on main
```

### Prompt used in 2025 (verbatim intent)

> "Du er en analytiker med speciale i teknologi, etik og samfundssikkerhed. Din opgave er at analysere nedenstående artikler (aggregeret fra nyhedskilder) og vurdere: Er kunstig intelligens (AI) farlig i denne måned?"
> Output: JSON `{ "bedømmelse": "Ja"|"Nej"|"Måske", "ræsonnement": "400-700 tegn", "kilder": <antal> }`

### Known weaknesses of the 2025 version

1. **`Merge` with `combineByPosition` across 3 feeds is lossy** — it truncates to the shortest feed and pairs unrelated articles into one item. This is why "sources analyzed" was 7 and 15, not the real article count.
2. **Only 3 sources**, one of which (Reddit /r/artificial `.rss`) is unmoderated opinion, and OpenAI's blog is vendor marketing. No academic, regulatory, or incident-tracking source.
3. **`kilder` was invented by the LLM**, not counted — the prompt literally told it to "anvend 10-20 forskellige kilder", so the number is a hallucinated field, not a measurement.
4. **Buffer-window memory keyed `monthly-risk-report`** made runs non-reproducible; the verdict depended on n8n's in-process memory state.
5. **No history on the site.** Every run overwrote `index.html`. The Google Sheet is the only archive.
6. **Single overwritten file**, no per-month permalinks (the `verdict-july-2025*.html` files are manual leftovers).
7. **No error handling / no proof of run.** If a feed 404s or the LLM returns bad JSON, the workflow fails silently and the site just keeps the old verdict — exactly what happened for the last 12 months.
8. **Danish field names with æ/ø in JSON keys** (`bedømmelse`, `ræsonnement`) caused encoding damage in the exported workflow file.
9. n8n dependency — the whole thing dies if the n8n instance stops. It did.

### Goal for the 2026 version

Rebuild as **Python**, fully automated, no n8n. Keep both descriptions ("2025 description" / "2026 description") for the site so the rebuild story is visible.

### Open questions for Peter → see next log entry

---

## 2026-08-21 — Session 1, part 2: Decisions for the 2026 version

Peter's answers:

| Question | Decision |
|---|---|
| Ambition | **Scored index** — verdict backed by a computed 0–100 danger index over weighted sub-dimensions, with citations, trend chart and per-month history. |
| Runtime | **GitHub Actions cron** — Python in the repo, no server, no n8n. Failures are visible in the Actions tab. |
| Model | **Anthropic API (Claude)** — key already exists. |
| Language | **Danish only.** |
| Repo | **New clean repo**, so the live site is never broken mid-rebuild. |
| History | **JSON files committed to the repo** (`data/verdicts/YYYY-MM.json`). No Google Sheets, no credentials. |

### Feed audit (probed live 2026-08-21, HTTP status + item count)

Working:

| Feed | Items | Tier |
|---|---|---|
| techcrunch.com/category/artificial-intelligence/feed/ | 20 | press |
| technologyreview.com/topic/artificial-intelligence/feed | 10 | press |
| arstechnica.com/ai/feed/ | 20 | press |
| theverge.com/rss/ai-artificial-intelligence/index.xml | 10 | press |
| wired.com/feed/tag/ai/latest/rss | 10 | press |
| spectrum.ieee.org/feeds/topic/artificial-intelligence.rss | 30 | press |
| zdnet.com/topic/artificial-intelligence/rss.xml | 20 | press |
| venturebeat.com/category/ai/feed/ | 7 | press |
| feeds.bbci.co.uk/news/technology/rss.xml | 21 | press |
| **incidentdatabase.ai/rss.xml** | 100 | **incident** |
| **artificialintelligenceact.eu/feed/** | 27 | **regulering** |
| export.arxiv.org/rss/cs.AI | 222 | forskning |
| lawfaremedia.org/feeds/articles | 3 | analyse |
| openai.com/news/rss.xml | 1143 | vendor |
| deepmind.google/blog/rss.xml | 100 | vendor |
| simonwillison.net/atom/everything/ | 30 | kommentar |
| importai.substack.com/feed | 20 | kommentar |
| garymarcus.substack.com/feed | 20 | kommentar |
| transformernews.ai/feed | 20 | kommentar |
| dr.dk/nyheder/service/feeds/viden | 20 | dansk |
| version2.dk/rss | 50 | dansk |
| ing.dk/rss | 50 | dansk |
| reddit.com/r/artificial/.rss | 25 | community |
| news.ycombinator.com/rss | 30 | community |

Dead / changed since 2025 — these would have silently broken the old workflow anyway:
- `anthropic.com/rss.xml`, `anthropic.com/news/rss.xml` → **404**, no Anthropic RSS feed exists.
- `hnrss.org/newest?q=...` → **502** (hnrss.org/frontpage works).
- `hai.stanford.edu/rss.xml` → 200 but returns HTML, 0 items.
- `nyheder.tv2.dk/rss`, `euractiv.com/sections/digital/feed/` → 404.
- `openai.com/blog/rss.xml` still 200 but now just redirects to `/news/rss.xml`.

Note: Reddit and Hacker News feeds are included but marked low-credibility; Reddit may 403 from GitHub Actions datacenter IPs, so a feed failure must be non-fatal per-feed and reported, never fatal to the run.

### Architecture of the 2026 version

```
.github/workflows/monthly-verdict.yml   (cron: 1st of month 06:00 UTC + manual dispatch)
  └─ python -m eraifarligt run
       1. collect.py   feedparser over config/sources.yaml
                       -> filter to target month -> dedupe -> cap per source
                       -> Article[] with stable id, tier, real count
       2. score.py     ONE Claude call (claude-opus-5, adaptive thinking)
                       structured output via client.messages.parse(output_format=Pydantic)
                       -> per-dimension score 0-100 + begrundelse + citations (article ids)
       3. verdict.py   DETERMINISTIC in Python:
                       index = weighted mean of dimension scores
                       bedoemmelse = band(index)   Nej / Maaske / Ja
                       delta vs. trailing months
       4. render.py    Jinja2 -> site/index.html, site/arkiv.html,
                       site/maaned/YYYY-MM.html, site/om.html, inline SVG trend chart
       5. writes data/verdicts/YYYY-MM.json, commits it, deploys site/ to Pages
```

### Design rules that fix the 2025 flaws

1. **No `combineByPosition`.** Feeds are concatenated as a flat list, deduped by URL hash and by near-duplicate title (token Jaccard ≥ 0.8).
2. **`kilder` is counted, not asked for.** The JSON stores `antal_artikler`, `antal_kilder`, and the full list of article ids that went into the call. The LLM never reports a count.
3. **No memory.** Every run is a fresh, stateless call. Prior months enter the prompt only as an explicit, visible list of past index values.
4. **Verdict word is computed, not chosen.** Claude scores dimensions; Python maps the weighted index to Ja/Måske/Nej via fixed thresholds in config. Removes the "always Måske" drift and makes the output auditable.
5. **Citations are validated.** Every dimension must cite article ids that exist in the input set; unknown ids are dropped and a dimension with zero valid citations is flagged `ubegrundet` on the page.
6. **Per-month permalinks + archive.** Nothing is overwritten; `index.html` is regenerated from the newest JSON.
7. **Per-feed failure is non-fatal and visible.** Feed errors are recorded in the month's JSON and shown in a "kildestatus" section, so a dead feed is obvious instead of silent.
8. **ASCII JSON keys** (`bedoemmelse`, `raesonnement`, `kilder`) with Danish labels held in config — no more æ/ø encoding damage.
9. **Reproducibility fields** in every JSON: model id, prompt hash, run timestamp, article id list, raw dimension scores.

### Model & cost

`claude-opus-5`, structured output via `client.messages.parse()` with a Pydantic schema, adaptive thinking. One call per month, roughly 25K input / 4K output tokens ≈ **$0.22 per run**, ~$2.70/year.

---

## 2026-08-21 — Session 1, part 3: Build, and one finding that changed the architecture

### Finding: RSS is a stream, not an archive

The first working version was built exactly as planned — a single monthly job.
Then the numbers were checked against reality:

| Target month (probed 21 Aug 2026) | Articles the feeds could still supply |
|---|---|
| **July 2026** (the month a 1-Aug job would assess) | **42**, from 9 of 23 sources |
| **August 2026** (partial, 21 days) | **140** — hit the cap, from 20 of 23 sources |

Most feeds carry only their last 10–20 items, roughly one to two weeks. A job
that first fetches on the 1st of the month sees a thin, systematically skewed
slice: the month's last fortnight only, and only from the slowest-publishing
sources. This is the same defect that produced "7 sources analyzed" in 2025 —
it was never only the broken `Merge` node.

**Architecture changed to two jobs:**

- `harvest` — runs **daily**, fetches every feed, appends new articles to
  `data/raw/YYYY-MM.jsonl` keyed by the article's own publication month.
  No model call, no API key, free.
- `run` — runs **monthly**, selects from the accumulated pool, calls Claude once.
  Falls back to a live fetch if the pool holds fewer than 40 articles, and records
  on the page that it did so.

First real harvest, 21 Aug 2026: 1786 items fetched, 610 new articles pooled
(June 19, July 99, August 492).

### Finding: arXiv cs.AI was 38 % of storage for almost no signal

The arXiv `cs.AI` feed returns ~222 preprints per fetch and churns roughly 100
new items a day. In the first harvest it was 222 of 714 articles and 187 KB of
364 KB. It largely measures publication rate, not danger. **Dropped from
`config/sources.yaml`**, with the reason written into the file. Capability
coverage stays with IEEE Spectrum, Transformer and Import AI.

### Two bugs found and fixed by looking at the rendered page

1. `text-transform: lowercase` on the headline question rendered
   "er ai farligt i juli 2026?" — it lowercased the acronym. Removed.
2. The dimension bars used one gradient scaled to `background-size: 1000%`,
   so every bar rendered green regardless of score. Replaced with a per-score
   band tone (`cfg.bedoem(score).tone`), reusing the same thresholds as the
   overall verdict — so a bar's colour and the headline word can never disagree.
3. The trend chart's last x-axis label was clipped at the right edge
   (`text-anchor="middle"` at the plot boundary). Anchors now turn inward.

### What got built

```
config/sources.yaml        23 feeds, tiers, per-source caps
config/dimensions.yaml     6 weighted dimensions + verdict thresholds
src/eraifarligt/
  config.py                YAML -> dataclasses, bedoem() maps index -> verdict
  collect.py               feed fetch, normalise, dedupe, select
  harvest.py               daily pool, pool -> Collection
  score.py                 ONE claude-opus-5 call, Pydantic structured output
  verdict.py               weighted index, JSON schema v2, load/save
  render.py                Jinja2 + inline SVG trend chart
  cli.py                   harvest / status / run / collect / build / demo
templates/                 base, maaned, arkiv, om
static/style.css           light + dark, no JS, no external assets
.github/workflows/         harvest.yml, verdict.yml, deploy.yml
docs/WORKLOG.md            this file
README.md                  setup and operations
```

Verified working end to end without the model: harvest (23/23 feeds OK),
pool selection, verdict maths, and a full 5-month demo site render.

### Not yet done

- **The live model call has never been executed.** `ANTHROPIC_API_KEY` is not
  set in this shell, so `run` is untested against the real API. Everything up to
  and after the call is tested.
- The repo is not on GitHub yet, Pages is not configured, and the domain still
  points at the old `ai-verdict-site`.
- No unit tests. The deterministic parts (`beregn_indeks`, `bedoem`, dedupe,
  month windows) are the ones worth covering.

### Cost

~25K input / ~4K output tokens per month on `claude-opus-5` ($5/$25 per MTok)
≈ **$0.22 per run**, ≈ $2.70/year. The daily harvest costs nothing.

---

## 2026-08-21 — Session 1, part 4: First real run

`ANTHROPIC_API_KEY` was set with `setx` (Windows user registry). Note for future
sessions: Claude Code's tool shells do **not** inherit it, because Claude Code
started before `setx` ran. Pull it per command with
`export ANTHROPIC_API_KEY=$(powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('ANTHROPIC_API_KEY','User')" | tr -d '\r')`.

### Result — juli 2026

| | |
|---|---|
| Verdict | **Måske** |
| Faresindeks | **53.8** / 100 |
| Grundlag | 41 artikler fra 9 kilder (tynd pulje — kun én dags høst) |
| Tokens | 11 049 ind / 5 087 ud |
| Kostpris | ~$0.18 |
| Prompt-hash | `49d75772362f05f1` |
| Valideringsadvarsler | **ingen** — hver eneste kildehenvisning fandtes i materialet |

Dimensionsscorer: skader 61 · kapabilitet 62 · koncentration 57 ·
regulering 54 · arbejdsmarked 44 · misinformation 41.

### What the output shows about the design

- **Citations held up.** Zero invalid article ids across 29 references. The
  validation layer had nothing to strip, which is the outcome we wanted but not
  the one we could assume.
- **The scores spread.** 41 to 62, not six near-identical numbers. The "always
  Måske" failure of 2025 came from asking the model for the word; asking for
  dimensions and computing the word gives visible internal disagreement even
  when the headline lands in the middle band.
- **Danish sources earned their place.** The most concrete documented harm in the
  month was Sundhedsdatastyrelsen accidentally granting a US AI tool access to
  internal data — from Version2. A 2025-style three-feed setup would never have
  seen it.
- **The `modvaegt` field is doing real work.** The model argued against its own
  verdict on source-credibility grounds: much of the month's drama came from
  named commentators and vendor posts rather than independently verified harm.
  That is exactly the self-criticism the page needs in order to be honest.

### Still open

- Repo is local only. Not pushed, Pages not configured, domain still on
  `ai-verdict-site`.
- July's verdict rests on 41 articles because the pool only has one day of
  harvesting behind it. Once the daily job has run for a full month the figure
  should land near the 140 cap. Worth re-running July with `--overskriv` after
  a few weeks of harvest to see how much the thin pool distorted it.
- No unit tests yet.

---

## 2026-08-21 — Session 1, part 5: The tense problem

Peter spotted it: the page asked "Er AI farligt i juli 2026?" while being read in
August. Worth writing down properly, because it is a design flaw and not a typo.

**The mismatch.** The domain asks a present-tense question. The page answered a
past-tense one.

The first version of this note said the answer could be "up to eight weeks old",
which conflated two different ages and was wrong. Corrected, for July's verdict
read on 31 August — the worst case before September's run:

| What | Age |
|---|---|
| The verdict itself (published 1 Aug) | ~30 days |
| End of the period it describes (31 Jul) | ~31 days |
| Oldest article it cites (28 Jun, incl. `naade_dage: 3`) | ~62 days |

So the *verdict* is at most about a month stale; only the *oldest evidence* in it
reaches two months. Both facts belong on the page, stated separately — saying
"the answer is eight weeks old" overstates the staleness of the answer while
understating the age of the evidence.

**2025 had the identical lag but concealed it.** The old page printed only
"Senest opdateret: 3. august" and never named the period it covered, so it read
as current. Naming the month is the more honest choice — it just makes an
existing problem visible rather than creating a new one.

**Note on the calendar-month unit itself:** it exists because n8n had a monthly
trigger in 2025, not because the question requires it. Nothing in the Python
pipeline depends on it. A rolling 30-day window recomputed weekly would remove
the lag almost entirely and costs about $0.90/month instead of $0.18. Peter chose
to keep monthly and fix the framing — recorded here so the option is on the shelf
rather than forgotten.

### Changes

- **Front page** now asks "Er AI farligt?" in present tense, with
  "Seneste hele måned: **juli 2026**" underneath and
  "Næste vurdering: 1. september 2026" in the footer of the verdict card.
- **Archive pages** keep "Er AI farligt i juli 2026?" — retrospective framing is
  correct there, since those pages *are* historical.
- **`om.html`** states the lag outright in the caveats list, and distinguishes
  the two ages: the verdict is about a month old at worst, while the oldest
  events behind it may be two months old.
- New `naeste_vurdering()` helper in `render.py`: a month's verdict publishes on
  the 1st of the following month, so the *next* verdict falls two months after
  the month displayed.

Note the current page shows "opgjort 21. august" for July only because the test
run happened mid-month. Under the cron it will read "opgjort 1. august".

---

## 2026-08-21 — Session 1, part 6: Correction — the site is on Netlify, not GitHub Pages

Discovered while preparing to deploy. `curl -sI https://eraifarligt.dk` returns:

```
Server: Netlify
Cache-Status: "Netlify Edge"
```

and the GitHub Pages API for `ai-verdict-site` reports `"cname": null` — no custom
domain is configured there at all. DNS points at Netlify's edge
(`35.157.26.135`, `63.176.8.218` and two IPv6 addresses).

**So the 2025 chain was:** n8n → GitHub node writes `index.html` to
`peterbrandgardmadsen/ai-verdict-site` → **Netlify** builds from that repo →
served at eraifarligt.dk. GitHub Pages was also enabled on the repo but was never
the thing serving the domain.

This also explains an inconsistency noted in part 1 and left unresolved: the live
site showed an **August 2025** verdict while the newest file in the GitHub repo
was dated **31 July**. Different pipelines, different states.

Earlier entries in this log and the README asserted GitHub Pages. That was an
assumption from seeing the n8n GitHub node, never verified. Both corrected.

### Deployment shape, decided

| Where | Cadence | Does |
|---|---|---|
| `harvest.yml` | daily 05:17 UTC | fetches feeds, commits `data/raw` |
| `verdict.yml` | 1st, 06:00 UTC | scores the month, commits `data/verdicts` |
| Netlify (`netlify.toml`) | every push to `main` | builds `site/`, publishes |

The split matters: **GitHub Actions never publishes, and Netlify never calls
Anthropic.** Actions commits data; Netlify reacts to the commit and only ever
reads `data/verdicts/`. The API key therefore lives in exactly one place —
GitHub Actions secrets — and nothing at Netlify can leak it.

Chosen over moving to GitHub Pages because the domain and its certificate stay
untouched: no DNS edit, no propagation wait, no window where the site is down or
serving an untrusted certificate.

### Changes

- Deleted `.github/workflows/deploy.yml` — Netlify owns publishing now.
- Stripped the `configure-pages` / `upload-pages-artifact` / `deploy-pages` steps
  and the `pages` / `id-token` permissions from `verdict.yml`; it now runs
  `run --spring-build-over`, since building is Netlify's job.
- `render.py` no longer writes `CNAME` or `.nojekyll` — both are GitHub Pages
  artefacts.
- Added `netlify.toml`: build command, `publish = "site"`, `PYTHON_VERSION 3.12`,
  plus `nosniff` / `Referrer-Policy` headers and a week of cache on `/static/*`.

**Risk to watch on the first Netlify build:** the build image must provide Python
3.12 and install five packages. If `PYTHON_VERSION` misbehaves, the fallback is to
have `verdict.yml` build `site/` and commit it, leaving Netlify with an empty
build command and `publish = "site"`. Nothing else would need to change.

---

## 2026-08-21 — Session 1, part 7: Live

eraifarligt.dk now serves the 2026 pipeline. The August 2025 page, frozen for
almost a year, is gone.

### Deployed

- Repo: **github.com/peterbrandgardmadsen/eraifarligt-dk** (public).
- `ANTHROPIC_API_KEY` added as a GitHub Actions secret by Peter. It exists in
  exactly one place; Netlify never sees it.
- Netlify site repointed from `ai-verdict-site` to the new repo. Build succeeded
  on the first attempt — `PYTHON_VERSION = "3.12"` worked, so the fallback of
  committing a prebuilt `site/` was not needed.
- Domain and certificate untouched, as intended. No downtime.

Verified live: `/`, `/arkiv.html`, `/om.html`, `/maaned/2026-07.html` and
`/static/style.css` all return 200; an unknown path returns 404; no occurrence of
"n8n" remains in the served HTML.

Front page reads: **Er AI farligt? → Måske**, seneste hele måned juli 2026,
faresindeks 53.8, næste vurdering 1. september 2026.

### CI proven, not assumed

`harvest.yml` was dispatched manually and ran green: 1746 items from 23 feeds,
7 new articles pooled, committed as `Høst 2026-08-21` and pushed. So the daily
job, the commit step and the push permissions are all confirmed working rather
than merely written.

### Finding: Substack blocks GitHub's runners

Import AI and Gary Marcus both returned **HTTP 403** from the Actions runner.
Both fetch fine from Peter's home connection. Substack blocks datacenter IP
ranges. Reddit — the source predicted to fail this way — worked fine.

Consequences: two of 23 sources, both lowest-weight `kommentar` tier, will
contribute nothing to any CI-run verdict. The failure is non-fatal by design,
logged in the run and printed in the month's kildestatus table, so it degrades
visibly rather than silently. **Left in place pending Peter's decision** — the
options are to drop them, or to accept that they only contribute when a verdict
is run from a workstation.

### Next scheduled event

**1 September 2026, 06:00 UTC.** `verdict.yml` fires with no `--maaned`, so
`forrige_maaned()` resolves to `2026-08`, scored from a pool that by then will
hold a full month of daily harvests rather than July's 41 articles. Both
workflows share the `data-skrivning` concurrency group, so the 05:17 harvest and
the 06:00 verdict queue instead of racing.

### Still open

- Substack 403 decision.
- No unit tests. `beregn_indeks`, `bedoem`, the dedupe threshold and
  `month_window` are the parts worth covering.
- Worth re-running July with `--overskriv` once the pool is deep, to see how much
  the 41-article basis skewed the first number.
