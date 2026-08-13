# Validation Notes

This document is the evidence trail behind the governance scores — the
step most portfolio projects skip. Every claim below is reproducible by
re-running `batch_score.py` or hitting the `/score` endpoint directly.

## 1. Corpus

68 real, publicly available n8n workflow templates, sampled across 20
categories (AI/RAG, Telegram, Slack, Discord, Gmail, Airtable, Notion,
databases, PDF processing, WhatsApp, and more) from the
`enescingoz/awesome-n8n-templates` public GitHub repository (334 total
templates available; 68 sampled for diversity across categories, capped
at 4 per category). No synthetic or hand-authored workflows were used in
the scored corpus — the two hand-authored files (`test_risky_workflow.json`,
`test_hardened_workflow.json`) exist only as the deliberate before/after
proof pair described below, and are excluded from the corpus statistics.

## 2. Bug found and fixed during validation

**Issue:** Initial run flagged 5–11 "hardcoded secrets" in the riskiest
workflows — implausibly high for public templates, which typically don't
ship real API keys.

**Root cause:** The secret-detection regex matched any string 32+
characters of alphanumeric/hyphen characters. n8n auto-generates internal
UUIDs for structural purposes (e.g. Switch-node condition rule IDs), and
these UUIDs matched the same shape as a plausible API token.

**Fix:** Added an explicit UUID-shape exclusion, and restricted generic
long-string matching to only fire when the surrounding parameter key name
suggests credential material (`token`, `key`, `secret`, `password`, `auth`,
`bearer`) — or when the value matches a known provider-prefix pattern
(`sk-`, `xox-`, `AKIA`) regardless of key name.

