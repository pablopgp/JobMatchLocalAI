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
    company: str | None = None


def saved_job_details(job_id, title, context):
    """Recover explicit title/company lines for one link from a stored text digest."""
    for match in re.finditer(r'https://[^\s<>"\)]+', context):
        if canonical_job(match.group()) != job_id:
            continue
        blocks = re.split(r"\n\s*\n", context[: match.start()])
        for block in reversed(blocks[-4:]):
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            lines = [
                line
                for line in lines
                if not re.match(
                    r"(?:Esta empresa|Solicitar con|Ver anuncio|Actively hiring|Apply with|View job)",
                    line,
                    re.I,
                )
            ]
            if "https://" in block:
                break
            if 3 <= len(lines) <= 5 and not any("https://" in line for line in lines):
                if all(len(line) <= 300 for line in lines[:3]):
                    return lines[0], lines[1]
    labeled = re.search(r"(?:^|\n)(?:Company|Empresa)\s*:\s*([^\n]+)", context, re.I)
    return title, labeled.group(1).strip()[:300] if labeled else None


def analysis_evidence(job):
    """Isolate this job from historical multi-job digests without fetching links."""
    identity = job["id"]
    context = job["context"].replace("\r\n", "\n")
    links = list(re.finditer(r'https://[^\s<>"\)]+', context))
    job_links = [match for match in links if canonical_job(match.group())]
    target = next(
        (match for match in job_links if canonical_job(match.group()) == identity), None
    )
    if job_links:
        if target is None:
            return {
                "title": job["title"],
                "context": "The saved digest does not contain the excerpt for this specific job. Requirements, location, work arrangement and salary are unknown.",
            }
        start = 0
        for match in job_links:
            if match.start() >= target.start():
                break
            if canonical_job(match.group()) != identity:
                start = match.end()
        section = context[start : target.start()]
        section = re.split(r"\n[ \t]*-{5,}[ \t]*\n", section)[-1]
        # Remove alert headers and repeated action labels before the job details.
        blocks = re.split(r"\n\s*\n", section)
        for index, block in enumerate(blocks):
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if len(lines) >= 3 and not any("https://" in line for line in lines):
                section = "\n\n".join(blocks[index:])
                break
        context = section
    title, company = saved_job_details(identity, job["title"], job["context"])
    clean = re.sub(r'https://[^\s<>"\)]+', "", context)
    return {
        "title": title,
        "company": job.get("company") or company,
        "context": clean[:12000],
    }


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
        text = parent.get_text("\n", strip=True)
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
    content = list(bodies(payload))
    # Prefer HTML job cards over entire plain-text digests.
    content.sort(key=lambda part: part[0] != "text/html")
    for mime, body in content:
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
            if mime == "text/plain" and job_id in found:
                continue
            company = None
            if mime == "text/plain" and job_id:
                title, company = saved_job_details(job_id, title, context)
            elif mime == "text/html" and job_id:
                for anchor in soup.find_all("a"):
                    parsed = urlparse(anchor.get("href", ""))
                    if (
                        parsed.hostname
                        and (
                            parsed.hostname == "linkedin.com"
                            or parsed.hostname.endswith(".linkedin.com")
                        )
                        and "/company/" in parsed.path
                    ):
                        name = anchor.get_text(" ", strip=True)
                        if name and name in context:
                            company = name[:300]
                            break
            if job_id and (
                job_id not in found or len(context) > len(found[job_id].context)
            ):
                found[job_id] = Job(
                    job_id,
                    title[:300] or "Job recommendation",
                    f"https://www.linkedin.com/jobs/view/{job_id}/",
                    context[:12000],
                    company,
                )
    return list(found.values())
