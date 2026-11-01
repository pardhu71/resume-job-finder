# RoleRoute — Resume-to-Job Finder (Version 1)

A beginner-friendly, free **Streamlit website** that accepts a PDF or DOCX resume, extracts readable text, identifies selected skills, and suggests job titles to research.

**Important:** This is a working prototype, **not yet a fully autonomous AI agent**. It **does not fetch live vacancies** or verify that a specific employer is hiring. A search button opens a normal Google search. Version 2 can add actual job-source APIs and AI-based tool decisions.

## Publish it for free using only a browser

1. Download `resume_job_finder_v1.zip` and **extract/unzip** it on your computer.
2. Create a free account at [GitHub](https://github.com/signup).
3. On GitHub, choose **New repository**, name it `resume-job-finder`, choose **Public**, and **Create repository**.
4. On the new repository page, choose **Add file → Upload files**. From the extracted folder, upload these **three files into the repository root**:
   - `streamlit_app.py`
   - `analyzer.py`
   - `requirements.txt`
   You can also upload the `README.md` and `.streamlit/config.toml` later. (The app works without the optional config.) Click **Commit changes**.
5. Open [Streamlit Community Cloud](https://share.streamlit.io/) and sign in using GitHub.
6. Click **Create app** → **Yup, I have an app** (wording may change slightly).
7. Select your `resume-job-finder` repository, branch `main`, and main file `streamlit_app.py`.
8. Click **Deploy**. When deployment completes, Streamlit gives you a shareable `*.streamlit.app` link.
9. Open that link in **Chrome or Edge**. First click **Try with a sample resume**. Later test a non-sensitive PDF or DOCX.

You do not need to install Python or run a terminal to deploy through GitHub and Streamlit Community Cloud.

## Run on your own computer (optional)

With Python 3.10+ installed, from the project directory:

```bash
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

Open the local URL displayed in the terminal.

## Privacy and limitations

- When hosted, uploaded resume bytes **travel to the app's server** over the browser connection, and the uploaded content is processed in server memory. This source code does not intentionally write resumes to disk, databases, or third-party AI services.
- The product has not undergone production security, privacy, or abuse testing. For early trials, use the built-in **fictional sample resume**; do not request real users' personal resumes yet.
- PDF text extraction does not work for many scanned/image-only PDFs. OCR can be added later.
- Keyword detection is not an AI language model. It can miss skills or identify terms that do not represent proficiency.
- The example percentages are only skill-list overlap, **not** match probabilities, job-fit guarantees, hiring odds, or eligibility checks.
- Search buttons open Google searches; they do **not** establish that any resulting vacancy is available.
- Streamlit Community Cloud and any future AI/job APIs have free-tier limits. Scaling to many concurrent users may require spending money.

## Future milestones

1. Connect supported public job APIs and show currently published jobs with source links.
2. Add a real agent loop: plan search terms → call tools → compare job requirements → retry broader/narrower searches where appropriate.
3. Evaluate relevance against real annotated examples and add honest match explanations.
4. Add security review, individual accounts or anonymous sessions, consent, and deletion controls before collecting sensitive resumes broadly.

## Files

- `streamlit_app.py` — website UI.
- `analyzer.py` — PDF/DOCX extraction and basic role-suggestion logic.
- `requirements.txt` — Python libraries required for free deployment.
- `.streamlit/config.toml` — optional appearance and upload limit.
- `tests/test_analyzer.py` — basic developer tests.