**Result:** Re-running the full corpus after the fix: hardcoded-secret
findings across all 68 real workflows dropped to 0 in the top-risk set
(public templates correctly don't expose real secrets), and the risk
signal is now driven by the intended dimension — autonomy tier and
missing error handling — not detection noise.

## 3. Manual spot-check example

Workflow: `Discord__Discord_AI-powered_bot.json` — scored 42.2/100,
classified **Act Autonomously**.

Manually inspecting the raw node list confirms the classification: an
`openAi` node makes a routing decision, feeding a `switch` node that posts
directly into one of three Discord channels (`discord` write-action
nodes). Backward graph traversal from each of those write-action nodes
finds no approval-gate node anywhere upstream, and no error handling
exists anywhere in the workflow. This is a legitimate real-world
governance concern — an LLM's output determines which Discord channel
gets an automated post, with zero verified human review — and the tool
surfaced it correctly on a real, publicly used template.

## 4. Before/after proof pair

Two versions of the same underlying workflow logic (an auto-refund flow
triggered by webhook):

| Version | Composite Score | Autonomy Tier | Error Handling | Audit Trail |
|---|---|---|---|---|
| `test_risky_workflow.json` | **37.8** | Act Autonomously | No | No |
| `test_hardened_workflow.json` | **84.2** | Act with Approval | Yes | Yes |

Changes made between versions: added an approval-gate node (Slack
sendAndWait) directly upstream of every write action in the connection
graph, moved the API call to use n8n's Credentials system instead of a
hardcoded bearer token, added an Error Trigger node and workflow-level
`errorWorkflow` setting, and added a logging node. Every dimension moved
in the expected direction, confirming the rubric responds correctly to
the governance controls it claims to measure. (Note: the hardened
version's autonomy tier score of 84.2 — down from an earlier build's
93.0 — reflects a deliberate weighting change: "Act with Approval" is
now scored as moderate-risk rather than near-safe, since Gartner's own
framework flags approval-gated automation as still requiring rigorous
controls, not as low-risk by default. See Section 6.)

## 5. Corpus-wide distribution (post graph-traversal rebuild)

- Composite score: mean 57.47, range 42.2–78.8 (n=68)
- Autonomy tier breakdown: Act Autonomously 37, Advise 20, Act with
  Approval 6, Observe 5
- Error handling present: 0 / 68 (0%)
- Audit trail present: 5 / 68 (7.35%)
- Act Autonomously + no error handling + no audit trail (compound risk):
  34 / 68 (50%)
- No scoring errors across the 68-workflow run

## 6. Known limitations (documented, not hidden)

**Resolved during development, kept here for the record:** an earlier
version of the autonomy classifier only checked whether an approval-gate
node existed *anywhere* in a workflow, not whether it actually sat
upstream of each specific write action. This was corrected by adding
backward traversal of n8n's `connections` graph — the current version
verifies a gate genuinely precedes every write-action node before
classifying a workflow as "Act with Approval." This fix roughly doubled
the fully-autonomous count (27.94% → 54.41%), since many workflows had
been receiving credit for a gate that existed but didn't actually
protect the risky action.

**A second bug, found via public review, fixed with a durable (not
"permanent") architecture change:** a LinkedIn commenter asked whether
any of the 68 real workflows had a gate-typed node present that didn't
actually protect a write action. Checking that turned up 6 cases — and
inspecting *which* node types were involved surfaced a second, unrelated
bug: 4 of the 6 were generic n8n Wait nodes (plain timed delays, `resume:
timeInterval` with no external-signal configuration) being misidentified
as human checkpoints, not a graph-position problem at all. Fixed by
requiring a Wait node to have `resume: webhook` or `resume: form`
explicitly configured before it counts as a gate — a rule based on the
node's actual configuration, not a guess.

Rather than treat this as "patched, done," the fix was generalized: a
curated node-type list can never be complete, since n8n's ecosystem
grows continuously and any novel approval pattern built with an
unfamiliar node type would otherwise be invisible no matter how well the
known-type list is tuned. A second, independent, lower-trust signal was
added — does the node's *name* suggest a human checkpoint ("approve,"
"review," "sign-off")? This signal is deliberately never allowed to
upgrade a workflow's tier on its own; it can only surface as an
unconfirmed note in the reasoning text ("possible unverified approval
step found, flagged for manual review") alongside a still-correctly-
classified "Act Autonomously" result. This is an honest trade: it can't
promise to catch every future gate pattern (no static analysis genuinely
can), but it fails by flagging uncertainty rather than by silently
missing the case entirely — a meaningfully more durable design than the
single-signal version it replaced, without overclaiming permanence.

Both fixes are now enforced by a standing regression suite
(`tests/test_gate_detection_regressions.py`) covering all 8 known cases,
run on every future change to gate-detection logic rather than checked
once and forgotten — a discipline suggested directly by the commenter who
found the bug.

## 7. Two further fixes — write-action operation-awareness and a trigger/gate conflation bug

**Write-action detection was type-only, not operation-aware.** Nodes
like Airtable, Gmail, Google Sheets, Notion, and Slack were counted as
"write actions" based purely on node TYPE, regardless of what operation
they actually performed — meaning a pure read (Airtable `search`, Gmail
`get`, Notion `getAll`) was being counted the same as a genuine write
(Airtable `create`, Gmail `send`). Direct inspection of the real corpus
found ~20 such misclassified instances across roughly a third of
workflows — including the exact "Get Schema" node flagged during an
earlier manual spot-check in this document, which was a read the whole
time. Fixed by adding a `READ_OPERATION_EXCLUSIONS` map per node type,
checked against each node's actual `operation` parameter. Deliberately
conservative: raw SQL nodes (Postgres/MySQL `executeQuery`) were left
as-is, since determining read vs. write from arbitrary SQL text is a
different scope of problem — better to over-flag a database query than
silently miss a real write hidden in it.

**A Trigger node was being treated as equivalent to a mid-flow approval
gate.** Investigating why the write-action fix flipped one workflow's
classification surfaced a second, more significant bug: `formTrigger`
was in the approval-gate node list, but a Trigger-type node is, by n8n's
own architecture, always the workflow's entry point — it can never sit
mid-flow between two other nodes (it structurally has zero incoming
connections). That means it can only represent "a human started this
run," never "a human reviewed and approved this specific risky action."
Those are different levels of oversight, and Gartner's "Act with
Approval" tier specifically requires the latter. Fixed by removing
`formTrigger` from the gate-type list while keeping the plain `form`
node (confirmed via real corpus node names like "Get Answer," "Decline,"
"Terms & Conditions" that it genuinely pauses mid-workflow for a human
decision, unlike the trigger variant).

**Combined impact across the 68-workflow corpus:** Act Autonomously rose
from 54.41% to 55.88%; more significantly, Act with Approval — the tier
meant to represent genuinely gated workflows — collapsed from 8.82% to
2.94%, since most workflows previously credited with a real gate were
only "gated" by the trigger/gate conflation bug. The compound risk stat
(Act Autonomously + no error handling + no logging) rose from 50.00% to
51.47%. Both fixes are covered by the same regression suite as Section 6.

## 8. Fixing "some path is gated" vs. "every path is gated" — a real practitioner-reported failure mode

Even after Section 7's fixes, the gate-verification logic still had a
structural gap: it checked whether a write action had *some* gated
ancestor (backward traversal from the write node), not whether *every*
path from a trigger to that write action passes through a gate. A
practitioner reviewing the project in a private message described
exactly this failure mode from real experience: a gate that exists and
passes code review, wired correctly on the primary path, but a retry or
fallback branch quietly bypasses it and reaches the same write action
under a specific failure condition — invisible to the old check, and
notably invisible to runtime monitoring too, since a runtime scan only
observes whichever branch actually fired.

Fixed by replacing the backward "does a gated ancestor exist" check with
forward reachability: starting from every trigger node (identified
structurally — any node with zero incoming connections, not a hardcoded
trigger-type list), traverse forward through the connection graph,
treating gate nodes as dead ends. If the target write action is still
reachable, at least one path bypasses every gate, and the write action is
correctly classified as ungated — regardless of whether a separate,
properly-gated path to the same node also exists.

Verified against a constructed test matching the reported scenario
exactly (a primary path through a form-based approval gate, a fallback
branch bypassing it entirely, both converging on the same write action):
correctly classified as ungated with the bypass edge present, and
correctly classified as genuinely gated with only that one edge removed —
confirming the fix responds to the exact structural feature it claims to
check, not just to surface-level cues. Both directions are now permanent
regression fixtures (`tests/test_gate_detection_regressions.py`).

**Impact on the 68-workflow corpus: none.** Re-running the full corpus
after this fix produced identical results to before it (Act Autonomously
38, Advise 23, Observe 5, Act with Approval 2; mean composite 57.73) —
none of the current real workflows happen to contain a fallback-bypass
pattern. The fix closes a real, now-proven architectural gap and is
expected to matter on future submissions through the live pipeline, even
though it didn't change today's numbers. Reported here in full rather
than only reporting fixes that moved the headline stats, since a
validation record that only mentions changes with visible impact would
itself be a form of selective reporting.

**Genuinely still open:**
- Autonomy-tier naming is *adapted from*, not a certified implementation
  of, Gartner's four-level model (Observe / Advise / Act with Approval /
  Act Autonomously, per Gartner's May 2026 press release). Observe vs.
  Advise is distinguished by checking for the presence of an AI/LLM node
  type — this is a reasonable proxy but not a guarantee that a given
  AI node is specifically generating a human-facing recommendation
  rather than doing something else read-only. Node-type detection lists
  are also necessarily incomplete against n8n's full, constantly growing
  ecosystem of integrations.
- Audit-trail detection relies on node-name keyword matching (`log`,
  `audit`, `history`), which will miss logging implemented through a
  generically-named node, and could theoretically false-positive on an
  unrelated node with "log" in its name (e.g. "Dialog Box"). No such case
  was observed in the 68-workflow corpus, but it's a known heuristic
  limitation.
- Credential-exposure detection cannot see credentials n8n itself
  encrypts and stores outside the exported JSON — it can only detect
  secrets that were hardcoded directly into node parameters.
