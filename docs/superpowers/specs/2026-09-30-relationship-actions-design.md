# CV relationship review: Merge & Update, Delete Duplicate, Create New — design

Date: 2026-09-30
Status: implemented from the client clarification; "Delete Duplicate = archive" chosen by the user. Not committed.

## What already existed (unchanged)

- Detection and confidence: `app/domain/confidence.py` (email, phone, name, document hash, CV dates, explicit version,
  employment, education, skills, semantic). Filenames are not identity evidence. Ambiguous or low-confidence
  assessments recommend nothing and offer all three actions.
- State machine: `duplicate_review` `pending -> accepted_update | recorded_duplicate | created_separate`, all three
  `USER_ONLY`. `decide_duplicate_review` rejects any non-user actor (`human_required`); `POST /reviews/{id}/decision`
  requires the recruiter role. A decided review cannot be decided again (409).
- Merge & Update: attaches the CV, makes it current, sets `supersedes_document_id`, keeps the previous CV on the
  candidate as history, adds an application.
- Create New Candidate: new profile, CV linked to it, existing candidate untouched.

## What changed

- **Delete Duplicate** (`record_duplicate`) used to attach the duplicate to the candidate as a non-current CV plus an
  application. It now archives only the duplicate upload through the existing `archived` document state (retention
  model: rows and file kept, nothing hard-deleted). The duplicate is not attached, gets no application and never
  becomes current. A document a candidate already has, or the current CV, cannot be archived this way.
- Audit for that decision adds `outcome: "archived"` and `canonical_document_id` (new allowlisted key). Details stay
  IDs and safe metadata; the existing allowlist still rejects any other key.
- Excel rows have no uploaded CV, so their duplicate outcome is unchanged and keeps the label "Record as duplicate".
- UI labels: "Merge & Update Profile", "Delete Duplicate" (danger tone), "Create New Candidate", in the compare
  workspace and the shared relationship-review panel (intake, sourcing, Excel). Every action now opens a confirmation
  that states what will happen; the confirm buttons read "Yes, ..." so the first click never decides.
