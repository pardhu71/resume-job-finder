"""RoleRoute v5 — dynamic resume-to-vacancy comparison + optional bounded AI agent.

Uses permitted employer feeds only. No prebuilt job-title role taxonomy; all
role matching comes from resume evidence and actual listings.
"""
from __future__ import annotations
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
import html

import streamlit as st

from analyzer import extract_resume_text
from job_sources import (
    DEFAULT_BOARDS, EXTRA_DEFAULT_BOARDS, CAREER_PORTALS, JobListing, JobSourceError,
    fetch_greenhouse_jobs, fetch_lever_jobs, fetch_remotive_jobs,
    fetch_ashby_jobs, fetch_smartrecruiters_jobs, external_search_links,
    parse_board_names, valid_job_url,
)
from matching_engine import (extract_resume_skills, resume_focus, rank_jobs,
                             evaluate_job, safe_llm_profile)
from llm_agent import plan_search, explain_job_matches, AgentError

st.set_page_config(page_title='RoleRoute V5 | Resume-to-Job Agent', page_icon='🎯', layout='wide')
st.markdown('''<style>
.block-container{max-width:1130px;padding-top:1.9rem}
.eyebrow{color:#2563eb;font-size:.82rem;font-weight:800;letter-spacing:.1em}
.hero{font-weight:820;font-size:clamp(2rem,4vw,3rem);line-height:1.2;margin:.3rem 0 .6rem}
.desc{font-size:1.07rem;color:#65748b;margin-bottom:1.1rem}
</style>''', unsafe_allow_html=True)

with st.sidebar:
    st.title('🎯 RoleRoute')
    st.caption('Resume-to-Job Finder · Version 5')
    st.divider()
    st.success('Live job feed search + description-based matching')
    st.write('✅ No predefined list of job roles')
    st.write('✅ Requirement-by-requirement evidence')
    st.write('✅ India, worldwide, and remote sources')
    st.write('✅ Optional Gemini AI planning and review')
    st.write('✅ User-approved manual application links')
    st.warning('Not included: unauthorized premium feed access, guaranteed eligibility, or automatic submissions.')
    st.caption('Prototype: use fictional resumes until privacy and security review.')

st.markdown('<div class="eyebrow">VERSION 5 · DYNAMIC CAREER MATCHING</div>', unsafe_allow_html=True)
st.markdown('<div class="hero">Find jobs using your resume — not a fixed job-role list.</div>', unsafe_allow_html=True)
st.markdown('<div class="desc">We compare the candidate’s actual skills and interests with employer job descriptions. Optional AI planning helps decide which sources to check and explains candidate fit.</div>', unsafe_allow_html=True)

st.subheader('1. Add a resume')
st.caption('Uploaded files reach the Streamlit server. Public job feeds never receive your resume. If you enable optional Gemini, a limited, partially redacted skill/focus summary is sent to Google with your consent; free-tier data may be used to improve Google products. Do not upload sensitive personal documents to this prototype.')
uploaded = st.file_uploader('PDF or DOCX (maximum 5 MB)', type=['pdf', 'docx'])
col_demo1, col_demo2 = st.columns(2)
with col_demo1:
    if st.button('🧪 Fictional Embedded Systems resume', use_container_width=True):
        st.session_state.demo_resume = 'embedded'
with col_demo2:
    if st.button('🧪 Fictional Data Analyst resume', use_container_width=True):
        st.session_state.demo_resume = 'data'
