# RoleRoute — Resume-to-Job Finder (Version 2)

This is an educational Streamlit web prototype which:

1. Extracts readable text from a PDF or DOCX resume (no OCR).
2. Recognizes a small, explicit dictionary of skills.
3. Suggests possible roles from example skill lists.
4. Retrieves publicly published job posts from **selected** Greenhouse and Lever employer job boards via their documented GET APIs (no login/API key required for these public feeds).
5. Ranks retrieved posts with an **explainable heuristic relevance estimate**, then links to their original employer pages.

**Not an autonomous AI agent yet.** The site does not run an LLM. The job relevance number is not an actual hiring probability, job eligibility decision, or guarantee that an opening is still available. It does **not** find all jobs on the internet.

## Upgrade existing Streamlit deployment from Version 1

Upload these files to the **root** of your existing GitHub repository, replacing files with the same names:

- `streamlit_app.py` (replace)
- `analyzer.py` (replace or leave unchanged)
- `requirements.txt` (replace)
- `job_sources.py` (**new**)
- `README.md` (optional)

Do not upload the ZIP file itself. Commit the changes. Streamlit Community Cloud automatically redeploys the existing app from GitHub; your existing URL should remain the same.

## First test

1. Open the app.
2. Click **Try with a fictional sample resume**.
3. Review the extracted skills.
4. Select an experience level and optionally enter a location. Leave **Only show jobs** unchecked initially.
5. Click **Find published jobs**.
6. If your sample company feeds return no relevant results or errors, try other employer board IDs from actual company Greenhouse / Lever career pages. Coverage is limited to selected employers.

## Local run (optional)

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Tests

```bash
python -m pytest -q
```

`pytest` is only required for development tests, not for hosting.

## Privacy and safety notes

- In the hosted version, a user's resume is transferred to the Streamlit hosting server. The prototype's application code processes resumes in memory; it does not intentionally write raw resumes to a database or send them to the job-board APIs.
- Do not treat this as a professional privacy/security audit or deploy it with sensitive personal resumes before implementing data protection, access controls, deletion policies, abuse prevention, legal compliance, and a clear privacy notice.
- Public employer feeds may have access restrictions or usage limits. Be respectful of providers; this app caches public board reads for 10 minutes.
- Job descriptions are untrusted source text; they are displayed as escaped text rather than as executable HTML.
- The app never submits applications and never shares resume text with employers.

### Data source references

- Greenhouse Job Board API: https://developers.greenhouse.io/job-board.html
- Lever public Postings API: https://github.com/lever/postings-api
- Streamlit Community Cloud: https://docs.streamlit.io/deploy/streamlit-community-cloud
