# AI Agent Governance Auditor (n8n)

**80% of Fortune 500 companies now run AI agents built with low-code
tools, and only 10% have a governance strategy for them (Microsoft 2026
Cyber Pulse Report). The governance vendors that do exist — Credo AI,
Vectra, Microsoft Purview — inspect API traffic and SSO logs. None of
them read the actual workflow definitions where an agent's permissions,
autonomy, and blast radius are configured. This tool does.**

It parses exported n8n workflow JSON and scores it across four dimensions
grounded in two published external frameworks — Gartner's May 2026
proportional AI-agent governance model, and n8n's own documented security
guidance — rather than an invented rubric. The scoring is orchestrated as
a standing, triggerable n8n pipeline, not a one-off script: submit a
workflow to a webhook, it's scored, logged, and visible on a live
dashboard within seconds.

## The gap, precisely

Enterprise AI governance tooling operates at the network/API layer — who
called what service, from where. It has no visibility into
workflow-definition risk: whether an agent's write actions are gated
behind human approval, whether failures are handled or silent, whether
credentials are hardcoded, whether any audit trail exists. That's a
structural blind spot specific to low-code platforms, where — per
Gartner — the fastest-growing share of enterprise agents are actually
being built.

## Architecture

```
New workflow JSON submitted (webhook)
        ↓
n8n pipeline (orchestration layer)
   → HTTP Request → FastAPI /score endpoint (governance rubric)
   → Google Sheets → append scored result
        ↓
Looker Studio dashboard, live-connected to the Sheet
   → automated refresh (1-15 min) — near-real-time fleet risk view
```

## The four scoring dimensions

| Dimension | What it checks | Framework basis |
|---|---|---|
| Credential exposure | Hardcoded secrets in node params vs. proper n8n Credentials system usage | n8n security guidance |
| Error handling | Presence of Error Trigger node / errorWorkflow setting | n8n security guidance |
| Autonomy tier | Observe / Assist / Execute-with-gap / Autonomous, based on write-action nodes vs. approval gates | Gartner proportional governance model (May 2026) |
| Audit trail | Presence of logging/history-capturing nodes | Governance best practice |

## Findings — 68 real, public n8n workflows

Autonomy classification uses verified upstream graph traversal (not
presence-anywhere checking) — see Methodology below for exactly what
that means and why it changes the numbers.

| Metric | Value |
|---|---|
| Workflows audited | 68 |
| Average composite risk score | 57.47 / 100 |
| Act fully autonomously, no verified approval gate | **54.41%** |
| Have structured error handling | **0.00%** |
| Have any audit-trail logging | 7.35% |
| Act Autonomously **and** no error handling **and** no logging | **50.00%** |
| Highest-risk category | Discord (avg. 45.27) |

The compound stat is the sharpest finding: half of these real,
publicly-used AI agent templates can take real-world actions with no
verified human approval anywhere in their execution path, fail silently
if something breaks, and leave no record either way if something goes
wrong.

**Example finding:** `Discord__Discord_AI-powered_bot.json` scored 42.2 —
an LLM makes a routing decision that determines which of three live
Discord channels receives an automated post, with no approval gate and
no error handling anywhere in the workflow.

## Methodology — autonomy classification

Adapted from Gartner's AI-agent autonomy model (May 2026): Observe,
Advise, Act with Approval, Act Autonomously. Two things this
implementation does to genuinely earn those labels rather than
approximate them:

1. **Observe vs. Advise** is distinguished by checking for an AI/LLM
   node. Zero write actions + no AI node = pure data movement (Observe).
   Zero write actions + an AI node present = generating a recommendation
   for a human to act on manually (Advise).
2. **"Act with Approval" requires a verified upstream approval gate for
   every individual write-action node**, checked via backward traversal
   of n8n's actual `connections` graph — not merely checking that a gate
   node exists somewhere in the workflow. A single ungated write action
   anywhere drops the whole workflow to "Act Autonomously," matching
   Gartner's own definition that this tier requires *every* action to be
   gated.

This is still an adaptation, not a certified implementation — node-type
detection lists are necessarily incomplete against n8n's full ecosystem.
Full detail in `docs/validation_notes.md`.

## Validation — documented debugging trail

Not synthetic data — see `docs/validation_notes.md` for full corpus
sourcing and methodology. Validation caught and fixed a real
false-positive bug (n8n's internal structural UUIDs were being
misidentified as hardcoded secrets), manually confirmed the "Autonomous"
flag against the Discord bot example above, and validated scoring
direction with a before/after pair on deliberately hardened vs.
unhardened versions of the same workflow logic:

| | Composite Score | Autonomy Tier |
|---|---|---|
| Before hardening | 37.8 | Autonomous |
| After hardening | 93.0 | Assist |

Known limitations documented honestly in `docs/validation_notes.md` —
including where the current heuristics can still be wrong, and what a v2
would fix (in particular: audit-trail detection relies on node-name
keyword matching rather than structural analysis, and autonomy
classification checks for approval-gate *presence* rather than its exact
position in the execution graph).

## Live artifacts

- **Dashboard:** https://datastudio.google.com/reporting/9c7db748-d105-424b-b0c4-6e04fc9bdfc8
- **Repo:** https://github.com/SomeRandomIntrovert/AI-governance-auditor

## Repo structure

```
api/                    FastAPI service + governance rubric logic
n8n_pipeline/            Importable n8n workflow (the orchestration layer)
samples/corpus/          68 real n8n workflow templates used for validation
output/                  governance_report.csv (full scored corpus)
docs/                    Setup guides + validation notes
batch_score.py           Standalone batch scorer (used for corpus validation)
submit_corpus.py         Pushes the full corpus through the live n8n webhook
```

## Setup

See `docs/n8n_setup.md` for wiring the pipeline to your own n8n instance,
and `docs/looker_studio_setup.md` for the dashboard.

## Stack

Python, FastAPI, n8n, Google Sheets, Looker Studio.

## Known limitations

Documented in full in `docs/validation_notes.md` rather than hidden —
notably, autonomy-tier classification currently checks for presence of
an approval gate anywhere in the workflow rather than confirming its
exact position in the execution graph relative to each write action.