SAMPLE_EMBEDDED = '''Fictional Embedded Engineering Graduate\nEducation: B.Tech Electronics. Experience: 0 years.\nSkills: Embedded C, C++, STM32, ESP32, FreeRTOS, UART, SPI, I2C, Microcontrollers, Git, Linux, Python\nProjects: Built sensor logging firmware for STM32 microcontrollers in Embedded C. Implemented SPI communication and FreeRTOS tasks on an ESP32.\nInterested in firmware engineering and embedded software development.\n'''
SAMPLE_DATA = '''Fictional Data Analytics Graduate\nEducation: B.Sc Computer Science. Experience: 0 years.\nSkills: Python, SQL, Excel, Power BI, Pandas, Statistics, Git\nProjects: Analyzed sales data with SQL and Python. Built data analyst dashboards with Power BI and Pandas.\nInterested in data analysis and business intelligence roles.\n'''
resume = ''
if uploaded is not None:
    try:
        resume = extract_resume_text(uploaded.getvalue(), uploaded.name)
    except ValueError as exc:
        st.error(str(exc))
elif st.session_state.get('demo_resume'):
    resume = SAMPLE_EMBEDDED if st.session_state.demo_resume == 'embedded' else SAMPLE_DATA

@st.cache_data(ttl=1800, show_spinner=False)
def get_feed(provider: str, board: str) -> list[JobListing]:
    # Only public job source data is cached, never user resume content.
    functions = {'Greenhouse': fetch_greenhouse_jobs, 'Lever': fetch_lever_jobs,
                 'Ashby': fetch_ashby_jobs, 'SmartRecruiters': fetch_smartrecruiters_jobs}
    if provider not in functions:
        raise JobSourceError('Unsupported job source')
    return functions[provider](board)

@st.cache_data(ttl=21600, show_spinner=False)
def get_remote() -> list[JobListing]:
    return fetch_remotive_jobs()


def find_sources(scopes: set[str], extra: dict[str, list[str]]) -> list[tuple[str, str]]:
    result = []
    for region in ('India', 'International'):
        if region in scopes:
            result += [('Greenhouse', b) for b in DEFAULT_BOARDS[region]]
            result += EXTRA_DEFAULT_BOARDS[region]
    for provider, boards in extra.items():
        result += [(provider, board) for board in boards]
    if 'Remote' in scopes:
        result.append(('Remotive', 'remote-feed'))
    return list(dict.fromkeys(result))


def fetch_sources(sources: list[tuple[str, str]]) -> tuple[list[JobListing], list[str]]:
    data, errors = [], []
    if not sources:
        return data, errors
    with ThreadPoolExecutor(max_workers=min(8, len(sources))) as pool:
        pending = {pool.submit(get_remote if provider == 'Remotive' else get_feed,
                               *(() if provider == 'Remotive' else (provider, board))): (provider, board)
                   for provider, board in sources}
        for future in as_completed(pending):
            provider, board = pending[future]
            try:
                data.extend(future.result())
            except Exception:
                errors.append(f'{provider}/{board}: not available or temporarily restricted')
    return data, errors


