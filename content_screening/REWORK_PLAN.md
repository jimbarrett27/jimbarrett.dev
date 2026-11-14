# Literature monitoring rework + reMarkable reading loop — plan

Status: **planning, 2026-11-14.** Two related pieces of work:

1. **Rework literature monitoring** for a new field (financial crime / fraud prevention,
   GenAI data science) with much lower volume, a rubric-based score, and the PV era
   archived but kept as labelled data.
2. **A reMarkable reading loop over Google Drive:** kept papers go to Drive for the
   tablet, annotated papers come back and their highlights and margin notes are
   written into the paper's Obsidian stub. Handwritten notebooks move to the same
   Drive transport.

Triage itself stays where it is: the web UI on laptop/phone. The tablet is for
**reading only**.

Sources and topics for the new field are being researched separately; section 1.2
has a placeholder for them.

---

## 0. Where things stand

### Pipeline today

Daily `run_full_scan` (from `main.py`): arXiv RSS (11 categories), 16 journal RSS
feeds, OpenAlex (PV topics, citers of UMC first/last-author works). Cross-source
dedup → LLM screen (`screen_article.jinja2`, deepseek flash) → embedding
(gemini-embedding-2, 3072-d) → `pending` (relevant) or `auto_rejected`. Triage UI
`keep` → Zotero + Obsidian stub; `dismiss` → nothing.

### Live DB snapshot (2026-11-14)

| | |
|---|---|
| Ingested (2026-06-02 → today) | 14,551, all screened, 14,536 embedded |
| `auto_rejected` | 11,741 |
| Triage decisions | 462, **all June 2026** |
| `kept` / `dismissed` | 37 / 425 (8% keep rate) |
| `pending` | 2,348 |
| Keep rate by `suggested_depth` | deep 10%, skim 7%, file 8% (no signal) |

Triage stopped in June: too much volume, plus the interview process and notice
period. Access is now easier (Caddy on the tailnet rather than the Cloudflare
tunnel). **The goal is low volume, so triage is sustainable.**

### PV-specific knobs (all to be replaced by one profile)

- `prompts/screen_article.jinja2`: UMC, LAREB, ICSRs, PV interests
- `constants.py`: `PV_KEYWORDS`, `INTERESTING_ARXIV_CATEGORIES`
- `data/discovery.yaml`: PV OpenAlex topics, UMC institution seed
- `data/feeds.yaml`: mostly medical informatics journals

---

## 1. Literature monitoring rework

### 1.1 Interest profiles

One file per field, e.g. `content_screening/profiles/fincrime.yaml`, holding
everything that defines "interesting":

```yaml
name: fincrime              # stored on every article (see 1.4)
description: |              # prose interest description, injected into the prompt
  ...
keywords: [...]             # broad recall net (replaces PV_KEYWORDS)
arxiv_categories: [...]
feeds: [...]                # replaces data/feeds.yaml
openalex:                   # replaces data/discovery.yaml
  topics: [...]
  monitored_authors: [...]
  seed_papers: [...]
  institutions: [...]
rubric: [...]               # see 1.3
intake:                     # see 1.5
  threshold: ...
  daily_cap: 10
```

- The active profile is selected by config/env (default: the newest one). Only one
  profile is active at a time.
- `screen_article.jinja2` becomes generic and is filled in from the profile.
- The existing PV settings become `profiles/pv.yaml`. That documents what the PV
  era used and keeps a way back.
- The OpenAlex contact address stays outside the profile, as it is now.

### 1.2 Sources and topics — PLACEHOLDER

To be filled in from the separate research into financial crime / fraud / GenAI
sources: arXiv categories (likely q-fin.*, cs.CL, cs.LG, cs.CR), journals and RSS,
OpenAlex topics, authors and groups worth following, blogs and newsletters (would a
new `SourceType` be needed?).

Aim: **narrower discovery**, so fewer papers are screened in the first place. That
cuts cost as well as queue size.

