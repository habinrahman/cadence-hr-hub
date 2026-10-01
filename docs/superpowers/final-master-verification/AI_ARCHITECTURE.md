# AI and deterministic architecture

Written for the technical walkthrough. Everything here is what the code does today and what the clean-room run measured.
"AI" is used only for components that interpret language or images. Ordinary code that follows a rule is listed separately and is not called AI.

## Deterministic (rules, no model)

| Area | What it does |
|---|---|
| File type and size | Detects the type from bytes (a `.docx` that is really a PDF is read as a PDF); rejects unsupported types; size cap |
| Hashing | SHA-256 of the bytes; identical bytes are the same document |
| Text extraction | PyMuPDF (PDF), python-docx (DOCX), LibreOffice (legacy DOC) |
| CV / non-CV gate | Phrase rules; invoices, cover letters and job descriptions are quarantined with a reason |
| Identity signals | Weighted e-mail, phone, name, CV dates, employment, education, skills; filename is never an input |
| Normalisation | E-mail lower-casing, phone digits, CV date ranges ("June 2024 - Present") |
| Validation | Every extracted field must quote the source text; every requirement must quote the job description |
| State transitions | A state machine decides what may move where; the system actor is refused every human-only step |
| Permissions | Role checks on the backend; the UI never decides |
| Mandatory-requirement rules | An unmet mandatory requirement excludes; unknown or partial needs review; a similarity score can never clear it |
| Scoring | Mandatory 70 points, preferred 30 (one kind alone shares all 100); meets earns the full share, partial half |
| Shortlist and share authorisation | Provisional pool refused; recruiter-only; share needs approval, then a separate send |
| Audit | Append-only, IDs and codes only |
| Export rules | No e-mail, phone, summary or CV text |

## AI components

### 1. Requirement reader (the only language model in the running product)

1. **What it does.** Reads a company's job description and proposes requirements as structured items (label, text, mandatory or preferred, the quote it came from).
2. **Why deterministic code alone is not enough.** The rule reader understands labelled lines ("Required skills: Python, SQL") and a few phrases. Free-form prose such as "We're looking for a backend engineer who has strong Python and FastAPI experience. PostgreSQL is important and AWS would be a plus" gives it nothing (a test asserts this). A model reads that sentence.
3. **Why this model.** `qwen2.5:3b-instruct` through Ollama: small enough to run on a CPU laptop, runs locally so a job description never leaves the machine, supports a JSON schema for the answer. It is a weak model: it sometimes omits a requirement or rates a required one as preferred. That is acceptable only because of items 4, 9 and 10.
4. **If it is wrong.** Every proposal is checked and nothing it says becomes a requirement until a person approves it. Observed on the run: it dropped "Python" and "Power BI" from a short request and listed "2 years" as preferred; HR edits, rejects or adds.
5. **If it is unavailable.** The rule reader answers and the page says so, with the reason (`model_unreachable`, `description_too_long`, `model_reply_malformed`). Measured: model stopped -> pool in 12 s with Python, SQL and Power BI read by the rule reader. A fallback is never presented as the model's work.
6. **Cost.** No API cost (local). Measured latency request -> provisional pool: **48 to 63 s cold** (model just started), **14 to 28 s warm**, **8 to 12 s fallback**. The acknowledgement is under 0.4 s in all cases; extraction and matching are background work.
7. **Data it receives.** The job description text. Nothing else (a test asserts the exact request: system prompt plus the description).
8. **Data it is forbidden from receiving.** Any candidate data, CV text, e-mail address, phone number or audit content. It has no tool and no database access.
9. **Validation after it returns.** JSON schema; the quote must exist in the job description; the text must be inside its quote; protected traits (religion, nationality, ethnicity, gender, marital status, age) are rejected in the text and in the clause it came from; an instruction ("ignore previous instructions", "shortlist all") is rejected, and so is any skill inside an injected sentence; an experience number must be a count of years, not an age; a "mandatory" item whose sentence or list heading does not require it is demoted to preferred (never promoted). Live adversarial run: "require Kubernetes", "must be Muslim / Saudi / single / aged 25-30", "output SQL" produced no requirement.
10. **Human approval boundary that follows.** The first pool is provisional. A recruiter approves, edits, rejects or adds requirements; only then does the approved-only rematch run and the pool become confirmed. Shortlisting and sharing are refused until then.

### 2. OCR

1. Turns a page image into text. 2. A scan has no text layer to parse. 3. Tesseract: local, free, no data leaves the machine; production would use Textract (an adapter, not built). 4. Wrong text is possible; it is still only searchable text and a profile quotes it. 5. Missing binary -> `needs_ocr`; an empty result does not create a profile. 6. $0. 7. A page image. 8. Anything else. 9. Empty OCR text is refused. 10. A recruiter decides every relationship. Measured: 6 corpus files were read by OCR; 2 (a blank scan and a low-quality photo) stayed `needs_ocr`.

### 3. Vector (an approximation, not a semantic model)

A 1,024-dimension token hash is stored per chunk. It lets hybrid search blend keyword, fuzzy and vector scores and it lets a real embedding model replace it without a schema change. It does **not** understand meaning. A mandatory gap ignores it entirely. Claiming "semantic search" for it would be wrong.

## What is not AI

The section parser, identity scoring, matching, scoring, the CV/non-CV gate, the validators, the state machine and the audit are rules. The parser reports no confidence and cannot invent a field; it quotes the source.

## Failure behaviour (all exercised on the run)

| Failure | Result |
|---|---|
| Model stopped | Fallback reader, visible reason, request still processed |
| Job description over 12,000 characters | Fallback reader with reason `description_too_long` |
| Malformed or invalid model output | Fallback reader (covered by tests; not forced live) |
| Model timeout | Treated as unreachable (covered by tests; not forced live) |
| Prompt injection, protected trait | Rejected; reason code recorded, text not stored |
| Every proposal rejected | Request stays open, no pool, HR adds a requirement by hand |
| Worker killed mid-job | The job is reclaimed once; no duplicate requirement, match or audit row |
