# Verification — 2026-10-24

Environment: Windows, Python 3.13.7, NVIDIA GeForce RTX 3070 (8 GB VRAM).

- `python -m pytest -q`: **12 passed**. Tests use synthetic Gmail messages and mocked model responses, except real Windows DPAPI encryption/decryption and actual Streamlit application rendering through AppTest.
- `python -m ruff check .`: passed.
- `python -m pip check`: no broken requirements.
- Streamlit started at `http://127.0.0.1:8501`; `/_stcore/health` returned HTTP 200 with `ok`.
- The saved synthetic offer appears with its 80/100 score in the Streamlit rendering test. Synthetic data is isolated in temporary test storage, not the personal database.
- Windows task `JobMatchLocalAI-Sync` registered successfully and queried as Ready, interactive user mode. It triggers at the next user logon and repeats every three hours; initial next-run time is N/A until that logon trigger. Actual execution at logon has not been observed yet.
- Git repository initialized locally; private directories, credentials, tokens and virtual environment ignored. No remote, commit or publication created.
- Real synchronization attempted and stopped safely before Gmail access because the personal CV/preferences were empty. Doctor also confirmed absent OAuth client/token and an unavailable local Ollama endpoint. No real Gmail offers were retrieved or analyzed.

## Required personal setup

Private directory: `C:\Users\Nitropc\AppData\Local\JobMatchLocalAI`.

1. Fill `cv.txt` and `preferences.txt`.
2. Save a Gmail-enabled Desktop OAuth client JSON as `credentials.json` in that directory.
3. Start Ollama with a local `qwen2.5:7b` model, or configure another installed local model in `settings.json`.
4. Run `.\.venv\Scripts\jobmatch.exe authorize` and complete Google consent personally.
5. Run `.\.venv\Scripts\jobmatch.exe sync` twice and verify the real results in the dashboard. Confirm the second run introduces no duplicates.

Until these steps are complete, scheduled invocations will fail safely without processing mail. The requested real end-to-end acceptance test remains pending; unit/integration checks must not be interpreted as a substitute.

## Ollama integration update — 2026-10-24

This update supersedes the earlier Ollama/profile readiness findings above.

- Active private settings now use `qwen3:4b-instruct` through `http://localhost:11434`.
- Python successfully called the real local `/api/tags` endpoint and confirmed the model is installed.
- Actual `/api/show` and `/api/chat` calls succeeded using the real private CV/preferences and an explicitly synthetic job excerpt. Schema validation accepted score 15/100, low confidence, three matches, five concerns and three unknowns. This score describes only that synthetic test and is not a real offer assessment.
- Full test output is saved privately as `ollama-validation.json`; no test offer was inserted in the personal jobs database.
- `python -m pytest -q`: **21 passed**, including connection failures, timeouts, invalid output, HTTP failures, remote model rejection, external endpoint rejection and Windows UTF-8 BOM configuration support.
- Ruff formatting/checks and `pip check` passed.
- Configured HTTP transport ignores environment proxies and refuses redirects. Only loopback URLs are permitted; there is no external inference fallback.
- Gmail OAuth token is still absent and there are zero real stored offers. Retrieval, analysis and panel verification using real Gmail offers remain pending personal Google consent. The existing sync pipeline uses the configured Ollama model automatically after authorization.

## Real Gmail acceptance update — 2026-10-24

This update supersedes the OAuth and real-data blockers above.

- Personal Google consent completed; doctor confirms an encrypted OAuth token and an available local `qwen3:4b-instruct` model.
- Real Gmail ingestion persisted 142 messages and **474 unique offers** from the initial history window.
- The first attempt encountered a Gmail API error after committing partial ingestion. A subsequent synchronization recovered the remaining 23 messages without data loss, analyzed three real offers with local Ollama and reported zero errors.
- A second successful synchronization reported **0 new messages, 1 additional analysis, 0 errors**. The stored offer count remained 474 with **0 duplicate IDs**.
- Four actual persisted analyses passed JSON/schema validation. The real-data Streamlit render displayed 474 offers and four scored offer cards, with zero rendering exceptions. The live server health endpoint returned HTTP 200 (`ok`).
- **470 offers remain pending analysis**. Synchronization now processes at most `max_analyses` offers per invocation (default 20), preserving pending work for later runs. Acceptance runs used temporary command-line limits of three and one. These limits did not change scheduled settings.
- The per-user scheduled task remains registered and Ready. Its first trigger is the next Windows logon, followed by three-hour repetition; execution at a real logon remains unobserved.
- Tests: **22 passed**; Ruff and dependency checks passed. Added coverage verifies that limited analysis batches preserve pending work and never repeat completed analyses.
- Personal emails, CV and model explanations were not copied into this repository or this report. No LinkedIn pages were fetched and no applications were submitted.

## Rolling 24-hour window update — 2026-10-24

- Active private settings now use `lookback_hours: 24`. The former persisted initial-history boundary is ignored.
- Gmail ingestion, pending-analysis eligibility and the default dashboard view use the recommendation email's received timestamp. Job publication dates are not inferred.
- Older stored offers and analyses are retained. They are excluded from new analysis unless a recent recommendation email references the same offer. The dashboard provides an explicit archive checkbox.
- Real validation sync: **0 new messages, 3 analyses, 0 errors**. The real dashboard rendered **27 offers** in the 24-hour window with no exceptions; the full archive retained 474 unique offers.
- **25 tests passed**, with Ruff checks passing. Coverage includes old pending offers being skipped, recent recommendations making existing offers eligible, and archive visibility without deletion.
- Older pending offers can age out without analysis; this is intentional under the requested rolling-window behavior.
