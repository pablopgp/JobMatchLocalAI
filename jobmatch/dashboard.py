import json
import time
import hashlib

import streamlit as st

from jobmatch.analysis import fingerprint, profile
from jobmatch.config import home, initialize, settings
from jobmatch.storage import TRACKING_STATUSES, connect, update_offer, empty_trash
from jobmatch.parsing import canonical_job, saved_job_details
from jobmatch.ui import compatibility_chart
from jobmatch import manual_sync
from filelock import Timeout

st.set_page_config(page_title="JobMatch Local AI", layout="wide")
initialize()
cfg = settings()
since = (int(time.time()) - cfg.lookback_hours * 3600) * 1000
st.title("JobMatch Local AI")
st.caption("Your job recommendations, ranked for you. Private data and local analysis.")
with st.sidebar:
    st.subheader("Synchronization")
    st.caption(
        f"Retrieve new email and reanalyze all non-deleted offers recommended in the last {cfg.lookback_hours} hours. This may take several minutes."
    )
    if st.button(
        "Resynchronize all offers", disabled=manual_sync.is_running(), type="primary"
    ):
        try:
            if manual_sync.launch():
                st.success(
                    "Synchronization started in the background. Refresh to see progress."
                )
            else:
                st.info("Synchronization is already running.")
        except Timeout:
            st.info(
                "Another synchronization is already running. Try again after it finishes."
            )
        except OSError:
            st.error(
                "Could not start synchronization. Check the local Python environment."
            )
    if manual_sync.is_running():
        st.info("Synchronization in progress. You can continue browsing.")
    else:
        state = manual_sync.read_status()
        if state.get("status") in ("success", "partial"):
            st.caption(
                f"Last manual sync: {state['status']} · {state['messages']} new emails · {state['analyzed']} analyses · {state['errors']} errors"
            )
        elif state.get("status") == "failed":
            st.error(
                f"Last manual synchronization failed ({state['error']}). Check Gmail authorization and local Ollama, then retry."
            )

db = connect()
include_archive = st.sidebar.checkbox("Include older saved offers", value=False)
view = st.sidebar.radio("View", ["All offers", "Saved offers", "Trash"])
if view == "Trash":
    with st.sidebar:
        with st.expander("Empty trash"):
            st.warning(
                "Permanently removes all offers in Trash, including notes and analyses. This cannot be undone."
            )
            confirmed = st.checkbox(
                "I confirm permanent deletion", key="confirm_empty_trash"
            )
            if st.button("Empty trash permanently", disabled=not confirmed):
                count = empty_trash()
                st.session_state.pop("confirm_empty_trash", None)
                st.session_state["trash_notice"] = (
                    f"Permanently deleted {count} offers."
                )
                st.rerun()
        if "trash_notice" in st.session_state:
            st.success(st.session_state.pop("trash_notice"))
try:
    rows = [
        dict(row)
        for row in db.execute(
            "SELECT j.* FROM jobs j WHERE "
            "((?='Trash' AND deleted_at IS NOT NULL) OR (?!='Trash' AND deleted_at IS NULL)) "
            "AND (?!='Saved offers' OR saved=1) "
            "AND (? IN ('Saved offers','Trash') OR saved=1 OR ? OR EXISTS "
            "(SELECT 1 FROM message_jobs mj JOIN messages m ON m.id=mj.message_id "
            "WHERE mj.job_id=j.id AND m.received >= ?)) ORDER BY saved DESC, first_seen DESC",
            (view, view, view, view, include_archive, since),
        )
    ]
    runs = [
        dict(row) for row in db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 10")
    ]
    unparsed = db.execute(
        "SELECT COUNT(*) FROM messages WHERE status='no_jobs'"
    ).fetchone()[0]
finally:
    db.close()
with st.sidebar:
    st.subheader("Filters")
    search = st.text_input("Search role, company or keywords")
    minimum = st.slider("Minimum compatibility", 0, 100, 0)
    pending = st.checkbox("Show pending analysis", value=True)
    st.button("Refresh")
    st.caption(f"Private data: {home()}")
    st.caption(
        "Run jobmatch sync to retrieve new mail. Scheduling is independent of this panel."
    )
    if unparsed:
        st.warning(
            f"{unparsed} emails contained no recognized job links. Review the sender query or email format."
        )
try:
    active_profile = profile()
    digest = fingerprint(active_profile, settings().model)
    with st.sidebar.expander("Active professional preferences"):
        st.caption(str(home() / "preferences.txt"))
        st.text(active_profile["preferences"])
except RuntimeError:
    digest = None
    st.info("Add your CV and preferences to the private data directory before syncing.")
summary = st.columns(3)
summary[0].metric("Stored offers", len(rows))
summary[1].metric("Analyzed", sum(bool(row["analysis"]) for row in rows))
summary[2].metric("Awaiting analysis", sum(not row["analysis"] for row in rows))
outdated = sum(bool(row["analysis"]) and row["profile_hash"] != digest for row in rows)
if outdated:
    st.warning(
        f"{outdated} displayed analyses use older preferences or evaluation rules. Resynchronize all offers to update eligible scores."
    )
st.caption(
    "Saved offers remain available beyond the 24-hour window. Trash can be restored."
    if view != "All offers"
    else f"Showing offers received in the last {cfg.lookback_hours} hours, plus saved offers."
    if not include_archive
    else "Showing all saved offers."
)
items = []
for row in rows:
    inferred_title, inferred_company = saved_job_details(
        row["id"], row["title"], row["context"]
    )
    if row["title"] == "Job recommendation":
        row["title"] = inferred_title
    row["company"] = row.get("company") or inferred_company
    result = json.loads(row["analysis"]) if row["analysis"] else None
    if (
        search.lower()
        not in (row["title"] + (row["company"] or "") + row["context"]).lower()
    ):
        continue
    if result and result["score"] < minimum:
        continue
    if not result and not pending:
        continue
    items.append((row, result))