def display_match(item, ai_notes: dict | None = None) -> None:
    job = item.job
    with st.container(border=True):
        a, b = st.columns([5, 1])
        a.markdown(f'#### {job.title}')
        a.caption(f'{job.company} · {job.location} · {job.source}')
        b.metric('Fit estimate', f'{item.score}%')
        st.caption('Fit estimate is a heuristic, not hiring probability, eligibility, or employer ATS score.')
        st.progress(item.score / 100)
        if item.found_required:
            st.write('**Required skills evidenced in resume:** ' + ', '.join(item.found_required))
        if item.missing_required:
            st.warning('**Mentioned as required but not evidenced in resume:** ' + ', '.join(item.missing_required))
        if item.found_preferred:
            st.write('**Preferred skills evidenced:** ' + ', '.join(item.found_preferred))
        if item.missing_preferred:
            st.caption('Preferred skills not found in resume: ' + ', '.join(item.missing_preferred))
        if item.found_mentioned:
            st.caption('Other shared technical terms: ' + ', '.join(item.found_mentioned))
        if item.role_evidence:
            st.caption('Resume-focus terms found in job title: ' + ', '.join(item.role_evidence))
        st.caption('Experience: ' + item.experience_note)
        st.caption('Location: ' + item.location_note)
        for message in item.warnings:
            st.caption('⚠️ ' + message)
        if ai_notes:
            st.info(f'**AI second opinion — {ai_notes["fit"]}:** {ai_notes["reason"]}\n\nCheck: {ai_notes["needs_check"]}')
        with st.expander('Show source job description (excerpt)'):
            st.write(job.description[:3500] if job.description else 'This feed did not supply a full description.')
        if job.last_updated:
            st.caption(f'Feed date: {job.last_updated} (not proof the position is still open)')
        if valid_job_url(job.url):
            st.link_button('🔗 View employer job page / Apply manually', job.url)
        with st.expander('Application readiness checklist (user verification required)'):
            st.caption('These checks are for the applicant to verify; RoleRoute cannot certify eligibility.')
            checks = [
                'I checked this job is still open on the official site',
                'I reviewed mandatory skills and degree requirements',
                'I reviewed minimum experience and seniority requirements',
                'I checked country, remote-work and work-authorization conditions',
                'I consent to opening the external application page myself',
            ]
            identity = sha256((job.url + job.job_id + job.title).encode()).hexdigest()[:14]
            ticked = [st.checkbox(label, key=f'{identity}_{idx}') for idx, label in enumerate(checks)]
            if all(ticked):
                st.success('Checklist completed by applicant. This is not verified eligibility or an application submission.')
        st.caption('RoleRoute does not log in, submit your resume, or apply for you. Verify opening status and requirements before applying.')

if not resume:
    st.info('Start by using a fictional resume above, then test the matching process.')
