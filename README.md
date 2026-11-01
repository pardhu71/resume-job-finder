# RoleRoute Version 5.2 — Resume In, Relevant Jobs Out

RoleRoute is a beginner-friendly Streamlit website that searches supported **public employer job feeds** and compares the **actual job descriptions** with an uploaded PDF or DOCX resume. It runs in modern browsers, including Chrome and Edge.

## What changed in 5.2

- **No fictional/sample resume buttons or sample-resume instruction banner.** Users simply upload a PDF or DOCX.
- **Automatically starts job discovery on a new upload** and displays matching vacancies. A Refresh button reruns the search after optional settings changes.
- **Relevant jobs first:** Strong and Possible matches appear in the main results list; uncertain or potentially conflicting jobs appear under a separate expandable area. Unrelated careers should be excluded rather than ranked merely for sharing generic skills.
- **Direct resume-to-job-description comparison:** no predefined list of job titles determines the recommendations. Matching uses evidence in the resume and employer's job description, including required/preferred skills and domain-specific terms.
- **Better recognition of skills in multiline skill sections** (including uncommon technologies not included in the starter keyword patterns).
- **Unknown experience is not assumed to be 0 years.** Experience can be confirmed under optional search preferences. Jobs specifying experience are marked for review when the applicant's years are unknown.
- **Fast repeated matching:** resume skills are analyzed once per search, rather than once per vacancy. A synthetic benchmark with 1,200 postings completed the matching stage in under a second on the test machine; real site performance depends on external job feeds.
- **A 5 MB application-side resume upload limit** and careful wording about relevance, uncertainty and privacy.

The first user-visible action is to **upload the resume**. Optional controls for regions, location, years of experience, consent-based Gemini mode, and extra approved employer feeds are inside a collapsed preferences panel.

## Update the existing GitHub + Streamlit website

You **do not** need to delete older files or create a new website.

1. Extract the ZIP file to a folder on your computer.
2. Open the existing repository: https://github.com/pardhu71/resume-job-finder
3. Choose **Add file → Upload files**.
4. Upload these six files from the extracted folder (the same names overwrite the previous versions on commit):
   - `streamlit_app.py`
   - `analyzer.py`
   - `job_sources.py`
   - `matching_engine.py`
   - `llm_agent.py`
   - `requirements.txt`
5. Click **Commit changes**. Streamlit Community Cloud should redeploy from the repository automatically.
6. Open the **existing** Streamlit URL, confirm that the sidebar says **Version 5.2**, and upload a *non-sensitive test resume* to check the results.

If Streamlit shows an error, use **Manage app → Logs** and check that all six files are in the repository root.

## Test checklist

1. Upload a text-based PDF or DOCX resume with no personal contact details; you can create a fictional resume yourself for testing, but **the public UI no longer offers sample resumes**.
2. Confirm that the site **starts searching automatically** without requiring a second submit click.
3. Confirm the returned vacancies have company name, location, matching evidence and a direct source link.
4. Test a resume focused on Embedded C, STM32, FreeRTOS and firmware: DevOps positions sharing only Git/Linux/Python should not be recommended.
5. Try a different career-focused resume. Confirm that results change and are not selected from a fixed set of job roles.
6. If a job has ambiguous minimum experience or location eligibility, confirm it is flagged rather than treated as confirmed eligibility.
7. If the site finds no relevant job in its retrieved feeds, it should say so rather than invent listings.

Run the local test suite with `python -m pytest -q`. Automated tests use mocked job feeds. They **do not** prove that live public feeds are accessible or that all matching rules are accurate on every real resume.

## Important limitations

- This is a prototype; it has **not** undergone a professional privacy/security audit. Uploaded resumes reach the Streamlit server. Do **not** collect real personal resumes from the public until you have appropriate data protection, retention/deletion controls, and consent.
- The app does **not** search every job on the internet. It retrieves openings from a **limited set of public employer feeds** (Greenhouse, Lever, Ashby, SmartRecruiters and Remotive where available), plus external search links to platforms such as Indeed and Internshala. External search links are not scored or presented as verified vacancies.
- Employer job descriptions may be incomplete or out of date, and matching is **heuristic** (not a verified qualification assessment or hiring probability).
- Optional Gemini planning/review needs the user's own API key and opt-in. It sends a limited redacted candidate summary and some public descriptions to Google, and subject to the provider's terms and limits. **No Gemini key is required for basic matching.**
- Premium/private feeds require permission; the app does not bypass logins, paywalls or usage restrictions.
- RoleRoute **never applies to a job on a person's behalf**. A person must inspect the employer's source page and apply themselves.
- If a PDF consists of scanned images, text extraction may fail; a text-based PDF or DOCX is recommended.

## Repository files

- `streamlit_app.py` — user interface, auto-search and result presentation
- `matching_engine.py` — actual job-description vs resume matching
- `analyzer.py` — file parsing and technical skill patterns
- `job_sources.py` — approved public job feed adapters
- `llm_agent.py` — optional bounded Gemini integration
- `requirements.txt` — dependencies
- `tests/` — regression tests (do not need to upload the tests to GitHub for deployment)
