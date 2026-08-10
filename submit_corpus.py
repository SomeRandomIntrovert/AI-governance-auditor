"""
Pushes every workflow in samples/corpus/ through the LIVE n8n webhook
pipeline (not the FastAPI endpoint directly) — this is what actually
exercises the automation end-to-end: n8n receives it, calls the scorer,
writes to Google Sheets, responds.

Usage:
    python submit_corpus.py https://<your-n8n-domain>/webhook/audit-workflow
"""
import sys
import os
import json
import time
import requests

CORPUS_DIR = "samples/corpus"


def main():
    if len(sys.argv) != 2:
        print("Usage: python submit_corpus.py <n8n_webhook_url>")
        sys.exit(1)

    webhook_url = sys.argv[1]
    files = sorted(f for f in os.listdir(CORPUS_DIR) if f.endswith(".json"))
    print(f"Submitting {len(files)} workflows to {webhook_url} ...")

    ok, failed = 0, 0
    for fname in files:
        with open(os.path.join(CORPUS_DIR, fname), "r", encoding="utf-8") as f:
            wf = json.load(f)
        payload = {"filename": fname, "workflow": wf}
        try:
            resp = requests.post(webhook_url, json=payload, timeout=30)
            if resp.status_code == 200:
                ok += 1
                print(f"  [{ok+failed}/{len(files)}] OK  {fname} -> {resp.json()}")
            else:
                failed += 1
                print(f"  [{ok+failed}/{len(files)}] FAIL ({resp.status_code}) {fname}")
        except Exception as e:
            failed += 1
            print(f"  [{ok+failed}/{len(files)}] ERROR {fname}: {e}")
        time.sleep(0.3)  # be gentle on the webhook

    print(f"\nDone. {ok} succeeded, {failed} failed.")


if __name__ == "__main__":
    main()