### 1.3 Rubric scoring

LLMs are poor at producing calibrated scores directly. Instead:

- The profile defines **6–10 statements**, each with a weight. Examples:
  - "The paper is about fraud, AML or financial crime" (+)
  - "Generative AI / LLMs are central to the method" (+)
  - "It proposes a new method rather than applying an existing one" (+)
  - "It evaluates on realistic or large-scale data" (+)
  - "Its techniques could transfer to a GenAI data science team in fraud" (+)
  - "It is mainly a survey or position paper" (−)
- For each statement the LLM writes a **one-line justification first**, then answers
  on a 5-point scale: strongly disagree … strongly agree, mapped to −2…+2. There is
  also a **"can't tell"** option, which counts as 0 rather than a forced guess
  (title-only papers).
- **The raw per-statement answers are stored** in a new JSON column
  (`rubric_answers`). **The score is computed in code** (weighted sum) and stored in
  `llm_interest_score`.
  - Weights can be retuned, or fitted to triage decisions later (logistic
    regression), **without re-running the LLM**.
  - The answers are clear features for a future model, next to the embeddings.
- Metadata signals (monitored author, cites a seed paper, venue) are added to the
  score directly in code, not asked of the LLM.
- `llm_reasoning` stays as a short summary for the triage card. It could be
  generated, or built from the justifications behind the strongest answers.
- **Drop `suggested_depth`**: the column stays for history, but nothing new is
  written to it, and the triage card stops showing it.

### 1.4 Profile column and the PV archive

One Alembic migration:

- Add `articles.profile` (text). **Backfill `'pv'` on all existing rows.** Every new
  row gets the active profile's name. Training can then filter by profile or use it
  as a feature, so the two fields aren't mixed by accident.
- Add `articles.rubric_answers` (JSON, nullable; null for PV rows).
- Move the 2,348 PV `pending` rows to **`archived`**. The 462 `kept`/`dismissed`
  decisions and all embeddings stay as they are.

### 1.5 Intake control (no expiry)

Every paper that enters `pending` stays there until it is triaged. **There is no
automatic expiry.** Volume is kept down at intake:

1. **Narrower discovery** (1.2).
2. **Score threshold + daily cap:** after a scan, relevant papers are ranked by
   score. Only those above `intake.threshold` and within the top `intake.daily_cap`
   become `pending`.
3. Papers that pass screening but miss the cut get **`below_cut`**. They are kept
   with their answers and embeddings, out of the queue, and could be promoted later.

If the queue still builds up, clear it by hand or add a bulk-archive action
later. Not built now.

The triage UI only shows `pending`, so the new statuses (`archived`, `below_cut`)
need no frontend change beyond defensive handling of unknown statuses.
`count_pending_triage` is unchanged.

### 1.6 Cleanup

- Remove the dead Telegram rating flow in `screening_bot.py` (ratings, pending
  notifications) and its DB helpers. The tables can stay.
- Remove the Cloudflare Access guard in `triage/app.py` (`make_access_guard`,
  `TRIAGE_REQUIRE_CF_ACCESS`). Caddy only serves the tailnet now, and the setting
  is already `false`.

### 1.7 Later, not now

A small supervised ranker on embeddings + rubric answers, trained on `fincrime`
decisions (and maybe PV decisions as a weak prior). Worth revisiting once there are
a few hundred new-field decisions.

---

## 2. reMarkable reading loop over Drive

### 2.1 Transport — tested 2026-11-14

