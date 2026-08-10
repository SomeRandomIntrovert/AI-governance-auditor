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

## Validation — real corpus, documented debugging trail

68 real, public n8n workflow templates were scored (not synthetic data —
see `docs/validation_notes.md` for the full corpus sourcing). Validation
caught and fixed a real false-positive bug (n8n's internal structural
UUIDs were being misidentified as hardcoded secrets), confirmed via a
manual spot-check that the tool's "Autonomous" flag correctly identified
a real ungated LLM-routing risk in a popular public Discord bot template,
and validated the scoring direction with a before/after pair on
deliberately hardened vs. unhardened versions of the same workflow logic:

| | Composite Score | Autonomy Tier |
|---|---|---|
| Before hardening | 37.8 | Autonomous |
| After hardening | 93.0 | Assist |

Full methodology and known limitations documented honestly in
`docs/validation_notes.md` — including where the current heuristics can
still be wrong, and what a v2 would fix.

## Live artifacts

- **Dashboard:** [Looker Studio link — add after publishing]
- **Demo:** [Loom walkthrough link — add after recording]
- **API:** deployed FastAPI scorer — [add public URL if deployed]

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