else:
    st.success('Resume text loaded')
    st.subheader('2. Review candidate evidence')
    skills = extract_resume_skills(resume)
    st.write('**Skills extracted from the resume:** ' + (', '.join(skills) if skills else 'No skills confidently detected'))
    focus = st.text_input('Career focus or target terms (editable; NOT chosen from a fixed role list)',
                          value=resume_focus(resume)[:170], max_chars=180,
                          help='Examples: embedded firmware engineer STM32; data analytics SQL dashboard. This helps avoid unrelated roles.')
    with st.expander('Resume text (only visible to this browser session)'):
        st.text_area('Extracted resume', value=resume[:6000], height=150, disabled=True)

    st.subheader('3. Choose where to search')
    left, right = st.columns(2)
    with left:
        scopes = st.multiselect('Job regions', ['India', 'International', 'Remote'],
                                default=['India', 'International', 'Remote'])
        city = st.text_input('Preferred city (optional)', placeholder='Hyderabad, Bengaluru, etc.')
    with right:
        try:
            inferred_years = int(__import__('re').search(r'Experience:\s*(\d{1,2})\s*years?', resume, __import__('re').I).group(1))
        except (AttributeError, ValueError):
            inferred_years = 0
        years = st.number_input('Professional experience (years — confirm manually)', 0, 50, inferred_years, step=1)
        country = st.text_input('Country where applicant lives', value='India')

    st.markdown('**AI agent mode (optional)**')
    enable_ai = st.checkbox('Enable Gemini AI search planning and second-opinion review', value=False)
    api_key = ''
    ai_model = 'gemini-3.8-flash'
    consent = False
    if enable_ai:
        st.warning('Privacy: with consent, selected skill tags and a redacted career-focus summary are sent to Google Gemini. Public job descriptions may also be sent. Free-tier data can be used for product improvement. Do not use this with sensitive resumes.')
        api_key = st.text_input('Your own Gemini API key (never add this to GitHub)', type='password', help='Create a key in Google AI Studio. Keys are not written to disk by RoleRoute.')
        ai_model = st.selectbox('AI model (availability depends on your free-tier account)', ['gemini-3.8-flash', 'gemini-3.6-flash'])
        consent = st.checkbox('I understand and consent to sending limited candidate information and public job descriptions to Google for AI processing')
        st.caption('Without a key, the full basic job-description matcher still runs. The model is not guaranteed to be free for every account.')
        with st.expander('See exactly what candidate data could be sent'):
            st.json(safe_llm_profile(resume, focus))
    with st.expander('Optional: additional approved public company-board IDs'):
        st.caption('Greenhouse, Lever, Ashby and SmartRecruiters company IDs only. No unauthorised site scraping or premium bypass.')
        gh_extra = st.text_input('Greenhouse IDs', key='gh')
        lever_extra = st.text_input('Lever IDs', key='lev')
        ashby_extra = st.text_input('Ashby IDs', key='ash')
        sr_extra = st.text_input('SmartRecruiters IDs', key='sr')

    start = st.button('🔎 Find jobs and compare ACTUAL job requirements', type='primary', use_container_width=True)
    context = sha256((resume + focus + str(years) + str(scopes) + city + country).encode()).hexdigest()
    if start:
        if not scopes:
            st.warning('Select at least one region.')
        elif enable_ai and (not api_key.strip() or not consent):
            st.warning('To use Gemini, enter your API key and consent, or turn AI mode off for free rule-based matching.')
        else:
            try:
                extra = {
                    'Greenhouse': parse_board_names(gh_extra), 'Lever': parse_board_names(lever_extra),
                    'Ashby': parse_board_names(ashby_extra), 'SmartRecruiters': parse_board_names(sr_extra),
                }
            except JobSourceError as exc:
                st.error(str(exc))
            else:
                all_sources = find_sources(set(scopes), extra)
                plan = None
                if enable_ai:
                    try:
                        with st.spinner('AI is planning which tools and job sources to use...'):
                            plan = plan_search(resume, focus, set(scopes), api_key, ai_model)
                    except AgentError as exc:
                        st.warning(str(exc))
                # AI plan selects search order among authorized sources, not arbitrary URLs.
                if plan and not plan['start_with_extra_sources']:
                    core = [x for x in all_sources if x[0] in ('Greenhouse','Remotive')]
                    remaining = [x for x in all_sources if x not in core]
                else:
                    core, remaining = all_sources, []
                with st.spinner(f'Fetching public job postings from {len(core)} selected sources...'):
                    jobs, errors = fetch_sources(core)
                ranked, stats = rank_jobs(jobs, resume, focus, int(years), set(scopes), country, city)
                # Bounded follow-up decision: if initial results have too few strong candidates,
                # use remaining permitted tools once. No arbitrary browsing or auto-apply.
                expanded = False
                if remaining and stats.get('Strong', 0) < 3:
                    with st.spinner('AI search plan is expanding to additional permitted employer feeds...'):
                        additional, more_errors = fetch_sources(remaining)
                    jobs.extend(additional)
                    errors.extend(more_errors)
                    ranked, stats = rank_jobs(jobs, resume, focus, int(years), set(scopes), country, city)
                    expanded = True
                ai_reviews = {}
                if enable_ai and plan:
                    try:
                        with st.spinner('AI is checking evidence in the top job descriptions...'):
                            ai_reviews = explain_job_matches(resume, focus, ranked[:6], api_key, ai_model)
                    except AgentError as exc:
                        st.warning(str(exc))
                st.session_state.v5_search = {
                    'fingerprint': context, 'jobs': jobs, 'ranked': ranked, 'stats': stats,
                    'errors': errors, 'plan': plan, 'expanded': expanded, 'reviews': ai_reviews,
                    'used_ai': bool(plan),
                }

    results = st.session_state.get('v5_search')
    if results and results['fingerprint'] != context:
        st.info('Candidate details or filters changed. Run the search again for updated matches.')
    elif results:
        st.subheader('4. Live employer job results')
        jobs, ranked, stats = results['jobs'], results['ranked'], results['stats']
        a, b, c, d = st.columns(4)
        a.metric('Retrieved postings', stats.get('retrieved', 0))
        b.metric('Strong', stats.get('Strong', 0))
        c.metric('Possible', stats.get('Possible', 0))
        d.metric('Review / conflicts', stats.get('Review / conflict', 0))
        provider_counts = Counter(j.source for j in jobs)
        st.caption('Actual feed counts: ' + (' · '.join(f'{s}: {v}' for s, v in sorted(provider_counts.items())) or 'none'))
        if results['plan']:
            plan = results['plan']
            st.info(f'**AI search plan:** {", ".join(plan["search_terms"]) or "No suggested phrases"}. {plan["query_reason"]} '
                    f'Additional source expansion: {"used" if results["expanded"] else "not needed or all sources already searched"}.')
        if results['errors']:
            with st.expander(f'{len(results["errors"])} public feeds unavailable'):
                for message in results['errors']:
                    st.write('- ' + message)
        st.caption('These groups reflect tentative resume evidence, not verified hiring eligibility. Results are drawn from a limited set of sources. Incomplete descriptions are flagged for review.')
        tabs = st.tabs(['✅ Strong candidates', '🟡 Possible candidates', '⚠️ Review / conflicts'])
        for tab, category in zip(tabs, ('Strong', 'Possible', 'Review / conflict')):
            with tab:
                shown = [(idx, item) for idx, item in enumerate(ranked) if item.category == category]
                if not shown:
                    st.info('No jobs in this group from this set of sources. This does not mean no suitable jobs exist.')
                for idx, item in shown:
                    display_match(item, results['reviews'].get(idx) if results['used_ai'] else None)
        with st.expander('Source and filtering diagnostics'):
            st.json(stats)
            st.caption('Ranked list is capped at 40; counts reflect the unique retrieved postings. No automatic application occurs.')

    st.subheader('5. Compare a job you already have permission to view')
    st.caption('For premium/private sites, paste a job description you are authorized to access. We do not bypass logins, payment, restrictions, or site controls. This text stays in this Streamlit session for basic matching.')
    with st.form('manual_job'):
        title = st.text_input('Job title (from an actual posting)', placeholder='Embedded Firmware Engineer')
        company = st.text_input('Employer', placeholder='Company name')
        location = st.text_input('Location', placeholder='Hyderabad, India')
        description = st.text_area('Paste the job description and requirements', height=160)
        url = st.text_input('Official posting link (optional)', placeholder='https://...')
        compare = st.form_submit_button('Compare pasted job with this resume')
    if compare:
        if not title.strip() or len(description.strip()) < 30:
            st.warning('Enter a job title and at least 30 characters of actual job requirements.')
        else:
            test_job = JobListing(source='User-supplied (not independently verified)',
                                  company=company[:100] or 'Not provided', job_id='manual',
                                  title=title[:150], location=location[:150] or 'Unspecified',
                                  description=description[:24000],
                                  url=url if valid_job_url(url) else '', is_remote='remote' in location.lower())
            review = evaluate_job(test_job, resume, focus, int(years), country)
            st.write(f'**Provisional category:** {review.category}')
            display_match(review)

    st.subheader('6. Explore more official job websites')
    st.caption('These are external job searches, NOT retrieved or automatically scored vacancies. Premium access remains subject to each provider’s terms.')
    from matching_engine import focus_search_query
    search_role = (results['plan']['search_terms'][0] if results and results.get('plan') and results['plan']['search_terms'] else focus_search_query(focus))[:80]
    links = external_search_links(search_role, city, country)
    for start_idx in range(0, len(links), 2):
        cols = st.columns(2)
        for col, (name, note, url) in zip(cols, links[start_idx:start_idx+2]):
            with col:
                st.link_button(f'Open {name}', url, use_container_width=True)
                st.caption(note)
    with st.expander(f'Browse official employer career sites ({len(CAREER_PORTALS)})'):
        for name, link in CAREER_PORTALS:
            st.link_button(f'{name} careers', link)

st.divider()
st.caption('RoleRoute v5 · Job descriptions are untrusted third-party data · No premium bypass · No auto-submission · No confirmed eligibility · Use fictitious resumes when testing.')
