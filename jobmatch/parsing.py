"""Extract only job links embedded in mail. Never fetch a job URL."""

import base64
import re
from dataclasses import dataclass
from email.utils import parseaddr
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup


@dataclass
class Job:
    id: str
    title: str
    url: str
    context: str


def canonical_job(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not (
        parsed.hostname == "linkedin.com"
        or (parsed.hostname or "").endswith(".linkedin.com")
    ):
        return None
    match = re.search(r"/jobs/view/(?:[^/?#]*-)?(\d+)(?:/|$)", parsed.path)
    job_id = match.group(1) if match else None
    if not job_id and parsed.path.startswith("/comm/jobs/view/"):
        match = re.search(r"/comm/jobs/view/(\d+)", parsed.path)
        job_id = match.group(1) if match else None
    if not job_id:
        job_id = (parse_qs(parsed.query).get("currentJobId") or [None])[0]
    return str(job_id) if job_id and str(job_id).isdigit() else None


def bodies(payload):
    if payload.get("mimeType") in ("text/html", "text/plain") and payload.get(
        "body", {}
    ).get("data"):
        data = payload["body"]["data"]
        yield (
            payload["mimeType"],
            base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode(
                "utf-8", errors="replace"
            ),
        )
    for part in payload.get("parts", []):
        yield from bodies(part)


def link_context(anchor):
    """Use the largest nearby container containing just this job's ID."""
    target = canonical_job(anchor.get("href", ""))
    best = anchor.get_text(" ", strip=True)
    for parent in list(anchor.parents)[:6]:
        ids = {canonical_job(a.get("href", "")) for a in parent.find_all("a")}
        ids.discard(None)
        if ids != {target}:
            break
        text = parent.get_text(" ", strip=True)
        if len(text) > 12000:
            break
        best = text
    return best


def extract(message):
    payload = message.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    sender = parseaddr(headers.get("from", ""))[1].lower()
    if not sender.endswith("@linkedin.com"):
        return []
    found = {}
    for mime, body in bodies(payload):
        soup = BeautifulSoup(body, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        candidates = (
            [
                (a.get("href", ""), a.get_text(" ", strip=True), link_context(a))
                for a in soup.find_all("a")
            ]
            if mime == "text/html"
            else [
                (u, "Job recommendation", body)
                for u in re.findall(r'https://[^\s<>"\)]+', body)
            ]
        )
        for url, title, context in candidates:
            job_id = canonical_job(url)
            if job_id and (
                job_id not in found or len(context) > len(found[job_id].context)
            ):
                found[job_id] = Job(
                    job_id,
                    title[:300] or "Job recommendation",
                    f"https://www.linkedin.com/jobs/view/{job_id}/",
                    context[:12000],
                )
    return list(found.values())
