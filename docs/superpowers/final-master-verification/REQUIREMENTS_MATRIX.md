# Requirements matrix

Read from `REQUIREMENTS.md`, line by line, and checked against the clean-room run of 1 October 2026 on the real 488-CV corpus. Evidence
file names are in this folder. PASS means exercised on the run. PARTIAL means it works with the stated limit. NOT TESTABLE means the input does not exist in this clone.

| Req | Status | Evidence | Remaining limitation |
|---|---|---|---|
| **1.1** Keep all CVs and candidate details in one place | PASS | `01-corpus.json`, `02-corpus-stats.json`: 472 documents and 401 profiles in one database with content-addressed files | SharePoint/OneDrive are not read; CVs enter by upload, the sourcing form or Excel |
| **1.2** Move current CVs, Excel lists and recruitment information in | PARTIAL | 488 CVs loaded in 72 s (`01-corpus.json`); a 12-row workbook imported (`12-excel-export.json`) | The challenge workbook was not provided; no SharePoint/OneDrive connector; no import of past hiring requests |
| **1.3** One profile per candidate | PASS | 16 byte-identical copies stayed one document; same-person CVs opened reviews instead of new profiles (`04-duplicates.json`, `02-corpus-stats.json`) | Different-name CVs of one person cannot be linked without a shared email or phone |
| **1.4** Name/contacts, experience, education, skills, qualifications, certificates, previous applications, years | PASS | `03-profiles.json`, `03a-real-candidate-profile.png`: every section present on real profiles; 180 of 181 evidence quotes on five real profiles found in the CV text by an independent check (the one miss is a multi-line quote that the system's own verifier accepts) | Coverage depends on layout: years known for 247 of 401, skills for 221, education 370, certificates 32. Employer/title split is heuristic and sometimes wrong; multi-column CVs add noisy rows |
| **1.5** Keep the candidate's information and CV up to date | PASS | Merge & Update Profile: new CV current, old kept as history, applications 1 -> 2 (`04-duplicates.json`) | |
| **2.1** Read PDF and Word | PASS | 444 PDF, 25 DOCX, 3 JPEG; 436 text layer, 25 DOCX, 6 OCR (`02-corpus-stats.json`); Word preview fallback (`15-visual-compare.json`) | Legacy `.doc` path exists (LibreOffice) but the corpus has no `.doc` |
| **2.2** Search inside every CV, not only by file name | PARTIAL | 1,834 chunks, all with a vector; free-text, e-mail, phone, Arabic queries return the CV with the matching passage (`05-search.json`) | The vector is a local token hash, not a semantic model. The 2 `needs_ocr` and 5 quarantined files are not searchable |
| **2.3** Filter by name, skills, years, education, qualifications, certificates, industry, job title, nationality | PASS | All filters and combinations on real data; every hit carries a reason or evidence; no quarantined or non-CV document appears as a confirmed profile (`05-search.json`) | Nationality is a text match on what the CV states, never inferred or stored. Certificate and skill filters follow parsed sections, so a CV whose layout hides them can be missed |
| **2.4** Results clear and simple | PASS | `05-search-python.png`, `16-07-search-python.png` | |
| **3.1** Compare CVs with the job description and requirements | PASS | `08-matching-rules.json`: 404 candidates scored on each of three requests, no rule violation | Verdicts for skills use stored skills plus CV text retrieval |
| **3.2** Help find the best candidates | PASS | 0-100 score, dispositions, sorted pool (`07g-confirmed-pool.png`) | |
| **3.3** Show requirements met, skills/experience, strengths, gaps | PASS | Per-requirement verdict, points and evidence quote on every card (`07g-confirmed-pool.png`) | |
| **3.4** Short clear summary | PARTIAL | One-line narrative on each profile and card | Built from parsed fields; on messy parses the "title" can be wrong |
| **3.5** HR reviews before anything is shared | PASS | Provisional pool refuses shortlist/share/send with 409; share needs explicit approval, then a separate send; every actor except a recruiter refused (`07-request-A-ui.json`, `10-security.json`) | |
| **4.1** Find repeat applicants and update the profile | PASS | 64 reviews: 39 updated CV, 11 duplicate, 14 different; sourced updated CV recognised (`06b-sourced-outcomes.json`) | Updating is an HR decision by design |
| **4.2** Use name, e-mail and phone | PASS | Signals and weights shown per review; the ambiguous case (email on one person, phone on another) opened one review with 2 candidates and no recommendation (`04b-ambiguous.json`) | A date such as "2022 - 2024" was being read as a phone number; fixed and tested (`tests/test_contacts.py`) |
| **4.3** Update the existing profile instead of creating another | PASS | Merge & Update attaches to the existing candidate; candidate count unchanged | |
| **4.4** Merge repeated profiles | PASS | Recruiter-only merge with explicit confirmation; both documents kept; audit holds survivor and absorbed ids (`18-remaining.json`) | |
| **4.5** Keep the latest application | PASS | New CV is current, previous is superseded, applications ordered | |
| **5.1** Company | PASS | Request page and export | |
| **5.2** Job title | PASS | | |
| **5.3** Description and requirements | PASS | Description, proposed/approved/rejected requirements with the quote each came from (`07c-provisional-top.png`, `07e-requirements-review.png`) | |
| **5.4** Date received | PASS | `18-remaining.json` | |
| **5.5** Cadence employee handling it | PASS | Owner on the request and in the export | |
| **5.6** Candidates found for the role | PASS | Pool of 233 matched (171 excluded for an unmet mandatory requirement) on request A | |
| **5.7** Candidates shared | PASS | Sharing record after an approved send; request page shows 1 shared (`18-remaining.json`) | |
| **5.8** Quarterly export | PASS | `12-hiring-activity-export.xlsx`: ids, company, title, status, date, owner, requirement kinds, counts; no e-mail, phone or CV text | "Candidates found" is the pool, not the excluded |
| **5.9** Notes and comments | PASS | `18-remaining.json` | |
| **5.10** Upload related files | PASS | `18-remaining.json` | Files are listed; download is not available |
| **5.11** Updates and next steps | PASS | `18-remaining.json` | |
| **5.12** Record of support provided | PASS | Request + matches + shares + notes + audit; two requests stay independent | |
| **6.1** Add candidates from LinkedIn or approved sources | PASS | UI form and API (`16-05-source-form-filled.png`, `06-sourced.json`) | |
| **6.2** Contact details and CV | PASS | Name, e-mail, phone, notes, CV; the CV goes through normal intake | A candidate **without** a CV is refused (422), so a CV-less lead cannot be recorded |
| **6.3** Check for an existing candidate first | PASS | Re-sourcing the same file kept one profile; a different CV with the person's e-mail opened an "updated CV" review (`06b-sourced-outcomes.json`) | |
| **6.4** Show where the candidate was found | PASS | Source type and reference kept on the profile (`16-06-source-result.png`) | |
| **7.1** Keep information private | PARTIAL | Contacts, CV text, evidence and page previews are recruiter-only; engineer sees document metadata only; no e-mail in logs or audit (`10-security.json`) | The engineer's document list shows status, type and size; the web app uses one baked recruiter token |
| **7.2** Download or move information | PARTIAL | Backup job writes every table and file (`18-remaining.json`); hiring workbook export | No full CV-store download |
| **7.3** Only approved employees | PARTIAL | 53 of 54 routes answer 401 without a token; engineer 403 on 48 (`10-route-matrix.json`) | Two shared role tokens; per-person sign-in is not built |
| **7.4** Meet information security and privacy requirements | PARTIAL | RBAC matrix; audit immutability; unsafe problem-report content refused; formulas never executed; protected traits never inferred (`10-security.json`, `09-llm-edges.json`) | The client's own policy was not provided; the database role is a superuser; OpenAPI and `/docs` are public |
| **7.5** Record of important actions | PASS | `17-audit-shortlist.json`: every required event type present with actor and timestamp; UPDATE, DELETE and TRUNCATE rejected | An operator with database ownership can disable the trigger |
| **7.6** Backup copies | PASS | Local backup run: 33 tables plus files, manifest says `aws_backup_implemented=false` | AWS backup is a plan |
| **7.7** How long documents are kept | PASS | 730-day archive rule; the job ran (`archived=0`) | |
| **8.1** Easy for HR to use | PARTIAL | Dashboard, queue, request page with a stepper; `16-*.png` | No first-time user handoff was run; "Review Queue" and "Hiring requests received" numbers use specific definitions that can surprise |
| **8.3** Work with SharePoint, OneDrive, Outlook, Excel | PARTIAL | Excel import and export; mail to Mailpit; Graph and SES refuse until configured | SharePoint and OneDrive are not connected |
| **8.4** Allow later changes | PASS | Extractor, embedder, requirement reader, mail sender are providers; the model was swapped on and off during the run | |
| **8.5** Computers and phones | PASS | 54 page checks at 390, 820, 1440 px: no overflow, console error, failed request or broken image (`14-ui-sweep.json`, `16-13-mobile-command.png`) | |
| **8.2** (not in your list, included for completeness) One place for profiles, requests and reports | PASS | `16-01-command-center.png` | |

The challenge workbook is **NOT TESTABLE**: there is no `.xlsx` in `cvs/`. Other spreadsheets were not used as a substitute.