Groundwork: `gcp_util/drive.py` (PR #238). OAuth refresh token for the photos
account (full `drive` scope) is in Secret Manager as `DRIVE_OAUTH_TOKEN`. The
tablet's Drive integration uses the same account. The folders already exist:

```
reMarkable/
  Notes/              ← you export notebooks here      → notebook pipeline
  Papers/
    To read/          ← server uploads kept papers here
    Annotated/        ← you export read papers here    → annotation pipeline
  Done/               ← server moves processed exports here
```

What the tests showed (samples kept in `/home/jim/data/remarkable_test/`):

- **The Drive export and the email PDF of the same document are byte-identical**
  (same SHA-256). Drive is the main path; email is no longer needed.
- **Export lets you choose the folder**, so the folder chooses the pipeline.
- The tablet names documents after the uploaded filename. The export is
  `<name>.pdf`, with ` (1)`, ` (2)` … added on name clashes.
- "Current page" exports produce single-page PDFs; the pipeline must cope with them.

**Annotated paper format:**

- The original page content is **unchanged** (same text layer and word counts).
  Your strokes are **appended after the original's drawings**: black filled
  outlines, one per stroke.
- **Highlights** are separate filled shapes in their own colour (seen: pink
  `(0.95, 0.62, 1.0)`, orange `(1.0, 0.76, 0.55)`), drawn with a blend graphics
  state (MuPDF warns about a missing `ExtGState`, but renders correctly).
  `page.get_textbox(highlight_rect)` returns the exact highlighted passage.
- **Writing past the page edge widens the page** (seen: page extended 31pt left,
  another 18pt right). The mediabox origin moves, so allow for that.
- **Inserted blank pages** are notebook-size (445×594pt) with no text layer and
  only strokes. **Every later page shifts by one**, so map exported pages to
  original pages by **text**, not by index.

**Notebook format:**

- A vector PDF (producer PDFium), 445×594pt per page.
- Pen strokes are real stroked paths with a width (seen: 1.27pt black; one grey
  diagram path).
- The dot-grid template is ~1,500 tiny dot shapes, easy to drop by size, so only
  the ink is rendered.

### 2.2 Drive watcher

One job on the bot's job queue (like the daily scan), every 1–2 minutes:

- List `reMarkable/Notes` and `reMarkable/Papers/Annotated`.
- For each file: download it, dispatch it by folder, and **on success move it to
  `reMarkable/Done/`**. On failure, leave it in place and retry with a cap. Record
  attempts by Drive file ID (a small table or state file under `util.paths`).
- Telegram notifications, as the email ingest does now: a message per processed
  file with a link to the note it produced, and a message on a final failure.

### 2.3 Outbound: kept paper → tablet

A new routing target alongside Zotero and Obsidian in `triage/routing.py`
(idempotent, retried like the others):

- **Find a PDF:**
  - arXiv: `https://arxiv.org/pdf/<id>`.
  - OpenAlex / RSS: `best_oa_location.pdf_url`. Store it in `metadata` at
    ingest from now on. For older rows, look it up from OpenAlex by DOI when the
    paper is kept.
- **Upload** to `reMarkable/Papers/To read/` as `<article id> - <short title>.pdf`.
  The leading ID is how an export is matched back to its paper.
- Keep **the uploaded original** locally (e.g.
  `data_path("papers/<id>.pdf")`). The annotation pipeline compares against it.
- **No open-access PDF** (paywalled): record it on the row and say so in the
  Obsidian stub ("no open-access PDF; add one by hand"). If you upload a PDF to the
  folder by hand with the `<id> - ` prefix, the return path works the same.
- New columns: `drive_file_id`, `drive_error` (same pattern as `zotero_key` /
  `zotero_error`).

### 2.4 Annotation pipeline (`Papers/Annotated`)

Input: an exported PDF. Match it to its paper by the leading ID in the filename,
then load the original from local storage.

1. **Map pages.** Match each exported page to an original page by text-layer
   equality. Pages with no text layer are **inserted pages**.
2. **Separate the ink.** On each matched page, the drawings beyond the original
   page's drawing count are annotations. Exact, no image work.
3. **Classify strokes.** By colour: highlight vs pen. Highlights get their colour
   recorded (it might carry meaning later).
4. **Group** pen strokes into annotations by proximity (e.g. dilate stroke bboxes and
   merge overlaps), so one margin note or one circled passage = one group.
5. **Anchor** each group to the original's word boxes:
   - highlight → the words under it (exact text)
   - circle / loop → the words enclosed
   - underline → the words just above
   - margin note → the nearest line(s) / paragraph by vertical position
   - figure-adjacent → the figure's caption
6. **Transcribe** handwriting only: crop each pen group (rendered from the vectors,
   ink only) and send it to **Sonnet 5.5 via OpenRouter** with the anchored passage
   as context ("this note was written beside: …"). Pure marks (a loop, a
   star) are labelled, not transcribed. Batch all of a paper's crops into one call
   if quality holds; otherwise one small call per group.
7. **Inserted pages** → the notebook pipeline (2.5), with the output put into the
   same paper note under a "Notes pages" heading.
8. **Write to Obsidian** under the stub's `## Notes`, in page order:

   ```markdown
   **p.4**
   > "we threshold the anomaly score at the 99th percentile…"
   Why not calibrate per merchant?
   ```

   Highlights are quotes with no comment. The crop image can be embedded as a
   fallback for checking. Frontmatter `status: unread` → `read`.
   Re-exporting the same paper **replaces** the generated section. It doesn't
   append a second copy.

Test fixture: the 2026-11-14 export (`/home/jim/data/remarkable_test/drive2/export3.pdf`
vs `original/…pdf`) has a circled passage + "CREMLS?" (p2), a symbol (p3),
"dot product?" beside an equation (p5), a rotated margin note + bracket (p6),
"Amazing!" beside a figure (p8), pink and orange highlights, and an inserted page.
Copy a trimmed version into `tests/` for unit tests of steps 1–5.

### 2.5 Notebooks over Drive (`Notes`)

- Render each notebook page from the PDF **without the dot-grid template** (drop
  tiny shapes, or redraw only the ink paths) into the `PageImage`s that
  `handwritten_notes.handwritten_bot.transcribe_and_file` already accepts. Skip
  blank pages.
- Everything after that is unchanged: transcript, figure redraws, vault note,
  routing buttons in Telegram.
- Keep the email ingest (`handwritten_notes/remarkable.py`) as a fallback until
  Drive has run reliably for a while, then remove it. That also removes the
  email-spoofing checks, which Drive doesn't need: only your account can write
  there.
- Possible later addition: subfolders of `Notes/` as routing targets (e.g.
  `Notes/Diary`), chosen at export time instead of by button.

---

## 3. Order of work

1. **Merge PR #238** (Drive helper).
2. **Migration + profile plumbing** (1.4, 1.1 with `profiles/pv.yaml`), plus cleanup
   (1.6). No behaviour change yet.
3. **Rubric scoring + intake control** (1.3, 1.5), tested against the `pv` profile
   on a replay of recent papers.
4. **Fincrime profile** (1.2) once the source research is in. Switch it on.
5. **Drive watcher + notebook pipeline** (2.2, 2.5). This is the smallest end-to-end
   win and proves the watcher.
6. **Outbound upload** (2.3).
7. **Annotation pipeline** (2.4).

Steps 2–4 and 5–7 are independent tracks; they share only the Obsidian stub.

## 4. Open questions

- The rubric statements and weights for fincrime (draft with the source research).
- `intake.daily_cap` and `threshold`: start at 10/day and a threshold picked from
  the score distribution of a replay.
- Do highlight colours mean anything to you (e.g. pink = key result, orange =
  disagree)? If so, the pipeline can label them.
- A personal marking scheme (`?` = open question, star = key point) that the
  pipeline turns into a `## Questions` list or tags? Only worth it if you'd use it
  consistently.
- Cost: annotation transcription is a handful of small Sonnet 5.5 calls per paper
  read, which seems fine, but worth checking after the first few papers.
