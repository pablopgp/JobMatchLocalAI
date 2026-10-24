# Security

Never post CVs, Gmail payloads, OAuth JSON, access tokens, refresh tokens or database files in issues. Report security concerns privately to the repository owner once a repository is published.

The application requests Gmail read-only permission, uses current-user Windows DPAPI for tokens and performs inference only through loopback Ollama. It does not fetch LinkedIn pages, follow email links, run model-generated commands or send applications. Treat email content and model output as untrusted evidence. Keep Python dependencies, Ollama, Windows and the browser updated.

Local personal data is not fully encrypted by this application. Use a private Windows account and appropriate disk encryption. Do not expose Streamlit or Ollama to a network. A local process with access to your Windows account can access personal data and decrypt your OAuth token.
