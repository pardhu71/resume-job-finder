"""RoleRoute — educational MVP for resume uploads and role suggestions."""

from __future__ import annotations

import streamlit as st

from analyzer import (
    extract_resume_text,
    find_skills,
    google_job_search_url,
    suggest_roles,
)

st.set_page_config(
    page_title="RoleRoute | Resume-to-Job Finder",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    .block-container {padding-top: 2rem; max-width: 1050px;}
    .rr-eyebrow {color: #2563eb; font-size: .8rem; letter-spacing: .12em; font-weight: 750;}
    .rr-title {font-size: clamp(2.1rem, 4vw, 3.4rem); font-weight: 820; line-height: 1.08;
        letter-spacing: -.04em; margin: .5rem 0 .8rem;}
    .rr-lead {font-size: 1.08rem; color: #64748b; line-height: 1.65; margin-bottom: 1.3rem;}
    .rr-card {background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 16px;
        padding: 16px 18px; min-height: 105px;}
    .rr-card strong {display: block; margin-bottom: 6px; color: #0f172a;}
    .rr-card small {color: #64748b; line-height: 1.5;}
    .rr-footer {font-size: .83rem; color: #64748b; margin: 2.4rem 0 .5rem;}
</style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("## 🎯 RoleRoute")
    st.caption("Resume-to-Job Finder · Version 1")
    st.divider()
    st.markdown("**What works today**")
    st.write("✅ Upload PDF or DOCX resume")
    st.write("✅ Extract readable text")
    st.write("✅ Detect listed skills")
    st.write("✅ Suggest possible job roles")
    st.write("✅ Open a Google job search")
    st.markdown("**Coming next**")
    st.write("⏳ Fetch live job listings")
    st.write("⏳ AI agent with search tools")
    st.write("⏳ Verified job-by-job matching")
    st.divider()
    st.caption("Designed for Chrome and Edge. No account is required for this prototype.")

st.markdown('<div class="rr-eyebrow">VERSION 1 · WORKING PROTOTYPE</div>', unsafe_allow_html=True)
st.markdown('<div class="rr-title">Your next career move starts with your resume.</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="rr-lead">Upload a resume, discover the skills it mentions, '
    'and explore job titles you may want to research. No installation needed.</div>',
    unsafe_allow_html=True,
)

cols = st.columns(3)
for col, title, desc in zip(
    cols,
    ("01 · Upload", "02 · Explore", "03 · Search"),
    ("Choose a PDF or DOCX", "Review detected skills and roles", "Open job-search results in a new tab"),
):
    with col:
        st.markdown(
            f'<div class="rr-card"><strong>{title}</strong><small>{desc}</small></div>',
            unsafe_allow_html=True,
        )

st.write("")
st.subheader("1. Add a resume")
st.caption(
    "Prototype privacy notice: uploaded files are transmitted to the Streamlit server "
    "and processed in memory; this code does not intentionally save them to disk or a database. "
    "Use the sample resume for initial testing."
)

uploaded = st.file_uploader(
    "Choose your resume", type=["pdf", "docx"],
    help="PDF or modern Word (.docx), up to 5 MB. Scanned PDFs are not supported yet.",
)

if "use_demo" not in st.session_state:
    st.session_state.use_demo = False

if st.button("🧪 Try with a sample resume", help="Uses fictional information; no upload needed"):
    st.session_state.use_demo = True

SAMPLE_RESUME = """Sample Person — Entry-Level Data Analyst
Education: Bachelor's degree in Computer Science.
Skills: Python, SQL, Microsoft Excel, Pandas, Power BI, Git.
Projects: Built a sales dashboard in Power BI, used Python and Pandas to clean data,
and wrote SQL queries to analyze customer purchases.
"""

resume_text = ""
source = ""
if uploaded is not None:
    st.session_state.use_demo = False
    source = uploaded.name
    try:
        resume_text = extract_resume_text(uploaded.getvalue(), uploaded.name)
    except ValueError as exc:
        st.error(str(exc))
elif st.session_state.use_demo:
    source = "Fictional sample resume"
    resume_text = SAMPLE_RESUME

if resume_text:
    st.success(f"Resume text is ready: {source}")
    detected = find_skills(resume_text)
    roles = suggest_roles(detected, limit=5)

    st.subheader("2. Skills mentioned in the resume")
    st.caption("This is keyword detection, not a test of someone's actual proficiency.")
    if detected:
        st.markdown(" · ".join(f"`{skill}`" for skill in detected))
    else:
        st.info("We couldn't find skills from our starter dictionary. We will expand it in later versions.")

    with st.expander("See extracted resume text (optional)"):
        st.text_area("Extracted text", value=resume_text[:5000], height=180, disabled=True)

    st.subheader("3. Explore possible job roles")
    st.caption(
        "The percentages below measure overlap with a short example skill list. "
        "They are NOT chances of getting hired or assessments of job eligibility."
    )
    job_cols = st.columns(2)
    location = job_cols[0].text_input(
        "Preferred location (optional)", placeholder="e.g., Hyderabad, Bengaluru, Remote"
    )
    seniority = job_cols[1].selectbox(
        "Experience level", ["Any", "Fresher / entry-level", "1–3 years", "4+ years"],
    )

    if roles:
        for role in roles:
            with st.container(border=True):
                left, right = st.columns([4, 1])
                with left:
                    st.markdown(f"#### {role.title}")
                    st.caption("Detected overlap: " + ", ".join(role.found))
                with right:
                    st.metric("Skill overlap", f"{role.coverage_pct}%")
                st.progress(role.coverage_pct / 100)
                if role.missing:
                    st.caption("Example skills not mentioned: " + ", ".join(role.missing))
                st.link_button(
                    "🔎 Search the web for these jobs",
                    google_job_search_url(role.title, location, seniority),
                )
    else:
        st.info("No roles found yet. Try the sample resume to see the feature working.")

    st.info(
        "**What this version does not do:** It does not fetch or verify live job vacancies, "
        "calculate actual job-fit scores, or apply for jobs. The search buttons open "
        "ordinary Google searches. We will add job APIs and AI decisions in version 2."
    )
else:
    st.info("Upload a PDF/DOCX resume above, or click **Try with a sample resume** to explore the app.")

st.markdown(
    '<div class="rr-footer">RoleRoute v1 · Educational prototype · '
    'Always check job requirements and verify vacancies on official employer websites.</div>',
    unsafe_allow_html=True,
)
