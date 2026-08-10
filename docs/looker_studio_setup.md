# Looker Studio dashboard setup

Connects live to the same Google Sheet the n8n pipeline writes to —
new audits show up on the dashboard without any manual export step.

## 1. Connect the data source

1. Go to [lookerstudio.google.com](https://lookerstudio.google.com) → **Create → Report**
2. Choose **Google Sheets** as the connector
3. Select the sheet you created in the n8n setup step, tab `governance_report`
4. Under the data source's freshness setting, set **Data Freshness** to
   1 or 15 minutes (this is what makes it near-real-time rather than a
   static export — see the note below on what this claim actually means)

## 2. Build these views

**View 1 — Fleet Risk Heatmap**
Table or heatmap chart: rows = `category` (parse from filename prefix, or
add a category column via a calculated field splitting on `__`),
color/value = average `composite_risk_score`. This is the "stop scrolling"
view — one glance shows where the risk concentrates.

**View 2 — Autonomy Tier Distribution**
Donut or bar chart: count of workflows by `autonomy_tier`
(Observe / Assist / Execute-with-gap / Autonomous). This is the direct
visualization of the Gartner framework the rubric is built on.

**View 3 — Top Contributing Risk Factors**
Four scorecards or a bar chart comparing average `credential_score`,
`error_handling_score`, `autonomy_score`, `audit_score` across the fleet
— shows which governance dimension is weakest overall.

**View 4 — Drill-down table**
Full table: `filename`, `workflow_name`, `composite_risk_score`,
`autonomy_tier`, `has_error_handling`, `has_logging_node`, `timestamp`,
sortable/filterable — lets a viewer click into any individual result.

## 3. A note on the "real-time" claim

Looker Studio's Google Sheets connector re-queries on the freshness
interval you set (as low as 1 minute), not on every single write via
push/websocket. Describe this accurately as "automated pipeline with
near-real-time dashboard refresh" — that's both true and still a strong
claim, and it will hold up if an interviewer asks how the refresh
actually works.

## 4. Publish

**File → Share → Publish to web**, or share the report link directly.
Grab the share link for the README and LinkedIn post.
