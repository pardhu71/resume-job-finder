# RoleRoute Version 4 — Wider job discovery (India + international + remote)

**What changed:** RoleRoute can now retrieve postings from a **curated subset** of public employer career feeds using **Greenhouse, Lever, Ashby, SmartRecruiters, and Remotive**. It also gives users **search links** to Indeed, Internshala, LinkedIn, Naukri, Foundit, Google, and **18 official company career portals**. The search links are a separate feature: RoleRoute **does not retrieve or rank jobs** from those external platforms.

**Important limitations:**
- This is **not a search index of every vacancy on the internet**. The app cannot access private/unlisted vacancies, premium-only content without a subscription/license, or unrestricted API results.
- This is a **rule-based prototype**, not yet an LLM-powered autonomous AI agent. Scores are **heuristic relevance estimates**, not eligibility or hiring probabilities.
- Provider feeds can fail, change, include stale vacancies, or omit full requirements. Some URLs may only lead to a company's career board; in that case you must find the specific role there.
- **No applications are submitted**, no premium paywall is bypassed, and no user's resume text is sent to job platforms by our app.
- **Do not collect sensitive real-world resumes from the public** until you complete a production privacy/security review, privacy notice and consent, retention/deletion controls, abuse prevention, and hosting checks. Use the fictional sample initially.

## Update your existing live website (no need to delete old files)

1. Download and **extract** `resume_job_finder_v4.zip`.
2. Open your existing repository: https://github.com/pardhu71/resume-job-finder
3. Select **Add file → Upload files**.
4. Upload these four files to the **repository root**, replacing the previous versions with the **same filenames**:
   - `streamlit_app.py`
   - `job_sources.py`
   - `analyzer.py`
   - `requirements.txt`
5. Optionally replace the repository `README.md` with this file. Do not upload the ZIP itself.
6. Click **Commit changes**. Streamlit will redeploy your **existing website URL**. Check the sidebar says **Version 4**.

## Test V4

1. Click **Use fictional sample resume**.
2. Select **India**, **International**, and **Remote**.
3. Select **0 years** of experience, and leave **Hide roles that appear to require more experience** on.
4. Click **Automatically find matching jobs**.
5. Review retrieved posting counts **by source**, diagnostics, ranked listings, and original employer links.
6. Continue down to **Search more websites and company careers**. Click **Indeed**, **Internshala**, or any company portal. Those pages open externally. Results there have **not** been inspected by RoleRoute.
7. For freshers, search for `Data Analyst Intern` or `Graduate Trainee`, and do not assume every listing allows freshers or India-based remote workers.

## Source coverage and refresh

**Actual individual jobs shown in RoleRoute:**
- **Greenhouse**: public GET for specifically listed employer boards (max 200 per board).
- **Lever**: public employer postings, optionally with board IDs supplied by the user (max 200).
- **Ashby**: public job-board postings for a specified organization (max 200).
- **SmartRecruiters**: public postings for a specified company (first 100). Summary records may lack full job descriptions and direct job URLs; if missing, the app links to the official company career board and labels that clearly.
- **Remotive**: remote jobs returned via its public feed (up to 200), delayed by at least 24 hours. Each job keeps source attribution and its Remotive link. The remote feed is cached for six hours per running app process to comply with the suggested refresh limit of roughly 4 calls/day. Multi-instance traffic still needs monitoring.

The example boards are **curated**, not discovered worldwide; source failure can reduce coverage. You may add up to four board identifiers for each provider under **Advanced**. Identifiers are not arbitrary URLs.

**External navigation only (not retrieved into RoleRoute):**
- Indeed, Internshala internships and jobs, LinkedIn Jobs, Naukri, Foundit, Google, and many MNC career pages, including TCS, Infosys, Wipro, Accenture, Cognizant, IBM, Amazon, Microsoft, Google, HCLTech and others.
- The user navigates the external site and may be required to sign in or pay for features. We do not scrape these services, evade rate limits, impersonate premium accounts, or attempt to unlock paid listings.

## Privacy and data flow

- A PDF/DOCX resume is uploaded to the **Streamlit-hosted server**, extracted in memory, and analyzed using a small list of skills and role patterns. We don't intentionally write the original resume to storage. Streamlit and the hosting provider may have separate operational logging and data-retention behavior.
- Only generic **role and preferred city** are placed in external search URLs, not the full resume text, name, phone number, or contact details.
- Retrieved job descriptions are untrusted content and should be treated only as data.
- Apply through original websites; confirm the vacancy is still active and review requirements.

## Local run (optional)

```bash
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

## Automated tests

```bash
python -m pip install pytest
python -m pytest -q
```

Tests use **mocked external provider responses**. They validate parsers and matching logic but **do not prove live job access** from deployed Streamlit.

## Official API references

- Greenhouse: https://docs.greenhouse.io/job-board
- Lever: https://github.com/lever/postings-api
- Ashby: https://developers.ashbyhq.com/docs/public-job-posting-api
- SmartRecruiters: https://developers.smartrecruiters.com/docs/endpoints
- Remotive: https://remotive.com/remote-jobs/api
- Indeed developer agreement: https://docs.indeed.com/legal-terms/developer-agreement
- Adzuna evaluation and licensing (a potential future source, **not** included here): https://developer.adzuna.com/docs/terms_of_service
