import json

import streamlit as st

from jobmatch.analysis import fingerprint, profile
from jobmatch.config import home, initialize, settings
from jobmatch.storage import connect

st.set_page_config(page_title="JobMatch Local AI", layout="wide")
initialize()
st.title("JobMatch Local AI")
st.caption("Private email evidence • Local inference • No LinkedIn access")
db = connect()
try:
    rows = [
        dict(row) for row in db.execute("SELECT * FROM jobs ORDER BY first_seen DESC")
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
    search = st.text_input("Search title or email excerpt")
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
    digest = fingerprint(profile(), settings().model)
except RuntimeError:
    digest = None
    st.info("Add your CV and preferences to the private data directory before syncing.")
st.metric("Stored offers", len(rows))
items = []
for row in rows:
    result = json.loads(row["analysis"]) if row["analysis"] else None
    if search.lower() not in (row["title"] + row["context"]).lower():
        continue
    if result and result["score"] < minimum:
        continue
    if not result and not pending:
        continue
    items.append((row, result))
items.sort(key=lambda pair: pair[1]["score"] if pair[1] else -1, reverse=True)
if not items:
    st.info("No matching offers yet.")
for row, result in items:
    label = f"{result['score']}/100" if result else "Pending"
    with st.expander(f"{label} · {row['title']}"):
        st.text(row["url"])
        st.caption(f"First seen: {row['first_seen']} UTC")
        if result:
            st.write(f"Confidence: {result['confidence']}")
            if row["profile_hash"] != digest:
                st.warning(
                    "This analysis uses an older profile or model. Run sync to update it."
                )
            for field, title in [
                ("reasons", "Compatibility reasons"),
                ("concerns", "Concerns"),
                ("missing_information", "Missing information"),
            ]:
                st.write(title)
                for text in result[field]:
                    st.text(f"• {text}")
        if row["error"]:
            st.warning(f"Analysis failed: {row['error']}. Next sync will retry.")
        st.write("Email evidence")
        st.text(row["context"])
with st.expander("Recent synchronization runs"):
    st.dataframe(runs, width="stretch")
