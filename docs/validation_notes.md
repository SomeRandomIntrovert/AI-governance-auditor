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
