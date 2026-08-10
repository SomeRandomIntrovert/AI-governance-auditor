# Wiring up the n8n orchestration pipeline

This pipeline is the "automation" layer of the project: it's what turns a
one-off script into a standing, triggerable audit process. Import
`n8n_pipeline/governance_audit_pipeline.json` into your n8n instance and
follow these steps.

## 1. Deploy the FastAPI scorer somewhere n8n can reach it

n8n needs to be able to call `POST /score` over HTTP. Two options:

- **Local demo (simplest, good for recording a screen capture):** run
  `uvicorn api.main:app --port 8000` on the same machine as a
  self-hosted n8n instance, and set `GOVERNANCE_API_URL=http://localhost:8000`
  as an n8n environment variable.
- **Public deploy (better for a live, shareable link):** deploy the
  `api/` folder to a free tier on Render or Railway. Set
  `GOVERNANCE_API_URL` to the public URL it gives you. This also means
  the pipeline works from n8n Cloud, not just self-hosted.

## 2. Create the Google Sheet

Create a new Google Sheet named anything you like, with a tab called
`governance_report` and this header row (must match exactly — the n8n
node maps to these column names):

```
timestamp | filename | workflow_name | node_count | composite_risk_score |
credential_score | hardcoded_secrets_found | error_handling_score |
has_error_handling | autonomy_score | autonomy_tier | audit_score |
has_logging_node
```

Grab the Sheet ID from its URL (`.../d/<THIS_PART>/edit`) and set it as
the n8n environment variable `GOVERNANCE_SHEET_ID`.

## 3. Import the pipeline

In n8n: **Workflows → Import from File** → select
`n8n_pipeline/governance_audit_pipeline.json`.

Open the **Append Result to Google Sheet** node and select/create your
Google Sheets credential (the JSON ships with a placeholder credential ID
that won't work until you swap it for your own).

Activate the workflow. n8n will give you a live webhook URL — that's your
audit endpoint.

## 4. Test it

```bash
curl -X POST https://<your-n8n-webhook-url>/webhook/audit-workflow \
  -H "Content-Type: application/json" \
  -d @samples/test_risky_workflow.json
```

You should see a new row appear in the Google Sheet within seconds, and
get back a JSON response with the composite score and autonomy tier.

## 5. Run the full corpus through it

Once the webhook is live, use `submit_corpus.py` (in the project root) to
push all 68 real corpus workflows through the pipeline in one go — this
populates the sheet with the full dataset Looker Studio will visualize.
