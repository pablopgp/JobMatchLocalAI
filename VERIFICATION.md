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
