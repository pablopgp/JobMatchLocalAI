# JobMatch Local AI

A Windows application that reads LinkedIn job recommendation emails through the official Gmail API, scores email evidence against your CV using local Ollama, and displays persisted results in Streamlit. It never requests LinkedIn pages or submits applications.

## Installation

Use Python 3.11 or newer. From PowerShell in the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\jobmatch.exe init
```

For the exact validated Windows dependency versions, install with `python -m pip install -r requirements.lock.txt` followed by `python -m pip install --no-deps -e .` inside the virtual environment.

Data defaults to `%LOCALAPPDATA%\JobMatchLocalAI`, outside the repository. Override with `JOBMATCH_HOME` or `jobmatch --data-dir C:\path\to\private <command>`. Use the same directory for every command. Do not place it in a cloud-synchronized folder or a shared location.

Fill `cv.txt` with your CV as plain UTF-8 text and `preferences.txt` with desired roles, location, remote policy, seniority, salary and deal breakers. PDF/DOCX imports are intentionally not supported: export the relevant text first. Settings are in `settings.json`; the default model is `qwen3:4b-instruct` and the interval is three hours.

Install/start Ollama and download the model explicitly:

```powershell
ollama pull qwen3:4b-instruct
ollama serve
```

If the Ollama Windows application already serves port 11434, do not start a second server. Only the loopback Ollama endpoint is used. Cloud model names and remote aliases are rejected. Configure Ollama with cloud features disabled (`OLLAMA_NO_CLOUD=1`) for defense in depth. A 4B quantized model is a reasonable starting point for an 8 GB GPU; memory use depends on context and other applications.

The active configuration is `%LOCALAPPDATA%\JobMatchLocalAI\settings.json` (or the selected private data directory). Set `"model": "qwen3:4b-instruct"` and `"ollama_url": "http://localhost:11434"`. Only localhost and 127.0.0.1 on port 11434 are accepted. Python ignores environment proxy settings and never follows HTTP redirects. Model metadata is checked before sending any CV or email excerpt. The application never downloads models automatically or falls back to cloud inference. `doctor` reports the configured endpoint, installed models and whether the configured model is present.

Analysis returns a validated JSON object: `score` (indicative 0–100, not a hiring probability), `confidence`, `reasons` (evidenced matches), `concerns` (evidenced incompatibilities), and `missing_information` (unknown facts). Unknowns must not be treated as incompatibilities. Inference disables thinking output and uses deterministic temperature settings. Connection timeouts are five seconds and inference timeouts are 240 seconds. Connection, timeout, HTTP and invalid-response failures have safe error categories; failed offers remain pending and are retried by the next synchronization. Response bodies containing personal information are never included in error messages.

New analyses also include `preference_checks`: atomic role, seniority, location, work arrangement and salary checks with met/not_met/unknown, explanations and supporting job quotes. Confirmed claims without a matching quote are downgraded to unknown. Preferences describe the desired job, never the candidate's salary history. The sidebar displays the actual active preferences file/content; outdated scores are flagged directly in previews. Historical multi-job text digests are isolated by job ID before inference; unavailable target excerpts remain explicit unknowns instead of borrowing another offer's facts. Scores remain model estimates and can still be imperfect.

## Gmail authorization (personal setup required)

1. Create/select your own Google Cloud project and enable the Gmail API.
2. Configure the OAuth consent screen. For an external app in testing, add your Gmail address as a test user.
3. Create an OAuth client with application type **Desktop app**.
4. Download its JSON and save it as `credentials.json` in the private data directory. Never commit this file.
5. Run `jobmatch authorize` from the activated virtual environment, or `.\.venv\Scripts\jobmatch.exe authorize`. Sign in and consent in your browser.

The only requested scope is `https://www.googleapis.com/auth/gmail.readonly`. Authorization is interactive only in this command; scheduled sync never opens a login browser. Tokens are encrypted using current-user Windows DPAPI. Google may expire refresh tokens for external apps in testing (commonly after seven days); authorize again if necessary. See [Google's official quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python).

## Operation

```powershell
.\.venv\Scripts\jobmatch.exe doctor
.\.venv\Scripts\jobmatch.exe sync
.\.venv\Scripts\jobmatch.exe dashboard
.\.venv\Scripts\jobmatch.exe install-task
```

The dashboard is at http://127.0.0.1:8501. It starts only on request and does not synchronize. Refresh after a sync. The scheduled task runs at user logon, repeats at the configured interval, and exits after each sync. It uses the current Windows user without storing a password and ignores overlapping runs. Re-run `install-task` after changing `interval_hours`, the virtual environment, or the data directory. `remove-task` removes it. The task requires a logged-in session; it does not wake or sign in to Windows. Ollama must be available when it runs.

Offer cards show a circular compatibility chart, company, confidence and an explicit **Open offer on LinkedIn** button. Clicking the button navigates your browser to the canonical offer URL; the application does not fetch it. Pending offers have no invented score. Companies are extracted conservatively from email company links, labeled text, or the title/company/location lines preceding the matching job link in saved text digests. Unknown companies are identified explicitly. Existing records can display recovered metadata without fetching mail or rerunning inference. Search includes company names, and results are paginated in groups of 12.

