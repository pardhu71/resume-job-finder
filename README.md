# RoleRoute Version 6.1 — Whole-Resume Job Matching

**Purpose:** After a user uploads their PDF/DOCX resume, match real vacancies using the **entire professional resume**, not only a skill keyword list. There is no hard-coded catalog of allowed job titles.

## What changed from Version 6

- **Professional titles:** Recognize titles in the resume header, labeled "Current Role" or "Target Role" fields, summaries, and work-history lines (e.g., "Embedded Software Engineer" or "Software Engineer").
- **Professional summary:** Use career direction and specialized experience as evidence.
- **Work experience and internships:** Compare role/responsibility language with the vacancy.
- **Projects:** Compare project descriptions, not just named software tools. Projects can establish career focus for freshers.
- **Education:** Include degree evidence; unclear qualification equivalence remains unverified.
- **Skills:** Compare the candidate's explicitly stated and text-evidenced skills against required/preferred job-description requirements, but do not allow generic skills (Linux, Python, Git, Excel) to overpower a different career field.
- **Career relevance:** Disfavor conflicting specializations. For example, an Embedded Engineer who knows Git and Linux should not be recommended a DevOps vacancy based solely on those two terms.
- **Unknown specialties:** Still allow fields outside the example concept vocabulary (e.g. marine corrosion) to match when project/work evidence and job-description terms overlap.
- **Explanation:** Each job shows which career titles or sections supported the recommendation and which requirements were not evidenced.
- **Optional AI (Gemini):** With explicit consent, the AI preview contains *redacted excerpts* of titles, summary, work, projects, education and skills; no original resume file is sent to the AI provider. Gemini availability and free-tier limits vary. Without an API key the fallback uses transparent rules.

The scoring weights are engineering heuristics, **not a probability of being hired or a verified ATS score**. Employers and jobs are read from supported permitted public feeds. The agent cannot guarantee every job on the internet or bypass premium job-site restrictions.

## Update your EXISTING GitHub + Streamlit website

1. Extract the ZIP.
2. Open your current GitHub repository `pardhu71/resume-job-finder`.
3. Click **Add file → Upload files**.
4. Upload **all eight** files below from the **same extracted Version 6.1 folder**, to the repository root (the same directory as `streamlit_app.py`):
   - `streamlit_app.py` (replace)
   - `analyzer.py` (replace)
   - `job_sources.py` (replace)
   - `matching_engine.py` (replace)
   - `llm_agent.py` (replace)
   - `agent_engine.py` (replace)
   - `resume_profile.py` (**NEW**, required)
   - `requirements.txt` (replace)
5. Click **Commit changes**. Keep the previous GitHub repository and existing Streamlit URL.
6. Confirm the sidebar reads **Version 6.1**. If the site still shows an import error, check **Manage app → Logs** and verify the full set of eight files is committed in the repository root. Redeploy/reboot if necessary.

**Important:** Do not upload only `streamlit_app.py`; this would cause missing-symbol ImportErrors if the supporting files have older versions.

## Test the complete-resume approach

Use a fictional or non-sensitive test resume such as:

```
Embedded Software Engineer
SUMMARY
Firmware, microcontrollers and RTOS development.
EXPERIENCE
Embedded Systems Engineer — Built STM32 drivers.
PROJECTS
Built an STM32 temperature-monitoring device using I2C and embedded C.
EDUCATION
B.Tech Electronics
SKILLS
C, C++, Linux, Python, Git, STM32, FreeRTOS, I2C
```

Confirm the website detects **Embedded Software Engineer** and relevant summary, work, projects, education and skill sections. It should prioritize firmware/embedded jobs over DevOps roles even if DevOps job descriptions mention Linux, Python and Git.

Then test a Software Engineer resume with backend projects, and verify relevant backend listings. Open each employer link to verify that it is still active and relevant. If sources have no applicable vacancies, it is correct to show no strong matches rather than invent jobs.

## Privacy and production readiness

Uploaded resumes are handled by the Streamlit-hosted server. This is a prototype and **has not completed a production security/privacy assessment**. Do not collect users' sensitive resumes at scale before adding a privacy notice, user consent, clear retention/deletion policies, separated user sessions and appropriate security testing. Keep Gemini keys out of public GitHub files; only submit resume excerpts to Gemini after reviewing the preview and consenting. Never claim legal eligibility or apply to jobs without explicit user permission.

## Automated checks

From the extracted folder, once the dependencies and `pytest` are installed:

```bash
python -m pytest -q
```

**73 tests passed locally** at build time. These include complete-resume parsing, unfamiliar careers, embedded-vs-DevOps conflicts, job requirements, missing experience and location cautions, agent workflow, and static import/export checks. Tests use simulated job feeds and AI responses. **Streamlit Cloud deployment and live job/APIs remain to be validated on your website.**