items.sort(key=lambda pair: pair[1]["score"] if pair[1] else -1, reverse=True)
if not items:
    st.info("No matching offers yet.")
page_count = max(1, (len(items) + 11) // 12)
page = st.selectbox(
    "Page",
    range(1, page_count + 1),
    format_func=lambda value: f"{value} of {page_count}",
)
st.caption(f"{len(items)} matching offers · Sorted by compatibility")
for row, result in items[(page - 1) * 12 : page * 12]:
    label = f"{result['score']}/100" if result else "Pending"
    card_key = "offer_" + hashlib.sha256(row["id"].encode()).hexdigest()[:16]
    if row["viewed"]:
        st.html(f"""<style>
        .st-key-{card_key} {{
            background-color:rgba(147,197,253,0.18);
            border-color:rgba(96,165,250,0.55);
            box-shadow:inset 3px 0 0 #93c5fd;
        }}
        </style>""")
    with st.container(border=True, key=card_key):
        chart_column, details_column = st.columns([1, 3])
        with chart_column:
            if result and row["profile_hash"] != digest:
                st.warning(
                    "Outdated analysis: preferences or evaluation rules have changed. Resynchronize to update this score."
                )
            st.image(
                compatibility_chart(result["score"] if result else None),
                width=190,
            )
            if result:
                st.caption(
                    f"Compatibility: {result['score']}/100 · Based on saved analysis"
                )
                st.caption("Indicative compatibility, not a hiring probability")
            else:
                st.info("Awaiting analysis")
        with details_column:
            st.subheader(row["title"])
            st.text(row["company"] or "Company not specified in the saved email")
            st.caption(f"Saved {row['first_seen']} UTC")
            job_id = canonical_job(row["url"])
            if job_id:
                st.link_button(
                    "Open offer on LinkedIn ↗",
                    f"https://www.linkedin.com/jobs/view/{job_id}/",
                    type="primary",
                )
            else:
                st.caption("Offer link unavailable")
            if result:
                st.caption(f"Confidence: {result['confidence'].capitalize()}")
                st.text(result["reasons"][0])
                st.caption(
                    f"{len(result['missing_information'])} unknown details · {len(result['concerns'])} concerns"
                )
            if row["saved"]:
                st.caption(f"Saved for follow-up · {row['tracking_status']}")
            actions = st.columns(3)
            if view == "Trash":
                if actions[0].button("Restore offer", key=f"restore_{row['id']}"):
                    update_offer(row["id"], deleted=False)
                    st.rerun()
                st.caption(
                    "Deleted offers stay out of synchronization. Restore them here if needed."
                )
            else:
                if actions[2].button(
                    "Viewed ✓" if row["viewed"] else "Mark as Viewed",
                    key=f"viewed_{row['id']}",
                    help="Toggle the viewed marker and light blue highlight.",
                ):
                    update_offer(row["id"], viewed=not row["viewed"])
                    st.rerun()
                if actions[0].button(
                    "Unsave offer" if row["saved"] else "Save offer",
                    key=f"save_{row['id']}",
                ):
                    update_offer(row["id"], saved=not row["saved"])
                    st.rerun()
                if actions[1].button(
                    "Delete offer",
                    key=f"delete_{row['id']}",
                    help="Move to Trash. You can restore it later.",
                ):
                    update_offer(row["id"], deleted=True)
                    st.rerun()
            if row["saved"] and view != "Trash":
                with st.expander("Follow-up status and notes"):
                    with st.form(f"tracking_{row['id']}"):
                        status = st.selectbox(
                            "Status",
                            TRACKING_STATUSES,
                            index=TRACKING_STATUSES.index(row["tracking_status"]),
                            key=f"status_{row['id']}",
                        )
                        notes = st.text_area(
                            "Private notes",
                            value=row["notes"],
                            max_chars=10000,
                            key=f"notes_{row['id']}",
                        )
                        if st.form_submit_button("Save follow-up"):
                            update_offer(row["id"], status=status, notes=notes)
                            st.rerun()
    with st.expander(f"{label} · {row['title']}"):
        st.text(row["url"])
        st.caption(f"First seen: {row['first_seen']} UTC")
        if result:
            st.write(f"Confidence: {result['confidence']}")
            if result.get("preference_checks"):
                st.write("Professional preference checks")
                st.dataframe(
                    result["preference_checks"], hide_index=True, width="stretch"
                )
            if row["profile_hash"] != digest:
                st.warning(
                    "This analysis uses an older profile or model. Run sync to update it."
                )
            for field, title in [
                ("reasons", "Matches"),
                ("concerns", "Incompatibilities and concerns"),
                ("missing_information", "Unknown information"),
            ]:
                st.write(title)
                for text in result[field]:
                    st.text(f"• {text}")
        if row["error"]:
            st.warning(f"Analysis failed: {row['error']}. Next sync will retry.")
            guidance = {
                "OllamaConnectionError": "Start the Ollama Windows application and check the local endpoint in settings.json.",
                "OllamaTimeoutError": "Check available memory and Ollama activity before retrying.",
                "OllamaResponseError": "Check that the configured model is installed and inspect Ollama's local logs.",
            }
            if row["error"] in guidance:
                st.info(guidance[row["error"]])
        st.write("Email evidence")
        st.text(row["context"])
with st.expander("Recent synchronization runs"):
    st.dataframe(runs, width="stretch")
