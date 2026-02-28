import streamlit as st
import requests
import pandas as pd

API_URL = "http://localhost:8000"

st.set_page_config(page_title="CaRMS Program Intelligence", layout="wide")

# ════════════════════════════════════════════════════════════════════
# Header + Summary
# ════════════════════════════════════════════════════════════════════
st.title("CaRMS Program Intelligence")

resp_summary = requests.get(f"{API_URL}/analytics/summary")
summary = resp_summary.json()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Programs", summary["total_programs"])
col2.metric("With Description", summary["with_description"])
col3.metric("Disciplines", summary["disciplines"])
col4.metric("Schools", summary["schools"])
col5.metric("Streams", summary["streams"])

st.divider()

# ════════════════════════════════════════════════════════════════════
# QA Section
# ════════════════════════════════════════════════════════════════════
st.header("Ask a Question")

question = st.text_input("Enter your question")

if st.button("Ask"):
    response = requests.post(
        f"{API_URL}/qa",
        json={"question": question}
    )
    data = response.json()
    st.subheader("Answer")
    st.write(data["answer"])
    st.subheader("Sources")
    st.write(data["sources"])

# ════════════════════════════════════════════════════════════════════
# Search Section
# ════════════════════════════════════════════════════════════════════
st.header("Search Programs")

s_col1, s_col2, s_col3, s_col4 = st.columns(4)
discipline = s_col1.text_input("Discipline")
school = s_col2.text_input("School")
stream = s_col3.text_input("Stream")
prog_id = s_col4.text_input("Program Stream ID")

if st.button("Search"):
    response = requests.get(
        f"{API_URL}/programs",
        params={
            "discipline": discipline,
            "school": school,
            "stream": stream,
            "program_stream_id": prog_id,
        }
    )
    programs = response.json()
    df = pd.DataFrame(programs)
    st.dataframe(df, use_container_width=True)

st.divider()

# ════════════════════════════════════════════════════════════════════
#  PROGRAM ANALYTICS
# ════════════════════════════════════════════════════════════════════
st.title("Program Analytics")

# ── Distribution by Discipline / School / Stream ───────────────────
st.header("Program Distribution")

tab_disc, tab_school, tab_stream = st.tabs(["By Discipline", "By School", "By Stream"])

with tab_disc:
    resp = requests.get(f"{API_URL}/analytics/discipline-count")
    df_disc = pd.DataFrame(resp.json())
    if not df_disc.empty:
        st.bar_chart(df_disc.set_index("discipline"))

with tab_school:
    resp = requests.get(f"{API_URL}/analytics/school-count")
    df_sch = pd.DataFrame(resp.json())
    if not df_sch.empty:
        st.bar_chart(df_sch.set_index("school"))

with tab_stream:
    resp = requests.get(f"{API_URL}/analytics/stream-count")
    df_str = pd.DataFrame(resp.json())
    if not df_str.empty:
        st.bar_chart(df_str.set_index("stream"))

# ── Citizenship Mentions ───────────────────────────────────────────
st.header("Programs Mentioning Canadian Citizenship")

resp_cit = requests.get(f"{API_URL}/analytics/citizenship-mentions")
cit_data = resp_cit.json()
total = summary["total_programs"]

st.metric(
    "Programs mentioning citizenship / permanent residency",
    cit_data["total"],
    f"{cit_data['total'] / total * 100:.1f}% of {total} programs",
)

tab_cit_disc, tab_cit_sch, tab_cit_list = st.tabs([
    "By Discipline", "By School", "Full List"
])

with tab_cit_disc:
    resp = requests.get(f"{API_URL}/analytics/citizenship-by-discipline")
    df_cd = pd.DataFrame(resp.json())
    if not df_cd.empty:
        st.bar_chart(df_cd.set_index("discipline"))

with tab_cit_sch:
    resp = requests.get(f"{API_URL}/analytics/citizenship-by-school")
    df_cs = pd.DataFrame(resp.json())
    if not df_cs.empty:
        st.bar_chart(df_cs.set_index("school"))

with tab_cit_list:
    if cit_data["programs"]:
        st.dataframe(pd.DataFrame(cit_data["programs"]), use_container_width=True)
    else:
        st.info("No programs mention Canadian citizenship.")

# ── Interview Process Analytics ────────────────────────────────────
st.header("Interview Process")

# Interview Dates
st.subheader("Interview Dates")
st.caption("Number of programs conducting interviews on each date")

resp_dates = requests.get(f"{API_URL}/analytics/interview-dates")
dates_data = resp_dates.json()
if dates_data:
    df_dates = pd.DataFrame(dates_data)
    st.bar_chart(df_dates.set_index("date"))
else:
    st.info("No interview date data found.")

# Applications Received
st.subheader("Average Applications Received (last 5 years)")

resp_apps = requests.get(f"{API_URL}/analytics/applications-received")
apps_data = resp_apps.json()

