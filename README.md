# RoleRoute — Resume-to-Job Finder (Version 3)

A **browser-based** Streamlit prototype for Chrome/Edge that reads PDF/DOCX resumes, recommends example job roles, **automatically fetches vacancies** from a curated group of employer boards in India and overseas, optionally includes remote jobs, and ranks the results using transparent heuristics.

**Honest status:** Version 3 is an automated, **rule-based search-and-ranking workflow**, not an autonomous LLM agent. It **cannot guarantee all jobs, 100% resume compatibility, employment eligibility, vacancy status, or getting hired**. No job applications are submitted.

## Update your already-deployed RoleRoute app (easy, no coding)

1. Download `resume_job_finder_v3.zip` and **extract it**.
2. Go to your existing GitHub repository: https://github.com/pardhu71/resume-job-finder
3. Open **Add file → Upload files**. From the extracted folder, upload these four files to the repository **root** (not inside another folder):
   - `streamlit_app.py` — **replace** the old version.
   - `job_sources.py` — **replace** the old version.
   - `analyzer.py` — replace (unchanged from v2, harmless).
   - `requirements.txt` — replace (unchanged from v2).
4. Optional: replace `README.md` in the repository.
5. Scroll down and choose **Commit changes**.
6. Your existing Streamlit URL will update after the GitHub commit. Open it and confirm the left sidebar says **Version 3**. If it doesn't, refresh and open **Manage app** for logs.

**Do not upload the ZIP itself.** If GitHub says there is no changed file, that's fine for the unchanged files.

## Quick test

1. Click **Use fictional sample resume**. Use the sample during initial testing instead of sensitive personal resumes.
2. Set **Where should we look?** to `India`, `International`, and `Remote` (all selected by default).
3. Leave `0` years of experience and **Hide roles that appear to require more experience** enabled.
4. Click **Automatically find matching jobs**. The app chooses a small collection of public boards without asking you to type board IDs, plus a remote feed.
5. The app shows the retrieved total and up to 30 ranked **potential matches**. Click through to the provider/employer site and validate each vacancy.
6. Try unchecking the experience filter or choosing `India` only. No results means **none matched in the sources checked**, not that no jobs exist.

## Data sources and refresh policy

- **Greenhouse public Job Board API**: curated India-related board IDs `aidashinc`, `sigmoid`, `tide`, `purestorage`, `instead`, `zyngacareers`, plus international boards `figma`, `ramp`, `galaxydigitalservices`. These are **illustrative starting employers**, not guaranteed reachable or exhaustively representative. Most public feeds cap to 200 postings **per board** in this prototype. The GET endpoints require no credentials.
- **Lever public Postings API**: optional additional companies can be entered under advanced controls. No global search index is provided by Lever.
- **Remotive public Remote Jobs API**: queried automatically when `Remote` is selected; **link to Remotive and mention Remotive for every listing** (the app does this). Jobs are **delayed at least 24 hours**; API use should be low volume (they advise about **four requests/day**, with hard limits). The app caches remote feed data for **six hours** in the running Streamlit process. A process restart clears this cache; you must monitor external usage if scaling.
- Employer feeds are cached **20 minutes** in the running Streamlit process.
- All feeds may fail, expire, return no vacancies, or restrict service. Remote roles may restrict countries and visa eligibility. The app surfaces known location restrictions instead of assuming remote means global access.

## Matching and experience limitations

- **Score**: title relevance up to 40 points, keywords in job descriptions up to 35, approximate experience hints up to 15, and location hints up to 10. The percentage is a **relevance score only**, NOT an estimate of hire/eligibility probability.
- Experience is parsed conservatively from some textual phrases and senior title words. It can be wrong. When a job states a minimum over the applicant's experience, the strict filter hides it; unknown requirements are **not** assumed to be entry-level. Always check the job's original description.
- Detected skill keywords may be listed as "nice to have" rather than mandatory. A missing keyword in a resume doesn't prove the person lacks that skill.
- Job board "last updated" is generally **not the original posting date**. Vacancy status must be confirmed on the source page.

## Privacy and security

- With Streamlit hosting, resume uploads reach Streamlit's server. The app parses resumes in memory and does not intentionally save raw resumes to disk/a database; it does not send resume text to employers or job APIs.
- Do not invite public users to upload sensitive resumes until you have done a privacy/security review, added appropriate notice and consent, data retention/deletion policies, access controls if needed, and abuse protection. Streamlit hosting and its logs/services are separate from this app code.
- External job descriptions are **untrusted data** and cannot instruct the application to perform actions. Jobs are linked to the original source. No applications are submitted automatically.
- No paid API key is required for the starting sources. The site is free to prototype on Streamlit Community Cloud, subject to its limits and source terms; production or high-volume use could cost money.

## Local run (optional)

```bash
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

## Tests

```bash
python -m pip install pytest
python -m pytest -q
```

Tests use **mock API data**, so they prove expected parsing/matching behavior but **do not validate live job availability**. Test deployed sources manually too.

## Useful official documentation

- Greenhouse public Job Board API: https://docs.greenhouse.io/job-board
- Lever public posting API: https://github.com/lever/postings-api
- Remotive API and terms: https://remotive.com/remote-jobs/api
- Streamlit hosting: https://docs.streamlit.io/deploy/streamlit-community-cloud


## V3.1 diagnostic update

- Shows the number of postings remaining after deduplication, region, city, experience, and relevance filtering.
- When no strong matches are found, users can opt into a clearly labeled broader exploratory-results view (not guaranteed fits; includes potential senior/ineligible roles).
- Normal strict matching behavior is unchanged.
- No additional API access or secrets are required.
