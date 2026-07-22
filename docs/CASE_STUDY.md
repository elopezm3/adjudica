# Adjudica — engagement write-up

How a tender-qualification system was scoped, verified, and built; what the data turned
out to be; and what I chose not to build. Written as an engagement report rather than a
feature list, because the interesting content is the decisions, not the code.

---

## 1. The brief

A company that sells to the Spanish public sector — say a regional cleaning contractor —
faces the same problem every week. Hundreds of tenders are published; they can afford to
write a handful of serious bids. Each bid costs days of expensive work. So the recurring
question is:

> *Of everything published, which few should we bid on — can we even legally qualify, and
> is it winnable at a margin worth having?*

Commercial tender-finding software exists, which is the useful signal that this is a real,
paid-for workflow rather than an invented one.

The deliverable is an agent that answers that question for a specific company, **plus
evidence that its answers are any good.** The second half is the harder and more valuable
half, and it drove every architectural decision below.

## 2. Discovery: how a bid decision actually gets made

Talking through the workflow, the decision decomposes into three layers that want very
different implementations:

| Layer | Question | Nature |
|---|---|---|
| 1 — Relevance | Is this our line of work? | Lookup (CPV family) |
| 2 — Eligibility | Can we *legally* bid? | Arithmetic + set membership. Pass/fail. |
| 3 — Judgment | Can we realistically *win*, at a margin? | Reasoning over history |

Layer 2 is the one people assume needs AI and doesn't. "Is our €900k turnover above the
€6M solvency floor?" is a comparison, not a judgment. Building it as deterministic code
made it fully testable and left the model free for Layer 3, where reasoning actually earns
its keep. The split is visible in the codebase: `qualify/eligibility.py` contains no LLM
call at all.

## 3. What I verified before building — and what was wrong

The scoping research produced a plausible plan. Most of its specifics turned out to be
wrong, and each correction changed the design. This section is the core of the engagement.

**The API field names were wrong.** The linkage key is `procedure-identifier`, not
`cbc:ContractFolderID` — the latter is the raw-XML name and isn't a valid API field. The
outcome fields were similarly misnamed. Cost of not checking: a data layer built on fields
that return nothing.

**Pagination took five probes.** Four reasonable guesses at the cursor parameter all
returned HTTP 400. The correct name is symmetric with the response field
(`iterationNextToken`). Undocumented, and unguessable.

**The backtest window is bounded on *both* ends — the opposite of the assumption.** The
plan said "draw backtest data from 2024 or earlier" so awards would exist. Sampling the
live API showed `procedure-identifier` is populated in 0/10 notices from 2023-H2 and
2024-H1, but 10/10 from 2024-H2: the EU eForms migration. So two forces pull in opposite
directions — award lag wants *old* tenders, structured linkage wants *new* ones — and the
usable window is their intersection, from 2024-H2 onward. Reaching further back yields
notices with no machine-readable linkage at all.

**"No winner name" does not mean the contract went unawarded.** I found award notices
marked `selec-w` (winner selected) with an empty winner field. Had I inferred *desierto*
from a missing name, the negative class of the entire outcome eval would have been
silently poisoned. The reliable signal is `winner-selection-status`, and only that.

**The document path in the plan was a dead end.** TED exposes `document-url-lot`, which
sounded like a link to the tender's specification documents. It returns *portal landing
pages* — including, in one case, a portal homepage. Fetching them would mean crawling a
site whose `robots.txt` is `Disallow: /`. The real path is PLACSP's ATOM syndication feed,
where each entry's CODICE XML carries direct document links **and** structured fields.

That last discovery improved the architecture rather than damaging it: because ground
truth and the messy PDF come from the *same feed entry*, the extraction eval needs no
cross-matching between sources. TED remains the source for award outcomes, where it's
genuinely the only option.

**Rate limiting is real, and my error handling was wrong.** A backfill loop earned an HTTP
429. My client treated all 4xx as fatal — correct for a malformed request, wrong for "slow
down." 429 is now retried with backoff honoring `Retry-After`, plus proactive throttling.
The same incident showed the per-procedure fan-out wouldn't scale (one call per procedure
≈ tens of thousands of calls), so it was replaced with windowed bulk pulls joined locally:
~240 calls per year of data instead.

## 4. What I built

