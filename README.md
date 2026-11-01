# RoleRoute Version 6 — Bounded AI Job Search Agent

A Streamlit website that searches *real, permitted employer job feeds* based on an uploaded resume. It does not rely on a preselected catalog of career titles. The optional Gemini mode adds AI-driven interpretation, search planning, refinement, and evidence-focused explanations.

## Features and architecture

1. **Understand the resume:** extract skills, project/career focus, basic qualification signals and experience (if known). In AI mode, Gemini checks the reduced, redacted profile, never the original PDF file.
2. **Plan the search:** derive job/skill phrases from resume evidence. In AI mode, Gemini proposes bounded phrases and the order in which approved source groups should be checked. Unsupported or unrelated suggestions are rejected.
3. **Use tools to fetch jobs:** the Python application calls only supported public Greenhouse, Lever, Ashby, SmartRecruiters and Remotive feeds. Feed requests are read-only. The job descriptions are real feed content, not generated vacancies. Selected company boards are illustrative and cannot index the whole internet.
4. **Assess requirements:** compare skills mentioned as required vs preferred, seniority, reported years of experience, candidate career focus, and possible geography restrictions. Unknowns remain *unknown*; matching scores are provisional evidence heuristics, not hiring probabilities or guarantees.
5. **Refine:** if fewer than five relevant leads appear, query additional approved public source boards. In AI mode, request one additional set of resume-grounded search terms and re-evaluate the retrieved jobs without waiving mandatory requirements. Maximum two rounds of employer feeds and one AI refinement. The alternative terms do not scrape other websites or fetch private results.
6. **Explain:** every result shows matched and missing evidence plus cautions, original description and link. AI mode optionally adds a second written interpretation of top job descriptions. Users can view a six-step *agent decision log*.

A full working **Gemini agent mode requires a user's own Gemini API key and explicit consent**. Otherwise, the website still performs the six-step workflow with deterministic decision rules; this is an automated job matching tool, not AI reasoning.

## Deploy to your existing Streamlit site

1. Extract the ZIP file locally.
2. Open your existing GitHub repository `pardhu71/resume-job-finder`.
3. Select **Add file → Upload files**. Upload all these root-level files, replacing files with matching names: `streamlit_app.py`, `analyzer.py`, `matching_engine.py`, `job_sources.py`, `llm_agent.py`, **`agent_engine.py` (NEW)**, `requirements.txt`, and optionally `README.md`.
4. Also upload `.streamlit/config.toml` to a `.streamlit` folder if GitHub's web upload can preserve folders (the app is functional without this file, but it enforces the 5 MB upload limit at the framework level).
5. Click **Commit changes**. Existing Streamlit Community Cloud app should redeploy from `streamlit_app.py`, keeping its URL.
6. Check the sidebar displays **Version 6** and run a non-sensitive test resume.

If an import error for `agent_engine` appears, confirm `agent_engine.py` is in the **same root folder** as `streamlit_app.py`.

## Test guide

- Upload a fictional or privacy-safe PDF/DOCX resume for Embedded Systems/Firmware, or another domain.
- Confirm extracted skills. Expand **Search preferences and optional AI** to set geography and professional years, or leave unknown years unspecified.
- The first search runs after file upload. It may make two calls batches against selected approved job feeds.
- Check **Relevant job opportunities** and expand **See what the agent did — six-step decision log** to see the actions taken and why the search expanded.
- Verify the role is truly relevant: embedded career signals should not produce unrelated DevOps recommendations based solely on generic Linux/Python/Git overlap.
- Check the original employer page for current availability, years, location/remote eligibility, visas, and application conditions.
- Optional AI mode: create a Google AI Studio Gemini API key, check the consent box, then press **Refresh matches using current preferences**. The key is entered in Streamlit's masked input; do **not** put keys in GitHub code or files.

## Security, privacy and honesty

- The resume is uploaded to the Streamlit server and processed in session memory. This prototype is **not production security-reviewed**. Do not request sensitive applicant files before implementing informed consent, privacy notices, deletion controls, retention policies, rate limits and abuse safeguards.
- No candidate resume or contact details are transmitted to job feed providers. In Gemini mode, selected non-identifying skills and career-focus snippets, plus top job description excerpts, are transmitted to Google under **explicit opt-in**. Candidate text can still accidentally contain personal details; inspect the *Preview the candidate data* panel before consenting. Gemini free-tier submissions may be used to improve Google's products and quotas may be limited.
- API keys should not be logged, committed or stored in GitHub. Streamlit hosted users who enter keys interact with the backend; consider server-side secrets handling before a public launch.
- This agent does **not** automatically apply, bypass logins/paywalls, verify legal eligibility, promise any number of jobs, or guarantee interviews.
- Job listing descriptions are **untrusted data**. They cannot execute arbitrary agent actions or instruct the AI to apply/send email.
- Public Remotive jobs must be attributed and linked to the Remotive listing; the cached feed is refreshed at most a few times per day. Follow provider terms and quotas.
- `requirements.txt` pins supported major versions, not exact versions; re-check dependency compatibility and security before production deployment.

## Local run (if using your own computer)

```bash
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Automated test suite

```bash
python -m pip install pytest
python -m pytest -q
```

Tests use **mocked job APIs/AI responses** and do not establish actual online search reliability, Streamlit cloud operation, or live Gemini availability. Production deployment remains to be verified using the user's live Streamlit app.
