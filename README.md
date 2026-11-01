# RoleRoute Version 5 — Dynamic Resume-to-Job Matching + Optional AI Planning

A **free-first Streamlit web app** that opens in Chrome/Edge and helps job seekers compare their resumes against **actual descriptions from public job feeds**. Does **not** use a predefined job-title list for its Version 5 ranking.

## What's improved in V5

- **Dynamic career matching:** resume evidence (skills, projects, stated interests and optional editable focus) vs. actual vacancy titles and descriptions. No fixed role catalogue decides which careers to recommend. This fixes the common embedded-resume → DevOps generic-keyword problem.
- **Job requirements:** tries to separate explicitly **required**, **preferred**, and merely **mentioned** technical terms; highlights skills **not evidenced in the resume** instead of assuming the candidate lacks them.
- **Ranked groups:** Strong, Possible, and Review/Conflict. Unrelated postings are excluded from the recommendations and counted in diagnostics.
- **Candidate constraints:** user-confirmed years of experience, country, regions, optional city. Remote country and visa issues are flagged as uncertain, never verified.
- **Optional bounded Gemini AI planner:** if the user supplies a Gemini API key and gives explicit consent, an LLM selects search focus terms and a safe subset/order of authorized source tools. If fewer than three strong leads are found, the tool loop expands to remaining selected sources once. AI also gives a second opinion on up to six results. JSON is validated, model cannot fetch arbitrary URLs or submit applications.
- **No AI key required:** the deterministic job description matcher and public feed search still work.
- **Premium/private:** user can manually paste a job description they are **authorized** to access and compare against resume. App does not bypass paywalls/login, harvest private sites or pretend pasted postings have been independently verified.
- **Human-in-the-loop application:** direct employer links and a five-item applicant confirmation checklist. **No auto-application, account login, or verified eligibility claims**.
- **Multiple sources:** curated Greenhouse, Lever, Ashby, SmartRecruiters, and Remotive feeds (subject to real availability); external searches for Indeed, Internshala, Naukri, LinkedIn, Foundit; links to 18 employer career sites. External links are NOT treated as retrieved/scored jobs.

## Updating your existing Streamlit website

You do **not** need to delete old GitHub files, create another GitHub repository, or create a new Streamlit URL.

1. Download and extract `resume_job_finder_v5.zip`.
2. Open your existing `https://github.com/pardhu71/resume-job-finder` repository.
3. Click **Add file → Upload files**. Upload these SIX files from the extracted ZIP root:
   - `streamlit_app.py` (replaces old file)
   - `job_sources.py` (replaces old file)
   - `analyzer.py` (replaces old file)
   - `requirements.txt` (replaces old file, adds optional Google SDK)
   - `matching_engine.py` (**NEW**)
   - `llm_agent.py` (**NEW**)
4. Click **Commit changes**. GitHub replaces files with the same names at the same path.
5. Reopen your existing Streamlit website. Sidebar should say **Version 5**. Existing Streamlit link stays unchanged.
6. If deployment fails, open **Manage app → logs**, and check `requirements.txt` and that the two new `.py` files are at the repository root next to `streamlit_app.py`.

**Never upload API keys, `.env`, `.streamlit/secrets.toml`, personal resumes, or private job text to public GitHub.**

## Quick testing

1. Click **Fictional Embedded Systems resume**.
2. Confirm extracted technical skills, and edit career focus if necessary.
3. Set experience to **0**, choose India + International + Remote.
4. Keep **AI agent mode off** for the first smoke test and click **Find jobs and compare ACTUAL job requirements**.
5. Review Strong, Possible and Review/Conflict tabs; inspect sources, requirements, limitations and links. Results can be empty because live feeds and the data pool are limited.
6. Check the source counts and that unrelated generic DevOps roles do not appear as recommendations for the embedded sample.
7. In Section 5 paste this **fictional** vacancy and click **Compare pasted job**:

   - Title: `Firmware Engineer`
   - Employer: `Fictional Electronics Ltd`
   - Location: `Bengaluru, India`
   - Requirements: `Required: Embedded C, STM32, FreeRTOS. Preferred: I2C. 0 years experience.`

8. For comparison paste an unrelated **fictional** posting: `DevOps Engineer` / `Required: Python, Linux, Git, Kubernetes, Docker.` and verify it is flagged as unrelated / needing review rather than recommended.

## Optional genuine model-driven AI mode

1. Visit https://aistudio.google.com/apikey and create **your own** Gemini API key, if eligible for a free tier.
2. On the site, check **Enable Gemini AI search planning and second-opinion review**.
3. Paste the key into the **password** input, choose a model supported by your account, inspect the preview of the limited candidate info, then check the **consent** box and click Search.
4. The model may choose the source order, recommend dynamic query phrases, and provide reviews. The app executes a bounded allowlisted search, may expand once when few strong candidates appear, and requires a person to choose whether to apply.
5. If free-tier quota or model access is unavailable, disable AI mode and continue using basic matching.

**Security and privacy:** This is a prototype, NOT security-audited. Never share API keys with users or commit them to GitHub. Streamlit sees uploaded data and transient session state; Gemini receives limited skill/focus signals and public job descriptions only if enabled and consented to. The free Gemini tier may use data for product improvement. Avoid real personal resumes until there is privacy review, security hardening, retention and deletion policies, and compliance with applicable laws. For scaled public deployment, add authenticated user accounts, rate limits and server-side secrets/key handling.

## Accuracy and limits

- Matching heuristics are not an employer ATS score, verified eligibility or the chance of being hired.
- Required / preferred parsing is approximate; real descriptions are inconsistent and sometimes omit requirements. Check employer page before applying.
- Career relevance may still miss synonyms or unusual job titles. Optional LLM can help, but can also make mistakes; its second opinion does not override source evidence.
- 100% job coverage is not possible: providers restrict access; jobs may be unindexed, closed or private.
- Premium/private feeds are **not accessible without authorization**; no bypass is included.
- The app cannot independently validate degrees, experience, work authorization, visas or whether jobs remain open.
- No application is sent to an employer. Application is manual through source links.

## Develop/test locally (optional)

Requires Python 3.10+.

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
python -m pytest -q
```

Unit tests are located in `tests/` (development machine needs `pytest`). Public-feed unit tests use mocked HTTP responses. API connectivity, free-tier quota, live job status, and full Streamlit runtime need checking after deployment.

## Files

- `streamlit_app.py`: Streamlit UI and bounded tool orchestration
- `matching_engine.py`: dynamic resume-to-job-description matcher and explanations
- `llm_agent.py`: optional Gemini tool planning and reviewed output (user key + consent)
- `job_sources.py`: public API adapters and external search links
- `analyzer.py`: resume text reading and initial technical skill signals
- `requirements.txt`: runtime dependencies
- `tests/`: automated tests