- **Data spine** — TED ingester (structured notices, award outcomes) and PLACSP ingester
  (live opportunities + pliego documents), both into one DuckDB file. Separate tables
  because they answer different questions: PLACSP is *what's open*, TED is *what happened*.
- **Tender→award resolver** — links a tender to its outcome by shared procedure UUID,
  producing the answer key the outcome eval grades against.
- **Extraction** — pliego PDF → structured fields via Claude.
- **Qualification** — company profile + the four hard eligibility rules.
- **MCP server** — the product surface. Four tools over the data; the user connects it to
  Claude Desktop and asks in plain language.
- **Two eval harnesses** — one per claim the system makes.

## 5. What I deliberately did not build

Naming the non-goals is part of the work.

| Not built | Why |
|---|---|
| An OCR pipeline | Claude reads PDFs natively, scanned ones included. A Tesseract stage would have been a week of work solving a problem that no longer exists. |
| A vector database | Nothing here needs semantic similarity search. Tenders are filtered by CPV code and budget — exact, structured predicates that a database answers correctly and a vector index answers approximately. |
| Fine-tuning | The task is extraction against a schema; a prompt does it. Fine-tuning would add a training loop, a dataset, and a versioning problem for no measurable gain. |
| A web frontend | The interface is Claude Desktop over MCP. A React dashboard would be the least interesting part of the system and would duplicate a client that already exists. |
| `.docx` / legacy `.doc` conversion | Real and needed eventually; deferred deliberately, with the extractor sniffing magic bytes and refusing non-PDFs loudly rather than silently mis-handling them. |

## 6. How I know it works

Every claim the system makes has a harness that can falsify it, and each was built
*before* the thing it measures.

**Extraction eval.** Each tender is published twice — as structured XML and as a human
PDF. The extractor reads the PDF; the XML grades it, field by field, at zero labeling
cost. Verdicts are `MATCH` / `MISMATCH` / `NO_GROUND_TRUTH`, and the third is never scored
as correct. Counting an ungradable field as a win is the easiest way to manufacture a
flattering accuracy number, so the harness refuses to.

**Outcome backtest.** Predicts awarded vs *desierto*, graded against award notices. Every
report prints the **majority baseline** beside the accuracy. Outcomes are roughly 90/10
imbalanced, so a predictor that always says "awarded" scores 90% while never identifying a
single *desierto* — and the report makes that visible rather than lettable-slide.

**One idea, applied four times.** The recurring design move is refusing to collapse "we
don't know" into a confident answer:

| Where | The distinction held |
|---|---|
| Award outcomes | `desierto` (closed, no winner) ≠ `unknown` (not awarded yet) |
| Extraction grading | `NO_GROUND_TRUTH` ≠ correct |
| Eligibility | `UNVERIFIED` (tender data missing) ≠ `NOT_APPLICABLE` (rule not configured) |
| Backtest | Unresolved procedures excluded, not counted as negatives |

The eligibility case was found by a failing test: my first version conflated the last two,
so a company that hadn't set a contract ceiling could never be judged eligible, because an
unused rule read as "unverified" forever.

The user-visible payoff: running the qualification tools against 179 real tenders returns
`UNKNOWN` with *"confirm by hand: no turnover requirement found in the pliego"* — not a
confident "eligible." The system names what it couldn't check. For a customer deciding
whether to spend three days on a bid, a false "you qualify" is the expensive failure.

## 7. Honest limitations

- **No live extraction accuracy figures yet.** The harness, extractor, and document
  pipeline are built and verified; the batch run needs API billing. Until it runs, the
  extraction accuracy table is a shape, not a result.
- **179 tenders** is one page of the PLACSP feed, not the corpus.
- **Spain only.** The design generalizes across EU member states, but only Spain is wired.
- **No persisted company profile** — it's re-described per call.
- **Requirement fields have no automated answer key.** Solvency thresholds and
  certifications exist only in PDF prose. They're extracted but not auto-graded; a
  hand-labeled sample is the honest next step, and its absence is stated rather than
  hidden.
- **The feed is a snapshot.** Incremental refresh exists; scheduling it does not.

## 8. What I'd do next

1. Run the extraction eval and publish the real per-field numbers, including failures.
2. Hand-label ~50 pliegos for the requirement fields, so Layer 2 can be graded too.
3. Build the Layer 3 judgment agent — incumbency and price-weight reasoning over the award
   history — and grade it with the backtest harness that already exists.
4. `.docx` conversion, to stop discarding a real slice of the corpus.
