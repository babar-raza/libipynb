# Test Fixture Provenance

## valid/

| Fixture | Origin | License |
|---------|--------|---------|
| `minimal.ipynb` | Hand-crafted, Format Factory donor | Apache-2.0 |
| `code-and-markdown.ipynb` | Hand-crafted, Format Factory donor | Apache-2.0 |
| `with-outputs.ipynb` | Hand-crafted, Format Factory donor | Apache-2.0 |
| `empty-notebook.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `nbformat-4-{0..4}.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `rich-mime-outputs.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `with-attachments.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `r-kernel.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `with-error-output.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `with-widgets.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `large-source-cell.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `unicode-content.ipynb` | Synthetic (libipynb project) | Apache-2.0 |

## invalid/

| Fixture | Origin | License |
|---------|--------|---------|
| `missing-nbformat.ipynb` | Hand-crafted, Format Factory donor | Apache-2.0 |
| `missing-cells.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `wrong-nbformat-version.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `null-cells.ipynb` | Synthetic (libipynb project) | Apache-2.0 |

## adversarial/

| Fixture | Origin | License |
|---------|--------|---------|
| `deeply-nested-metadata.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `huge-base64-output.ipynb` | Synthetic (libipynb project) | Apache-2.0 |
| `truncated-json.ipynb` | Synthetic (libipynb project) | Apache-2.0 |

## corpus/

| Fixture | Origin | License |
|---------|--------|---------|
| `spec-v45-complete.ipynb` | Synthetic, follows nbformat 4.5 spec | Apache-2.0 |
| `data-science-pattern.ipynb` | Synthetic, typical data science layout | Apache-2.0 |
| `multi-output-types.ipynb` | Synthetic, multiple output types | Apache-2.0 |

## Real-world fixtures (LIBIPYNB-Q13c) -- process and criteria

Every fixture above is either hand-crafted for this project or synthetically
generated to exercise one specific structural case. None was ever sampled
from a genuine, "in the wild" notebook authored outside this project --
the forensic audit (`plans/forensic-capability-audit-2026-08-18.md` §7,
§13) flagged this as a real gap: synthetic fixtures cannot surprise this
project's own author's assumptions about what real notebooks look like the
way an unrelated third party's notebook can.

This section records the selection criteria for closing that gap so a
future session (or the maintainer, Babar Raza) can add 2-4 real-world
fixtures without re-deriving the bar from scratch. Selecting and vetting the
actual notebooks is **out of scope for this taskcard** -- it requires
fetching real external content and verifying its license firsthand, which
is a judgment call with provenance consequences that should not be made
unilaterally inside an unrelated, unattended implementation pass (the same
reasoning `plans/production-hardening-plan.md`'s LIBIPYNB-Q12a card applies
to the internal-URL decision: don't guess at something that needs a human,
evidenced decision).

**Criteria for a qualifying real-world fixture:**

1. **Permissively licensed**, explicitly and verifiably -- MIT, BSD-2/3-Clause,
   Apache-2.0, or CC-BY (with attribution recorded below). A repository with
   no license file, or one that only grants viewing rights, does not qualify
   regardless of how useful the notebook looks.
2. **Genuinely authored for a real purpose** outside this project -- a
   tutorial, a published analysis, an example notebook shipped by another
   real open-source project (e.g. a well-known library's own `examples/`
   directory) -- not another synthetic fixture relabeled as "real-world."
3. **Small enough to vendor** (roughly under a few hundred KB) so it can be
   committed directly rather than fetched at test time (this project vendors
   every fixture; none are downloaded during a test run).
4. **Recorded here** with: the exact source URL, the license under which it
   was obtained, the retrieval date, and a one-line note on what structural
   pattern it was chosen to exercise (e.g. "real multi-kernel outputs,"
   "real large-scale metadata from an actual ML training notebook").
5. **Never modified post-fetch** beyond what's strictly necessary to keep it
   loadable (e.g. stripping a genuinely broken field would defeat the point
   of using real-world content) -- if a fixture needs edits to be useful, a
   synthetic fixture already serves that purpose better.

Until fixtures meeting this bar are added, `tests/fixtures/` remains
entirely synthetic/hand-crafted -- an honestly-disclosed limitation, not a
silently-assumed completeness the audit's own Anti-Overclaim discipline
warns against.

### Repeatable sourcing process (LIBIPYNB-Q2 production-design session)

Selection is still, and always will be, a maintainer decision (see above) --
what changed in this session is that the process for proposing, approving,
fetching, and vendoring a candidate is now a repeatable, tool-assisted loop
instead of a one-off manual question. The tool is `scripts/fetch_fixture.py`
(stdlib-only, never wired into CI, never runs unattended):

1. A future session researches candidates against the 5 criteria above and
   appends one row per candidate to the **Candidate shortlist** table below
   -- every column pre-filled except `Decision`/`Note/date`, so the
   maintainer's job is a skim-and-check, not research.
2. The maintainer marks each row's `Decision` column `Approve`,
   `Approve-with-substitution: <url>`, or `Reject`, with a dated note.
3. `python scripts/fetch_fixture.py --url <candidate-url> ... --dry-run`
   (the default mode) fetches the content, prints exactly what would be
   written (fixture path, hash, size, the `Vendored real-world fixtures`
   row), and writes nothing. `--dry-run` also stages the fetched bytes and
   their hash to a local, gitignored lockfile.
4. Only `--commit` actually vendors anything -- and only after two
   structural checks, not just human diligence: (a) the exact `--url` must
   match an `Approve`d row in the shortlist below, refused otherwise; (b)
   the content re-fetched at commit time must hash-match the staged dry-run
   copy, refused otherwise (a content-changed-since-review guard). See the
   tool's own `--help` and `tests/scripts/test_fetch_fixture.py` for the
   full behavior.
5. To retract a previously-vendored fixture (e.g. a license determination
   later found to be wrong), see "Retracted fixtures" below -- this is a
   deliberately manual, undocumented-in-tooling procedure, not automated,
   since it should be rare and each instance needs its own recorded reason.

### Candidate shortlist pending maintainer decision

| # | Candidate notebook | Source repo & pinned commit/tag URL | Declared license (+ LICENSE path at that pin) | Size | Structural pattern exercised | Criteria 1-5 self-check | Decision | Note/date |
|---|---|---|---|---|---|---|---|---|

*(Empty until a future session researches and proposes candidates. See "Repeatable sourcing process" above.)*

### Vendored real-world fixtures

| Filename | Category | Source URL (pinned) | License | Retrieval date | SHA-256 | Size (bytes) | Structural pattern |
|---|---|---|---|---|---|---|---|

*(Empty until the maintainer approves a shortlist candidate and `scripts/fetch_fixture.py --commit` vendors it.)*

### Retracted fixtures

| Filename | Category | Retraction date | Reason |
|---|---|---|---|

*(Empty -- expected to stay that way except in the rare case a vendored fixture's provenance is later found faulty. Retraction procedure: (1) move the row from "Vendored real-world fixtures" here, recording the date and reason -- never silently delete it, the historical record matters; (2) delete the vendored file; (3) remove its entry from `REAL_WORLD_HASHES` in `tests/integration/test_obligation_corpus_integrity.py` and any oracle-test parametrization; (4) this requires the same dated maintainer authority as adding a fixture -- see `.supervisor/project-adapter.yaml`'s `source_external_fixture_content` gated action.)*
