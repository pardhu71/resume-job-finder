"""RoleRoute Version 2: resume analysis + public employer job listings."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import streamlit as st

from analyzer import (
    extract_resume_text,
    find_skills,
    google_job_search_url,
    suggest_roles,
)
from job_sources import (
    JobSourceError,
    fetch_greenhouse_jobs,
    fetch_lever_jobs,
    match_jobs,
    parse_board_names,
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
    .block-container {padding-top: 2rem; max-width: 1060px;}
    .rr-eyebrow {color: #2563eb; font-size: .82rem; letter-spacing: .10em; font-weight: 750;}
    .rr-title {font-size: clamp(2.1rem, 4vw, 3.2rem); font-weight: 820; line-height: 1.1;
        letter-spacing: -.035em; margin: .5rem 0 .8rem;}
    .rr-lead {font-size: 1.05rem; color: #64748b; line-height: 1.6; margin-bottom: 1.2rem;}
    .rr-card {background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 14px;
        padding: 16px 18px; min-height: 95px;}
    .rr-card strong {display: block; margin-bottom: 6px; color: #0f172a;}
    .rr-card small {color: #64748b; line-height: 1.45;}
    .rr-footer {font-size: .83rem; color: #64748b; margin: 2.2rem 0 .4rem;}
</style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("## 🎯 RoleRoute")
    st.caption("Resume-to-Job Finder · Version 2")
    st.divider()
    st.markdown("**Ready now**")
    st.write("✅ Read PDF or DOCX")
    st.write("✅ Detect resume keywords")
    st.write("✅ Suggest possible job roles")
    st.write("✅ Fetch jobs from selected employer boards")
    st.write("✅ Show explainable relevance estimates")
    st.markdown("**Future improvements**")
    st.write("⏳ More employers and regions")
    st.write("⏳ AI-driven search and refinement")
    st.write("⏳ Privacy and security assessment for production")
    st.divider()
    st.caption("Educational prototype. Do not use real personal resumes for testing yet.")

st.markdown('<div class="rr-eyebrow">VERSION 2 · EMPLOYER JOB-BOARD SEARCH</div>', unsafe_allow_html=True)
st.markdown('<div class="rr-title">Find jobs that fit your resume.</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="rr-lead">Upload a resume, discover potential roles, and search '
    'selected employers’ published job listings. No installation required.</div>',
    unsafe_allow_html=True,
)

for col, title, desc in zip(
    st.columns(3),
    ("01 · Upload", "02 · Analyze", "03 · Find jobs"),
    ("Choose PDF or DOCX", "See detected skills and job roles", "Search selected public employer feeds"),
):
    with col:
        st.markdown(
            f'<div class="rr-card"><strong>{title}</strong><small>{desc}</small></div>',
            unsafe_allow_html=True,
        )

st.write("")
st.subheader("1. Add a resume")
st.caption(
    "Privacy notice: uploads are transferred to Streamlit's server and parsed in memory. "
    "This code does not intentionally save resumes to a file or database and does not send "
    "resume text to job providers. This is NOT a production privacy/security guarantee. "
    "Use the fictional sample resume for initial testing."
)

uploaded = st.file_uploader(
    "Choose a resume", type=["pdf", "docx"],
    help="PDF or Word (.docx), up to 5 MB. Image-only/scanned PDFs are not supported.",
)

if "use_demo" not in st.session_state:
    st.session_state.use_demo = False
if st.button("🧪 Try with a fictional sample resume"):
    st.session_state.use_demo = True

SAMPLE_RESUME = """Sample Person — Entry-Level Data Analyst
Education: Bachelor's degree in Computer Science.
Skills: Python, SQL, Microsoft Excel, Pandas, Power BI, Git.
Projects: Built a sales dashboard in Power BI, cleaned datasets using Python
and Pandas, and wrote SQL queries for customer analysis.
"""

resume_text = ""
if uploaded is not None:
    st.session_state.use_demo = False
    try:
        resume_text = extract_resume_text(uploaded.getvalue(), uploaded.name)
    except ValueError as exc:
        st.error(str(exc))
elif st.session_state.use_demo:
    resume_text = SAMPLE_RESUME

@st.cache_data(ttl=600, show_spinner=False)
def get_public_board(provider: str, board: str):
    """Cache public company vacancies only; no resume, identity, or user data."""
    if provider == "Greenhouse":
        return fetch_greenhouse_jobs(board)
    return fetch_lever_jobs(board)


if resume_text:
    st.success("Resume text extracted successfully" if uploaded else "Fictional sample resume loaded")
    skills = find_skills(resume_text)
    roles = suggest_roles(skills, limit=5)

    st.subheader("2. Skills and suitable roles")
    st.caption("Keywords are not proof of expertise. Roles are suggestions, not hiring decisions.")
    if skills:
        st.markdown("**Detected:** " + " · ".join(f"`{skill}`" for skill in skills))
    else:
        st.warning("No skills were recognized from our limited starter dictionary.")

    with st.expander("View extracted resume text"):
        st.text_area("Text", value=resume_text[:5000], disabled=True, height=170)

    col_loc, col_level = st.columns(2)
    location = col_loc.text_input("Preferred city or country (optional)", placeholder="e.g. Hyderabad, India")
    level = col_level.selectbox("Experience level", ["Any", "Fresher / entry-level", "1–3 years", "4+ years"])

    if roles:
        with st.expander("See suggested roles and skill overlaps", expanded=True):
            for role in roles:
                left, right = st.columns([4, 1])
                left.markdown(f"**{role.title}**")
                left.caption("Skills in example role profile: " + ", ".join(role.found))
                right.metric("Role overlap", f"{role.coverage_pct}%")
                st.progress(role.coverage_pct / 100)
                st.link_button("Google search", google_job_search_url(role.title, location, level))
                st.divider()
        st.caption("Role overlap uses example role profiles, not actual employer requirements.")
    else:
        st.info("Try the fictional resume if you want to see example role suggestions.")

    st.subheader("3. Search published jobs from selected employers")
    st.caption(
        "This searches only company boards you specify, not every job website. "
        "Employer job feeds can change, restrict access, or return no suitable listings."
    )

    with st.expander("Which employers should we search?", expanded=True):
        a, b = st.columns(2)
        gh_input = a.text_input("Greenhouse board IDs", value="figma, notion, ramp",
                                help="Comma-separated employer board IDs; examples may change or be unavailable.")
        lever_input = b.text_input("Lever board IDs", value="lever",
                                   help="Comma-separated employer site names; examples may change.")
        st.caption(
            "These are illustrative company-board identifiers, not a guaranteed list of accessible sources. "
            "You can replace them with board IDs from public Greenhouse or Lever career pages. "
            "Up to 5 boards per provider."
        )
    extra = st.text_input("Optional additional role or keyword", placeholder="e.g. Data Analyst Intern")
    location_only = st.checkbox("Only show jobs whose location contains my preferred city/country", value=False,
                                disabled=not bool(location.strip()))
    st.caption("Leave the location filter off to include other locations. Remote jobs may have country restrictions.")

    if st.button("🔎 Find published jobs", type="primary", use_container_width=True):
        try:
            sources = [("Greenhouse", c) for c in parse_board_names(gh_input)] + [
                ("Lever", c) for c in parse_board_names(lever_input)
            ]
        except JobSourceError as exc:
            st.error(str(exc))
            sources = []
        if sources:
            fetched = []
            errors = []
            with st.spinner("Checking selected company job boards..."):
                with ThreadPoolExecutor(max_workers=min(5, len(sources))) as pool:
                    work = {pool.submit(get_public_board, provider, board): (provider, board)
                            for provider, board in sources}
                    for future in as_completed(work):
                        provider, board = work[future]
                        try:
                            fetched.extend(future.result())
                        except JobSourceError as exc:
                            errors.append(f"{provider} / {board}: {exc}")
                        except Exception:
                            errors.append(f"{provider} / {board}: unexpected response; try another board.")
            st.session_state.public_job_results = fetched
            st.session_state.public_job_errors = errors
            st.session_state.public_job_sources = sources
        else:
            st.info("Enter at least one employer board ID to search.")

    if "public_job_results" in st.session_state:
        all_jobs = st.session_state.public_job_results
        st.caption(
            f"Retrieved {len(all_jobs)} postings from selected sources (maximum 200 per board). "
            "Listings should be independently checked on employer sites before applying."
        )
        for error in st.session_state.get("public_job_errors", []):
            st.warning(error)
        search_roles = [role.title for role in roles]
        if extra.strip():
            search_roles.insert(0, extra.strip()[:80])
        matches = match_jobs(
            all_jobs, skills, search_roles,
            location=location,
            entry_level_only=(level == "Fresher / entry-level"),
            filter_location=location_only,
            limit=25,
        )
        if matches:
            st.markdown(f"### {len(matches)} possible matches")
            st.caption(
                "Estimated relevance score = role-title similarity + listed skill keywords + optional location. "
                "It is not a hiring probability or a verification of all eligibility requirements."
            )
            for match in matches:
                job = match.job
                with st.container(border=True):
                    col_info, col_score = st.columns([4, 1])
                    col_info.markdown(f"#### {job.title}")
                    col_info.caption(f"{job.company} · {job.location} · {job.source}")
                    col_score.metric("Relevance", f"{match.score}%")
                    st.progress(match.score / 100)
                    st.write("**Resume skills also mentioned in listing:** " +
                             (", ".join(match.matching_skills) if match.matching_skills else "None detected"))
                    if job.last_updated:
                        st.caption(f"Board's last-update field: {job.last_updated} (not necessarily the posting date)")
                    with st.expander("Job description excerpt"):
                        st.write(job.description[:1800] if job.description else "No description supplied by this board.")
                    st.link_button("View job on employer website", job.url)
        else:
            st.info(
                "No matching jobs were identified in the selected boards. Try another employer, "
                "a different role, or remove the strict location filter. This does not mean no jobs exist."
            )
        st.info(
            "**Limitations:** This prototype does not access every employer, verify eligibility or vacancy status, "
            "run an autonomous AI model, or submit applications. Check all requirements on the employer's site."
        )
else:
    st.info("Upload a PDF/DOCX resume or click **Try with a fictional sample resume** above.")

st.markdown(
    '<div class="rr-footer">RoleRoute v2 · Educational prototype · '
    'Vacancy sources: selected public employer feeds · No automatic job applications.</div>',
    unsafe_allow_html=True,
)
