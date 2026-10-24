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

Fill `cv.txt` with your CV as plain UTF-8 text and `preferences.txt` with desired roles, location, remote policy, seniority, salary and deal breakers. PDF/DOCX imports are intentionally not supported: export the relevant text first. Settings are in `settings.json`; the default model is `qwen2.5:7b` and the interval is three hours.

Install/start Ollama and download the model explicitly:

```powershell
ollama pull qwen2.5:7b
ollama serve
```

If the Ollama Windows application already serves port 11434, do not start a second server. Only the loopback Ollama endpoint is used. Cloud model names and remote aliases are rejected. Configure Ollama with cloud features disabled (`OLLAMA_NO_CLOUD=1`) for defense in depth. A 7B quantized model is a reasonable starting point for an 8 GB GPU; memory use depends on context and other applications.

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

The first sync includes the previous 30 days by default. This initial boundary is saved, so older unprocessed messages cannot fall out of a sliding time window. The configurable `max_messages` limits new email ingestion per invocation; remaining mail is processed on subsequent runs. Gmail result pages are scanned for unknown IDs; known messages are never downloaded again. This deliberately favors recovery and correctness over mailbox-scale history cursor complexity. Gmail list scanning grows over time.

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
