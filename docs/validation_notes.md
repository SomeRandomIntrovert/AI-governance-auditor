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
classified **Autonomous**.

Manually inspecting the raw node list confirms the classification: an
`openAi` node makes a routing decision, feeding a `switch` node that posts
directly into one of three Discord channels (`discord` write-action
nodes) with no approval-gate node anywhere in the workflow and no error
handling. This is a legitimate real-world governance concern — an LLM's
output determines which Discord channel gets an automated post, with zero
human review — and the tool surfaced it correctly on a real, publicly
used template.

## 4. Before/after proof pair

Two versions of the same underlying workflow logic (an auto-refund flow
triggered by webhook):

| Version | Composite Score | Autonomy Tier | Error Handling | Audit Trail |
|---|---|---|---|---|
| `test_risky_workflow.json` | **37.8** | Autonomous | No | No |
| `test_hardened_workflow.json` | **93.0** | Assist | Yes | Yes |

Changes made between versions: added an approval-gate node (Slack
sendAndWait) before the write action, moved the API call to use n8n's
Credentials system instead of a hardcoded bearer token, added an Error
Trigger node and workflow-level `errorWorkflow` setting, and added a
logging node. Every dimension moved in the expected direction, confirming
the rubric responds correctly to the governance controls it claims to
measure.

## 5. Corpus-wide distribution (post-fix)

- Composite score: mean 63.3, range 42.2–84.0 (n=68)
- Autonomy tier breakdown: Observe 25, Autonomous 19, Assist 12, Execute-with-gap 12
- No scoring errors across the 68-workflow run

## 6. Known limitations (documented, not hidden)

- Autonomy-tier classification currently checks for the **presence** of
  an approval-gate node anywhere in the workflow, not full graph
  traversal to confirm the gate sits directly upstream of every write
  action. A workflow with an unrelated approval gate and a separate,
  ungated write action would currently be scored more favorably than it
  should. Flagged in the rubric code and here for transparency; a v2
  improvement would walk the `connections` graph explicitly.
- Audit-trail detection relies on node-name keyword matching (`log`,
  `audit`, `history`), which will miss logging implemented through a
  generically-named node, and could theoretically false-positive on an
  unrelated node with "log" in its name (e.g. "Dialog Box"). No such case
  was observed in the 68-workflow corpus, but it's a known heuristic
  limitation.
- Credential-exposure detection cannot see credentials n8n itself
  encrypts and stores outside the exported JSON — it can only detect
  secrets that were hardcoded directly into node parameters.
