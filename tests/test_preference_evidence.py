from jobmatch.parsing import analysis_evidence, saved_job_details


def test_evidence_uses_only_the_target_job_and_strips_tracking_links():
    digest = "Job alert for Europe\nManage: https://linkedin.com/jobs/alerts?token=secret\n\nPython role\nCompany A\nSpain\n\nView job: https://linkedin.com/jobs/view/123/?token=secret\n\n--------------------\n\n.NET Developer\nCompany B\nValencia\n\nEsta empresa busca personal activamente\nSolicitar con perfil y CV\nVer anuncio de empleo: https://linkedin.com/jobs/view/456/?token=private"
    result = analysis_evidence(
        {"id": "456", "title": "Job recommendation", "context": digest}
    )
    assert result["title"] == ".NET Developer"
    assert result["company"] == "Company B"
    assert "Valencia" in result["context"]
    assert "Spain" not in result["context"]
    assert "Python role" not in result["context"]
    assert "token=" not in result["context"]
    assert saved_job_details("456", "Job recommendation", digest) == (
        ".NET Developer",
        "Company B",
    )


def test_missing_target_excerpt_never_reuses_another_job():
    result = analysis_evidence(
        {
            "id": "999",
            "title": "Job recommendation",
            "context": "Python Madrid remote 100k https://linkedin.com/jobs/view/123/",
        }
    )
    assert "100k" not in result["context"]
    assert "unknown" in result["context"]


def test_isolated_html_card_keeps_its_evidence():
    result = analysis_evidence(
        {
            "id": "456",
            "title": ".NET Developer",
            "context": ".NET Developer\nRemote in Spain\nSalary 40k",
        }
    )
    assert "Salary 40k" in result["context"]


def test_preferences_are_sent_verbatim_and_unsupported_claims_are_unknown(
    tmp_path, monkeypatch
):
    import json
    import httpx
    from jobmatch.analysis import analyze
    from jobmatch.config import initialize

    monkeypatch.setenv("JOBMATCH_HOME", str(tmp_path))
    initialize()
    candidate = {
        "cv": "Candidate lives in Valencia",
        "preferences": "Only remote, at least 35k",
    }
    original = httpx.Client

    def handler(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json={})
        body = json.loads(request.content)
        assert json.loads(body["messages"][-1]["content"])["candidate"] == candidate
        assert "preference_checks" in body["format"]["required"]
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {
                            "score": 30,
                            "confidence": "low",
                            "reasons": ["Matching role"],
                            "concerns": [],
                            "missing_information": ["Salary"],
                            "preference_checks": [
                                {
                                    "preference": "35k minimum",
                                    "status": "met",
                                    "evidence": "Invented salary",
                                    "criterion": "salary",
                                    "job_quote": "Salary 50k",
                                }
                            ],
                        }
                    )
                }
            },
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    result = analyze(
        {"title": "Developer", "context": "Location unknown"}, candidate, "local:4b"
    )
    assert result.preference_checks[0].status == "unknown"
    assert result.preference_checks[0].job_quote is None