tab_apps_all, tab_apps_disc = st.tabs(["Overall", "By Discipline"])

with tab_apps_all:
    if apps_data:
        df_apps = pd.DataFrame(apps_data)
        st.bar_chart(df_apps.set_index("range"))
    else:
        st.info("No data.")

with tab_apps_disc:
    resp = requests.get(f"{API_URL}/analytics/applications-received-by-discipline")
    ad = resp.json()
    if ad:
        df_ad = pd.DataFrame(ad)
        pivot = df_ad.pivot_table(
            index="discipline", columns="range", values="count", fill_value=0
        )
        ordered = [c for c in ["0 - 50", "51 - 200", "201 - 400", "401 - 600", "601 +"] if c in pivot.columns]
        st.dataframe(pivot[ordered], use_container_width=True)
    else:
        st.info("No data.")

# Interview Offer Percentage
st.subheader("Average % of Applicants Offered Interviews")

resp_pct = requests.get(f"{API_URL}/analytics/interview-offer-pct")
pct_data = resp_pct.json()

tab_pct_all, tab_pct_disc = st.tabs(["Overall", "By Discipline"])

with tab_pct_all:
    if pct_data and pct_data.get("distribution"):
        df_pct = pd.DataFrame(pct_data["distribution"])
        st.bar_chart(df_pct.set_index("range")[["count"]])
        st.caption(f"Based on {pct_data['total_programs']} programs that report this metric")
    else:
        st.info("No data.")

with tab_pct_disc:
    resp = requests.get(f"{API_URL}/analytics/interview-offer-pct-by-discipline")
    pd_data = resp.json()
    if pd_data:
        df_pd = pd.DataFrame(pd_data)
        pivot = df_pd.pivot_table(
            index="discipline", columns="range", values="count", fill_value=0
        )
        ordered = [c for c in ["0 - 25 %", "26 - 50 %", "51 - 75 %", "76 - 100 %"] if c in pivot.columns]
        st.dataframe(pivot[ordered], use_container_width=True)
    else:
        st.info("No data.")

# Interview Evaluation Criteria
st.subheader("Interview Evaluation Criteria")

tab_crit_all, tab_crit_disc = st.tabs(["Overall", "By Discipline"])

with tab_crit_all:
    resp = requests.get(f"{API_URL}/analytics/interview-criteria")
    crit = resp.json()
    if crit:
        df_crit = pd.DataFrame(crit).set_index("criterion")
        st.bar_chart(df_crit)
        st.caption("Evaluated vs Not Evaluated across all programs with criteria section")
    else:
        st.info("No data.")

with tab_crit_disc:
    resp = requests.get(f"{API_URL}/analytics/interview-criteria-by-discipline")
    cd = resp.json()
    if cd:
        df_cd = pd.DataFrame(cd)
        pivot = df_cd.pivot_table(
            index="discipline", columns="criterion", values="count", fill_value=0
        )
        st.dataframe(pivot, use_container_width=True)
    else:
        st.info("No data.")

st.divider()

# ════════════════════════════════════════════════════════════════════
#  DATA HEALTH
# ════════════════════════════════════════════════════════════════════
st.title("Data Health")
st.caption("Metrics about data completeness and change tracking")

# ── Description Coverage ───────────────────────────────────────────
st.header("Description Field Coverage")

resp_cov = requests.get(f"{API_URL}/analytics/description-coverage")
cov_data = resp_cov.json()

if cov_data:
    df_cov = pd.DataFrame(cov_data["sections"])
    st.metric("Total Programs", cov_data["total_programs"])

    # Horizontal bar-style display
    for _, row in df_cov.iterrows():
        st.progress(
            row["pct"] / 100,
            text=f"{row['field']}: {row['count']} / {cov_data['total_programs']} ({row['pct']}%)"
        )
else:
    st.info("No coverage data.")

# ── Change Tracking ────────────────────────────────────────────────
st.header("Description Change Tracking")

tab_timeline, tab_recent, tab_most = st.tabs([
    "Changes Over Time", "Recent Changes", "Most Changed Programs"
])

with tab_timeline:
    resp = requests.get(f"{API_URL}/analytics/changes-over-time")
    cot = resp.json()
    if cot:
        df_cot = pd.DataFrame(cot)
        st.bar_chart(df_cot.set_index("date"))
    else:
        st.info("No change history yet. Changes are recorded when the pipeline detects description updates.")

with tab_recent:
    resp = requests.get(f"{API_URL}/analytics/recent-changes")
    rc = resp.json()
    if rc:
        st.dataframe(pd.DataFrame(rc), use_container_width=True)
    else:
        st.info("No changes recorded yet.")

with tab_most:
    resp = requests.get(f"{API_URL}/analytics/most-changed-programs")
    mc = resp.json()
    if mc:
        df_mc = pd.DataFrame(mc)
        st.bar_chart(df_mc.set_index("program_stream_id"))
    else:
        st.info("No changes recorded yet.")
