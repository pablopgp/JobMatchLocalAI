import base64
from pathlib import Path

from streamlit.testing.v1 import AppTest

from jobmatch.config import initialize
from jobmatch.parsing import extract, saved_job_details
from jobmatch.storage import connect
from jobmatch.ui import compatibility_chart


def test_company_is_matched_to_the_correct_plain_text_offer():
    context = "Engineer A\nCompany A\nMadrid\n\nView job: https://www.linkedin.com/jobs/view/123/\n\nEngineer B\nCompany B\nBarcelona\n\nActively hiring\nView job: https://www.linkedin.com/jobs/view/456/"
    assert saved_job_details("123", "Job recommendation", context) == (
        "Engineer A",
        "Company A",
    )
    assert saved_job_details("456", "Job recommendation", context) == (
        "Engineer B",
        "Company B",
    )
    assert saved_job_details("789", "Original", context) == ("Original", None)


def test_html_card_is_preferred_over_plain_text_digest():
    html = '<div><a href="https://www.linkedin.com/jobs/view/123/">Engineer</a><a href="https://www.linkedin.com/company/acme/">Acme</a><p>Madrid</p></div>'
    message = {
        "payload": {
            "headers": [{"name": "From", "value": "jobs-noreply@linkedin.com"}],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {
                        "data": base64.urlsafe_b64encode(
                            b"https://www.linkedin.com/jobs/view/123/ Entire long digest "
                            * 20
                        ).decode()
                    },
                },
                {
                    "mimeType": "text/html",
                    "body": {"data": base64.urlsafe_b64encode(html.encode()).decode()},
                },
            ],
        }
    }
    job = extract(message)[0]
    assert job.title == "Engineer"
    assert job.company == "Acme"
    assert "Entire long digest" not in job.context


def test_chart_supports_zero_and_full_compatibility():
    import xml.etree.ElementTree as ET

    for score in (None, 0, 80, 100):
        svg = ET.fromstring(compatibility_chart(score))
        circles = svg.findall("{http://www.w3.org/2000/svg}circle")
        assert circles[1].attrib["stroke-dasharray"] == f"{score or 0} 100"
        labels = [node.text for node in svg.findall("{http://www.w3.org/2000/svg}text")]
        assert labels == [
            str(score) if score is not None else "Pending",
            "/ 100" if score is not None else "Not analyzed",
        ]


def test_preview_radials_use_saved_analysis_scores(tmp_path, monkeypatch):
    import json

    monkeypatch.setenv("JOBMATCH_HOME", str(tmp_path))
    initialize()
    analysis = json.dumps(
        {
            "score": 83,
            "confidence": "low",
            "reasons": ["Matching skills"],
            "concerns": [],
            "missing_information": [],
        }
    )
    with connect() as db:
        db.execute(
            "INSERT INTO jobs(id,title,url,context,analysis) VALUES ('1','Analyzed role','https://www.linkedin.com/jobs/view/1/','Evidence',?)",
            (analysis,),
        )
        db.execute(
            "INSERT INTO jobs(id,title,url,context) VALUES ('2','Pending role','https://www.linkedin.com/jobs/view/2/','Evidence')"
        )
    scores = []

    def capture(score):
        scores.append(score)
        return compatibility_chart(score)

    monkeypatch.setattr("jobmatch.ui.compatibility_chart", capture)
    app = AppTest.from_file(
        str(Path(__file__).parents[1] / "jobmatch" / "dashboard.py")
    ).run()
    app.checkbox[0].check().run()
    assert not app.exception
    assert scores == [83, None]
    assert len(app.get("imgs")) == 2


def test_saved_card_company_link_and_unknown_score(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBMATCH_HOME", str(tmp_path))
    initialize()
    with connect() as db:
        db.execute(
            "INSERT INTO jobs(id,title,url,context,company) VALUES ('123','Engineer','https://www.linkedin.com/jobs/view/123/?trk=email','Evidence','Acme')"
        )
        db.execute(
            "INSERT INTO jobs(id,title,url,context,company) VALUES ('456','Other role','javascript:alert(1)','Evidence',NULL)"
        )
    app = AppTest.from_file(
        str(Path(__file__).parents[1] / "jobmatch" / "dashboard.py")
    ).run()
    app.checkbox[0].check().run()
    assert not app.exception
    assert any(text.value == "Acme" for text in app.text)
    links = app.get("link_button")
    assert len(links) == 1
    assert links[0].proto.url == "https://www.linkedin.com/jobs/view/123/"
    assert any("Awaiting analysis" in info.value for info in app.info)
