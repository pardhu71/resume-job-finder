"""RoleRoute v4 — multi-source public jobs + clearly labeled external discovery.

This version is an automated, rule-based workflow rather than an LLM agent.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter

import streamlit as st

from analyzer import extract_resume_text, find_skills, google_job_search_url, suggest_roles
from job_sources import (
    DEFAULT_BOARDS, EXTRA_DEFAULT_BOARDS, CAREER_PORTALS, JobSourceError, JobListing,
    fetch_greenhouse_jobs, fetch_lever_jobs, fetch_remotive_jobs,
    fetch_ashby_jobs, fetch_smartrecruiters_jobs, external_search_links,
    match_jobs, matching_diagnostics, parse_board_names,
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
    st.caption("Resume-to-Job Finder · Version 4")
    st.divider()
    st.markdown("**Available now**")
    st.write("✅ Read PDF and DOCX resumes")
    st.write("✅ Suggest roles from detected skills")
    st.write("✅ Public feeds: Greenhouse, Lever, Ashby & SmartRecruiters")
    st.write("✅ Indeed / Internshala / MNC search links")
    st.write("✅ India, international and remote filters")
    st.write("✅ Experience-aware relevance estimates")
    st.markdown("**Not yet included**")
    st.write("⏳ LLM-driven autonomous agent")
    st.write("⏳ Premium/private job-site feeds without permission")
    st.write("⏳ Verified eligibility / auto-applying")
    st.divider()
    st.caption("Early prototype. Please use fictional resumes for testing.")

st.markdown('<div class="rr-eyebrow">VERSION 4 · MORE SOURCES, MORE REACH</div>', unsafe_allow_html=True)
st.markdown('<div class="rr-title">Discover jobs that align with your resume.</div>', unsafe_allow_html=True)
st.markdown('<div class="rr-subtitle">Upload a resume and explore employer job feeds, India/international/remote roles, major company career sites, and job-platform searches. Works in Chrome and Edge.</div>', unsafe_allow_html=True)

for col, name, desc in zip(
    st.columns(3),
    ["01 · Read resume", "02 · Choose search", "03 · Compare jobs"],
    ["PDF or DOCX, with a sample included", "More job feeds + external websites", "Skills, experience, locations and direct links"],
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
    if provider == "Lever":
        return fetch_lever_jobs(board)
    if provider == "Ashby":
        return fetch_ashby_jobs(board)
    if provider == "SmartRecruiters":
        return fetch_smartrecruiters_jobs(board)
    raise JobSourceError("Unknown source provider")

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

    with st.expander("Advanced: include additional employer job boards (optional)"):
        st.caption(
            "The app chooses a curated starting set automatically. Add optional company identifiers "
            "from that company's public Greenhouse, Lever, Ashby or SmartRecruiters career page "
            "(up to four extra boards per provider). This is not an unrestricted global search."
        )
        gh_extra = st.text_input("Additional Greenhouse board IDs", placeholder="company1, company2")
        lever_extra = st.text_input("Additional Lever board IDs", placeholder="company1, company2")
        ashby_extra = st.text_input("Additional Ashby page names", placeholder="company1, company2")
        sr_extra = st.text_input("Additional SmartRecruiters company identifiers", placeholder="company1, company2")

    st.caption(
        "Automatic results come from selected, permitted public feeds. "
        "We also provide external searches for Indeed, Internshala and major company careers. "
        "A premium website cannot be unlocked by this app."
    )
    run_search = st.button("🔎 Automatically find matching jobs", type="primary", use_container_width=True)

    if run_search:
        if not scopes:
            st.warning("Select at least one search region.")
        else:
            try:
                extra_gh = parse_board_names(gh_extra)
                extra_lever = parse_board_names(lever_extra)
                extra_ashby = parse_board_names(ashby_extra)
                extra_sr = parse_board_names(sr_extra)
            except JobSourceError as exc:
                st.error(str(exc))
            else:
                sources: list[tuple[str, str]] = []
                for region in ("India", "International"):
                    if region in scopes:
                        sources.extend(("Greenhouse", board) for board in DEFAULT_BOARDS[region])
                        sources.extend(EXTRA_DEFAULT_BOARDS[region])
                sources += [("Greenhouse", board) for board in extra_gh]
                sources += [("Lever", board) for board in extra_lever]
                sources += [("Ashby", board) for board in extra_ashby]
                sources += [("SmartRecruiters", board) for board in extra_sr]
                sources = list(dict.fromkeys(sources))
                if "Remote" in scopes:
                    sources.append(("Remotive", "remote-feed"))

                collected: list[JobListing] = []
                errors: list[str] = []
                if sources:
                    with st.spinner(f"Searching {len(sources)} public job sources... (a source may fail)"):
                        with ThreadPoolExecutor(max_workers=min(8, len(sources))) as executor:
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
                st.session_state.job_results_v4 = collected
                st.session_state.job_errors_v4 = errors
                st.session_state.job_sources_v4 = sources
                st.session_state.job_searched_v4 = True

    if st.session_state.get("job_searched_v4"):
        jobs = st.session_state.get("job_results_v4", [])
        errors = st.session_state.get("job_errors_v4", [])
        st.subheader("4. Job search results")
        st.caption(
            f"Retrieved {len(jobs)} public postings from selected job sources (before filtering and ranking). "
            "Open each source link to verify the job is still open and that you meet the requirements."
        )
        provider_counts = Counter(job.source for job in jobs)
        if provider_counts:
            st.write("**Actual retrieved feed counts:** " + " · ".join(
                f"{provider}: {count}" for provider, count in sorted(provider_counts.items())
            ))
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
        diagnostics = matching_diagnostics(
            jobs, skills, role_names, scopes=set(scopes),
            years_experience=int(years), strict_experience=strict_exp,
            preferred_city=city, strict_city=strict_city,
        )
        with st.expander("Why were some jobs removed? View matching diagnostics", expanded=not matches):
            st.caption("Counts are sequential. The source list is limited and a filtering result is not an assessment of job availability.")
            count_cols = st.columns(3)
            for col, label, key in zip(count_cols, ("Retrieved", "After region filter", "After experience filter"), ("retrieved", "region", "experience")):
                col.metric(label, diagnostics[key])
            st.write(
                f"Distinct links: **{diagnostics['unique']}** · "
                f"After city setting: **{diagnostics['city']}** · "
                f"After relevance criteria: **{diagnostics['relevance']}**"
            )
            if diagnostics["region"] == 0:
                st.info("None of these source listings fell in the selected regions. Try selecting additional regions.")
            elif diagnostics["city"] == 0:
                st.info("The exact-city filter removed the remaining listings. Turn it off to explore other locations.")
            elif diagnostics["experience"] == 0:
                st.info("Experience requirements/seniority filters removed the remaining listings. You can turn off the strict experience filter, but always verify eligibility.")
            elif diagnostics["relevance"] == 0:
                st.info("No listings passed the role-title/skill relevance threshold. Try another role or explore broader results below.")

        if not matches:
            st.info(
                "No strong matches among the retrieved jobs with these settings. "
                "This does NOT mean that no suitable jobs exist. "
                "Try a different job title, fewer strict filters, or different job sources."
            )
            show_broader = st.checkbox(
                "Show broader exploratory results (may require more experience or have weak skill overlap)",
                value=False,
                help="These are leads to investigate, NOT suitable-job recommendations.",
            )
            if show_broader:
                exploratory = match_jobs(
                    jobs, skills, role_names, scopes=set(scopes),
                    years_experience=int(years), strict_experience=False,
                    preferred_city=city, strict_city=False, limit=8, exploratory=True,
                )
                if not exploratory:
                    st.warning("No exploratory leads in this small set of job sources either. Add more relevant public employer boards or try another role.")
                else:
                    st.warning("Exploratory leads are not verified matches. They may be senior, unsuitable for freshers, or restricted to other countries.")
                    for item in exploratory:
                        j = item.job
                        with st.container(border=True):
                            st.write(f"**{j.title}** — {j.company} · {j.location}")
                            st.caption(
                                f"Approximate relevance: {item.score}% · "
                                + item.experience_note + " · " + item.remote_eligibility
                            )
                            st.write("Overlapping resume skills: " + (", ".join(item.matching_skills) or "none detected"))
                            st.link_button("View original vacancy (check requirements)", j.url)
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
                    if not job.description.strip():
                        st.warning("This source did not supply a full job description. Relevance is based mostly on the title and location; verify the requirements on the employer site.")
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
                    job_button = (
                        "View on Remotive" if job.source == "Remotive" else
                        "Open company career board — find this job title" if
                        job.source == "SmartRecruiters" and job.url.startswith("https://careers.smartrecruiters.com/")
                        else "View original vacancy"
                    )
                    st.link_button(job_button, job.url)

        st.info(
            "**Important:** Only listings retrieved above have been processed for relevance. "
            "External website search results below are NOT fetched, reviewed or scored by this app. "
            "RoleRoute is currently rule-based, not an autonomous generative-AI agent."
        )

    st.subheader("5. Search more websites and company careers")
    st.caption(
        "These are human-initiated external searches. They may show additional jobs, but RoleRoute has "
        "NOT retrieved or verified them, and some websites require sign-in or a paid plan. "
        "We never send your resume text to these sites; only a role and optional city appear in search URLs."
    )
    role_for_search = extra_role.strip() or (roles[0] if roles else "entry level jobs")
    if len(role_for_search) > 80:
        role_for_search = role_for_search[:80]
    country_for_search = "India" if "India" in scopes else "Worldwide"
    links = external_search_links(role_for_search, city, country_for_search)
    for left, right in zip(links[::2], links[1::2]):
        a_col, b_col = st.columns(2)
        for col, (name, note, url) in ((a_col, left), (b_col, right)):
            with col:
                with st.container(border=True):
                    st.write(f"**{name}**")
                    st.caption(note)
                    st.link_button(f"Open {name}", url)
    with st.expander(f"Browse official company careers ({len(CAREER_PORTALS)} links)", expanded=False):
        st.caption(
            "Direct official portals. These links are not automatic vacancy retrieval. "
            "Use each company's own filters to check current openings and eligibility."
        )
        for i in range(0, len(CAREER_PORTALS), 3):
            cols = st.columns(3)
            for col, (name, url) in zip(cols, CAREER_PORTALS[i:i+3]):
                with col:
                    st.link_button(f"{name} careers", url, use_container_width=True)

st.markdown(
    '<div class="rr-footer">RoleRoute v4 · Free prototype · More permitted job feeds + external search links · '
    'No resume submission to employers · Check every vacancy before applying.</div>',
    unsafe_allow_html=True,
)
