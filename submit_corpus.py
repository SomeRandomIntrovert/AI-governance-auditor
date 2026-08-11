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

# Windows consoles (cp1252) can't print some Unicode characters (emoji, etc.)
# that appear in a few real workflow names. Force UTF-8 stdout so those don't
# crash the whole run.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CORPUS_DIR = "samples/corpus"
PROGRESS_LOG = "output/submitted_ok.log"


def safe_print(text: str) -> None:
    """Print that can never crash on Windows console encoding issues —
    replaces any character the terminal can't display instead of raising."""
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "ascii"
        print(text.encode(encoding, errors="replace").decode(encoding))


def load_completed() -> set[str]:
    if not os.path.exists(PROGRESS_LOG):
        return set()
    with open(PROGRESS_LOG, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def mark_completed(fname: str) -> None:
    os.makedirs(os.path.dirname(PROGRESS_LOG), exist_ok=True)
    with open(PROGRESS_LOG, "a", encoding="utf-8") as f:
        f.write(fname + "\n")


def main():
    if len(sys.argv) != 2:
        print("Usage: python submit_corpus.py <n8n_webhook_url>")
        sys.exit(1)

    webhook_url = sys.argv[1]
    all_files = sorted(f for f in os.listdir(CORPUS_DIR) if f.endswith(".json"))
    completed = load_completed()
    files = [f for f in all_files if f not in completed]

    if completed:
        print(f"Resuming: {len(completed)} already submitted successfully in a prior run, skipping those.")
    print(f"Submitting {len(files)} of {len(all_files)} workflows to {webhook_url} ...")

    ok, failed = 0, 0
    failed_files = []

    for idx, fname in enumerate(files, 1):
        with open(os.path.join(CORPUS_DIR, fname), "r", encoding="utf-8") as f:
            wf = json.load(f)
        payload = {"filename": fname, "workflow": wf}

        success = False
        last_error = None
        for attempt in range(1, 4):  # up to 3 attempts per file
            try:
                resp = requests.post(webhook_url, json=payload, timeout=45)
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        safe_print(f"  [{idx}/{len(files)}] OK  {fname} -> {data}")
                        success = True
                        break
                    except ValueError:
                        last_error = f"200 but non-JSON body: {resp.text[:100]!r}"
                else:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:100]!r}"
            except Exception as e:
                last_error = str(e)

            if attempt < 3:
                time.sleep(2 * attempt)  # backoff: 2s, then 4s before retrying

        if success:
            ok += 1
            mark_completed(fname)
        else:
            failed += 1
            failed_files.append(fname)
            safe_print(f"  [{idx}/{len(files)}] FAILED after 3 attempts: {fname} -> {last_error}")

        time.sleep(1.5)  # give Render's free-tier single worker room to breathe

    print(f"\nDone. {ok} succeeded, {failed} failed this run. "
          f"({len(completed) + ok} of {len(all_files)} total complete.)")
    if failed_files:
        print("Failed files (just re-run the same command — completed ones are skipped automatically):")
        for f in failed_files:
            safe_print(f"  - {f}")


if __name__ == "__main__":
    main()
