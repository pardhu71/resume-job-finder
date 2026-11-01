"""RoleRoute v3 — discover public vacancies + transparent resume matching.

This version is an automated, rule-based workflow rather than an LLM agent.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import streamlit as st

from analyzer import extract_resume_text, find_skills, google_job_search_url, suggest_roles
from job_sources import (
    DEFAULT_BOARDS, JobSourceError, JobListing,
    fetch_greenhouse_jobs, fetch_lever_jobs, fetch_remotive_jobs,
    match_jobs, parse_board_names,
)

st.set_page_config(page_title="RoleRoute | AI Job Finder Prototype", page_icon="🎯", layout="wide")
st.markdown("""
<style>
.block-container { max-width: 1110px; padding-top: 2rem; }
.rr-eyebrow {letter-spacing: .12em; font-size: .80rem; font-weight: 800; color: #2563eb;}
.rr-title {font-size: clamp(2rem, 4vw, 3.3rem); font-weight: 800; line-height: 1.12;
 letter-spacing: -.035em; margin: .45rem 0 .8rem;}
.rr-subtitle {font-size: 1.08rem; line-height: 1.6; color: #64748b; margin: 0 0 1.4rem;}
.rr-card {border: 1px solid #e2e8f0; padding: 17px 19px; border-radius: 16px;
 background: #f8fafc; min-height: 100px;}
.rr-card strong {display: block; color: #0f172a; margin-bottom: 5px;}
.rr-card small {color: #475569; line-height: 1.5;}
.rr-footer {font-size: .80rem; color: #64748b; margin: 2rem 0 .5rem;}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("## 🎯 RoleRoute")
    st.caption("Resume-to-Job Finder · Version 3")
    st.divider()
    st.markdown("**Available now**")
    st.write("✅ Read PDF and DOCX resumes")
    st.write("✅ Suggest roles from detected skills")
    st.write("✅ Automatically choose public job sources")
    st.write("✅ India, international and remote filters")
    st.write("✅ Experience-aware relevance estimates")
    st.markdown("**Not yet included**")
    st.write("⏳ LLM-driven autonomous agent")
    st.write("⏳ All job boards worldwide")
    st.write("⏳ Verified eligibility / auto-applying")
    st.divider()
    st.caption("Early prototype. Please use fictional resumes for testing.")

st.markdown('<div class="rr-eyebrow">VERSION 3 · SMARTER JOB DISCOVERY</div>', unsafe_allow_html=True)
st.markdown('<div class="rr-title">Discover jobs that align with your resume.</div>', unsafe_allow_html=True)
st.markdown('<div class="rr-subtitle">Upload a resume, select your experience and preferred regions, then find ranked vacancies from selected public employer boards and a remote-jobs feed. Opens in Chrome and Edge.</div>', unsafe_allow_html=True)

for col, name, desc in zip(
    st.columns(3),
    ["01 · Read resume", "02 · Choose search", "03 · Compare jobs"],
    ["PDF or DOCX, with a sample included", "India + international + remote", "Skills, job requirements and direct links"],
):
    with col:
        st.markdown(f'<div class="rr-card"><strong>{name}</strong><small>{desc}</small></div>', unsafe_allow_html=True)

st.write("")
st.subheader("1. Upload a resume")
st.caption(
    "Privacy: uploaded files are transferred to Streamlit's hosting server and processed "
    "in memory by this app. The app does not intentionally store resumes or send them to job APIs. "
    "This prototype has NOT undergone a production privacy/security review. Use a fictional resume for testing."
)
uploaded = st.file_uploader("Choose PDF or DOCX (maximum 5 MB)", type=["pdf", "docx"])
if "use_demo" not in st.session_state:
    st.session_state.use_demo = False
if st.button("🧪 Use fictional sample resume"):
    st.session_state.use_demo = True

SAMPLE = """Fictional Applicant — Data Analyst Fresher
Education: B.Sc. Computer Science. Experience: 0 years.
Skills: Python, SQL, Excel, Pandas, Power BI, Git, Statistics.
Projects: Built data dashboards in Power BI, used SQL for customer analysis,
and automated reporting tasks in Python and Pandas.
"""
resume_text = ""
if uploaded is not None:
    st.session_state.use_demo = False
    try:
        resume_text = extract_resume_text(uploaded.getvalue(), uploaded.name)
    except ValueError as exc:
        st.error(str(exc))
elif st.session_state.use_demo:
    resume_text = SAMPLE

@st.cache_data(ttl=1200, show_spinner=False)
def get_board(provider: str, board: str) -> list[JobListing]:
    """Caches only public jobs, never users' resume text or personal information."""
    if provider == "Greenhouse":
        return fetch_greenhouse_jobs(board)
    return fetch_lever_jobs(board)

@st.cache_data(ttl=21600, show_spinner=False)
def get_remote_jobs() -> list[JobListing]:
    """Remotive recommends no more than ~4 API calls per day per process."""
    return fetch_remotive_jobs()

if not resume_text:
    st.info("Upload a resume or click **Use fictional sample resume** to begin.")
else:
    skills = find_skills(resume_text)
    suggestions = suggest_roles(skills, limit=6)
    st.success("Fictional sample loaded" if st.session_state.use_demo and uploaded is None else "Resume processed")
    st.subheader("2. Review your profile")
    st.caption("These are keyword detections, not verified credentials or proof of skills.")
    if skills:
        st.write("**Skills found:** " + ", ".join(skills))
    else:
        st.warning("No skills found in the starter dictionary; matching may be limited.")
    roles = [s.title for s in suggestions]
    if suggestions:
        with st.expander("Suggested roles (examples, not guaranteed fit)", expanded=True):
            for suggestion in suggestions:
                st.write(f"**{suggestion.title}** — {suggestion.coverage_pct}% overlap with an example role skill list")
    with st.expander("View extracted text (do not share this with others)"):
        st.text_area("Extracted resume", value=resume_text[:5000], height=150, disabled=True)

    st.subheader("3. Choose opportunities and run automatic search")
    a, b = st.columns(2)
    with a:
        scopes = st.multiselect(
            "Where should we look?", options=["India", "International", "Remote"],
            default=["India", "International", "Remote"],
            help="Remote jobs may be geographically restricted, even when listed as remote.",
        )
        city = st.text_input("Preferred city (optional)", placeholder="e.g. Hyderabad or Bengaluru")
        strict_city = st.checkbox("Require the exact city in the listing", value=False,
                                  help="Strict city matching can hide relevant nearby and remote jobs.")
    with b:
        years = st.number_input("Your years of professional experience", min_value=0, max_value=40, value=0, step=1)
        strict_exp = st.checkbox("Hide roles that appear to require more experience", value=True,
                                 help="Heuristic: checks explicit years and seniority words in job titles. Unknown requirements can still appear.")
        extra_role = st.text_input("Specific job role (optional)", placeholder="e.g. Data Analyst Intern")

    with st.expander("Advanced: add specific employer boards (optional)"):
        st.caption("The app chooses starting boards automatically. Extra boards are optional and must be valid public Greenhouse/Lever board IDs. Up to four per provider.")
        gh_extra = st.text_input("Additional Greenhouse board IDs", placeholder="company1, company2")
        lever_extra = st.text_input("Additional Lever board IDs", placeholder="company1, company2")

    st.caption(
        "Our starting source list contains selected employers with India and international openings; "
        "Remotive adds remote listings. This is not an exhaustive index of jobs in any country."
    )
    run_search = st.button("🔎 Automatically find matching jobs", type="primary", use_container_width=True)

    if run_search:
        if not scopes:
            st.warning("Select at least one search region.")
        else:
            try:
                extra_gh = parse_board_names(gh_extra)
                extra_lever = parse_board_names(lever_extra)
            except JobSourceError as exc:
                st.error(str(exc))
            else:
                sources: list[tuple[str, str]] = []
                for region in ("India", "International"):
                    if region in scopes:
                        sources.extend(("Greenhouse", board) for board in DEFAULT_BOARDS[region])
                sources += [("Greenhouse", board) for board in extra_gh]
                sources += [("Lever", board) for board in extra_lever]
                sources = list(dict.fromkeys(sources))
                if "Remote" in scopes:
                    sources.append(("Remotive", "remote-feed"))

                collected: list[JobListing] = []
                errors: list[str] = []
                if sources:
                    with st.spinner(f"Searching {len(sources)} public job sources... (a source may fail)"):
                        with ThreadPoolExecutor(max_workers=min(6, len(sources))) as executor:
                            pending = {
                                executor.submit(get_remote_jobs if provider == "Remotive" else get_board,
                                                *(() if provider == "Remotive" else (provider, board))): (provider, board)
                                for provider, board in sources
                            }
                            for future in as_completed(pending):
                                provider, board = pending[future]
                                try:
                                    collected.extend(future.result())
                                except JobSourceError:
                                    errors.append(f"{provider}/{board}: unavailable or access restricted")
                                except Exception:
                                    errors.append(f"{provider}/{board}: unexpected response")
                st.session_state.job_results_v3 = collected
                st.session_state.job_errors_v3 = errors
                st.session_state.job_sources_v3 = sources
                st.session_state.job_searched_v3 = True

    if st.session_state.get("job_searched_v3"):
        jobs = st.session_state.get("job_results_v3", [])
        errors = st.session_state.get("job_errors_v3", [])
        st.subheader("4. Job search results")
        st.caption(
            f"Retrieved {len(jobs)} public postings from selected job sources (before filtering and ranking). "
            "Open each source link to verify the job is still open and that you meet the requirements."
        )
        if errors:
            with st.expander(f"{len(errors)} source(s) unavailable — others can still work"):
                for message in errors:
                    st.warning(message)

        role_names = ([extra_role.strip()[:80]] if extra_role.strip() else []) + roles
        matches = match_jobs(
            jobs, skills, role_names, scopes=set(scopes),
            years_experience=int(years), strict_experience=strict_exp,
            preferred_city=city, strict_city=strict_city, limit=30,
        )
        if not matches:
            st.info(
                "No matches among the retrieved jobs with these settings. "
                "Try turning off the strict experience/city filter or using another role. "
                "This does NOT mean that no suitable jobs exist."
            )
        else:
            st.write(f"**Showing {len(matches)} potential matches** (highest estimated relevance first)")
            st.caption(
                "Relevance = role-title overlap (40%) + mentioned skills (35%) + experience hints (15%) "
                "+ location hints (10%). These scores are heuristics, NOT eligibility assessments "
                "or chances of being hired. Missing skills are detected words, not necessarily mandatory requirements."
            )
            for item in matches:
                job = item.job
                with st.container(border=True):
                    left, right = st.columns([4, 1])
                    left.subheader(job.title)
                    left.caption(f"{job.company} · {job.location} · Source: {job.source}")
                    right.metric("Est. relevance", f"{item.score}%")
                    st.progress(item.score / 100)
                    st.write("**Skills found in both:** " + (", ".join(item.matching_skills) or "None found"))
                    if item.missing_skills:
                        st.write("**Skills in listing not found in resume:** " + ", ".join(item.missing_skills))
                    st.caption("Experience: " + item.experience_note)
                    st.caption("Location: " + item.location_note)
                    if job.is_remote:
                        if item.remote_eligibility.startswith("Geographically restricted"):
                            st.warning("Remote location restriction: " + (job.candidate_location or "Check the original posting"))
                        else:
                            st.caption("Remote eligibility: " + item.remote_eligibility)
                    if job.last_updated:
                        label = "Published on feed" if job.source == "Remotive" else "Board last-updated field"
                        st.caption(f"{label}: {job.last_updated} (may not indicate current vacancy status)")
                    with st.expander("Read job description excerpt"):
                        st.write(job.description[:2000] if job.description else "This feed has no description.")
                    if job.source == "Remotive":
                        st.caption("Remote job provided by **Remotive** · Remotive's public API listings may be delayed by at least 24 hours.")
                    st.link_button(
                        "View on Remotive" if job.source == "Remotive" else "View original vacancy",
                        job.url,
                    )
        st.info(
            "**Important:** The app uses an automatic *rule-based* search and ranking workflow, "
            "not a generative AI model or autonomous LLM agent yet. It doesn't search every job site, "
            "guarantee qualifications, or apply for jobs automatically."
        )

st.markdown(
    '<div class="rr-footer">RoleRoute v3 · Free prototype · Source-aware matching · '
    'No resume submission to employers · Check every vacancy before applying.</div>',
    unsafe_allow_html=True,
)