Use **Save offer** to keep an offer for follow-up beyond the 24-hour display window. The **Saved offers** view shows these records regardless of email age. Saved cards provide private notes and a manual status: Interested, Applied, Interview, Offer, Rejected or Closed. **Save follow-up** persists changes in SQLite; notes and statuses are not sent to Ollama. **Unsave offer** removes the bookmark while retaining notes and status. Changing a status never submits an application.

The sidebar **Resynchronize all offers** button starts a separate, hidden one-shot Python worker. It retrieves all new matching emails within `lookback_hours` and reanalyzes every non-deleted offer linked to that window, including completed analyses, using the current profile. This explicit manual action bypasses the normal per-run batch limits while retaining the rolling time window and deduplication. It does not revisit the entire archived mailbox. Closing the panel does not interrupt the worker, which exits on completion. Refresh to display progress/results. Locks prevent overlapping synchronization; safe failure categories and result counts are stored in the private `manual-sync.json` file. Scheduled and CLI synchronization retain their normal incremental batch behavior.

**Delete offer** moves an offer to **Trash**, retaining its data so it can be restored. Deleted offers are excluded from the main/saved views and model analysis, even when the same LinkedIn job is recommended in a new email. **Restore offer** returns it with its saved flag, notes and status intact. Deletion is reversible and does not permanently erase personal data. All these actions use local SQLite only and do not access Gmail or run analysis.

**Mark as Viewed** adds a persistent, independent viewed marker and light blue card background. Click **Viewed ✓** to remove it. It does not change the saved flag or follow-up status. In the **Trash** view, expand **Empty trash**, confirm permanent deletion and click **Empty trash permanently** to remove all trashed offer records, notes, analyses and message links. Active offers are unaffected. A minimal job-ID suppression list is retained to prevent reimport; purged offers cannot be restored. This does not delete the original Gmail messages or remove references that may occur in other offers' shared email excerpts.

Every sync uses a rolling window of the last 24 hours, configurable through `lookback_hours` in the private `settings.json`. Gmail filtering and analysis eligibility use the email receipt timestamp, not the job publication date (which is often unknown). The configurable `max_messages` limits new email ingestion per invocation. Known messages are never downloaded again. Older saved offers remain in SQLite, but they are not analyzed unless recommended again in a recent email. The panel defaults to this same window; enable **Include older saved offers** to browse the archive. The previous persisted initial-history boundary is no longer used.

`max_analyses` limits local model calls per invocation (default 20), independently of email ingestion. Pending offers remain eligible only while their recommendation email is inside the rolling window. Offers can therefore age out before analysis if the backlog exceeds processing capacity or the computer is off for more than 24 hours. For a shorter manual validation, use `jobmatch --max-analyses 3 sync`; this override does not change scheduled settings. Repeated syncs may analyze more eligible pending offers, but never create duplicate job IDs. Interruptions mark the run as failed and preserve already committed work.

Job IDs normalize tracking links and deduplicate offers across emails. Message extraction is transactional. Analysis failures are retained and retried on the next invocation. CV, preferences, model and prompt version determine an analysis fingerprint; changed profiles trigger reanalysis. The dashboard flags old results until updated. Empty or unsupported emails are recorded and counted visibly. Only recognized LinkedIn job URLs are extracted; shortened redirects and future email formats may need parser updates. No redirects are followed. Repeated emails do not enrich previously stored job excerpts.

## Privacy and limits

Gmail traffic goes to Google; CV/preferences and job excerpts go only to the local Ollama endpoint. No cloud AI SDK is used. External images and links are never loaded by the parser or panel. Scores are estimates from incomplete email excerpts, not verified full job descriptions. Missing salary, location or requirements must remain explicit unknowns. Email sender filtering is not cryptographic sender authentication; treat all email evidence as untrusted.

OAuth tokens have DPAPI encryption at rest. CV, preferences, job evidence and SQLite are plaintext private local files: protect your Windows account, filesystem permissions, backups and disk with BitLocker where appropriate. DPAPI does not protect against another process already running as your user. SQLite stores excerpts rather than complete raw emails. Errors store exception types, not response bodies or tokens. Deleting the private directory removes local records; revoke Google authorization separately in your account settings. There is no telemetry in application code, and Streamlit usage telemetry is disabled by the launch command.

## Development and verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

Tests cover parsing, hostile domains, idempotency, profile changes, retry recovery, concurrency locking, structured output validation, loopback inference, Windows DPAPI and rendering a saved offer in Streamlit. Gmail and inference integration tests use synthetic data and mocked transports; they do not prove real OAuth or model quality. After OAuth and the private profile are configured, run a real sync twice: the first should create/analyze offers, and the second should report zero new messages/analyses. Check the panel and recent runs. No repository is published automatically.

The project uses the [Ollama chat API](https://docs.ollama.com/api/chat) and [schema-constrained output](https://docs.ollama.com/capabilities/structured-outputs). Dependencies are bounded in `pyproject.toml`; `requirements.lock.txt` records the validated Windows environment for reproducibility.
