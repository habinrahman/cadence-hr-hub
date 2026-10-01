# Copilot Studio: how this would be built, and where the dedicated hub still matters

**Status of this document.** The current product is the dedicated Cadence HR Intelligence Hub. **It was not built in
Copilot Studio, and nothing below has been built or tested in Copilot Studio.** This is a design comparison written from
published Microsoft capabilities. Where I am not sure a capability exists or works the way this problem needs, it is
marked **VALIDATE WITH MICROSOFT** rather than asserted either way. Nothing here says "Copilot cannot do X".

Legend used in every table:

| Label | Meaning |
|---|---|
| **NATIVE** | A Copilot Studio / Microsoft 365 capability used as it ships |
| **ACTION** | A custom action (Power Automate flow, custom connector, or HTTP/OpenAPI tool) that Copilot Studio calls |
| **BACKEND** | A custom service we own (the same code as the hub's API and worker) |
| **MODEL** | A language model or OCR service called by the agent or the backend |
| **HUMAN** | A recruiter decision. No system may make it |

## 1. The hub's workflow mapped onto a Microsoft architecture

```text
SharePoint / OneDrive / Outlook / website form
        |  Microsoft Graph / connectors
        v
Copilot Studio agent (orchestration, conversation, triggers)
        |  custom actions (OpenAPI tools / flows)
        v
Cadence services (BACKEND): candidate system of record, extraction, identity, matching, approvals, audit
        |
PostgreSQL + pgvector / object storage / search / model provider
        |
HUMAN approval (work queue)  ->  Microsoft-controlled outbound mail (Outlook / Graph)
```

| # | Workflow step | Who does it in a Copilot Studio design | Label |
|---|---|---|---|
| 1 | A company request arrives by email or web form | Outlook trigger or a Forms/web hook starts the agent | NATIVE (trigger) + ACTION |
| 2 | CVs arrive from SharePoint / OneDrive folders | Graph connector or a flow copies new files to the backend ingest endpoint | NATIVE (connector) + ACTION |
| 3 | File type, hashing, identical-bytes check, quarantine reasons | The same deterministic code as today | BACKEND |
| 4 | Text extraction (PDF / DOCX) | PyMuPDF / python-docx in the backend. Azure AI Document Intelligence is the Microsoft option | BACKEND (+ MODEL for OCR) |
| 5 | OCR for scans | Tesseract today. Azure AI Document Intelligence or AWS Textract in production | MODEL |
| 6 | Structured profile (experience, education, skills) | Deterministic parser today. A model could assist on messy layouts, always validated against the source text | BACKEND (+ MODEL, optional) |
| 7 | Duplicate / updated-CV detection | Weighted identity signals (email, phone, name, CV dates). Must be a tested, deterministic service | BACKEND |
| 8 | Recruiter decides Merge & Update / Delete Duplicate / Create New | A work-queue screen. An approval card in Teams is a possible front end for the same endpoint | HUMAN (+ ACTION for the card) |
| 9 | Search and semantic retrieval | pgvector today. Azure AI Search or Azure PostgreSQL with pgvector on Azure | BACKEND / external search |
| 10 | Requirement extraction from the job description | Local model today, validated and quote-checked. A Copilot generative step is possible, but its output must still pass the same validator | MODEL + BACKEND (validator) |
| 11 | Automatic provisional matching | Deterministic matcher in the backend, triggered by the agent | BACKEND (+ ACTION trigger) |
| 12 | Recruiter reviews/approves requirements | Work-queue screen (or an approval card) | HUMAN |
| 13 | Approved-only rematch, confirmed pool, score | Deterministic scoring (70/30 policy) in the backend | BACKEND |
| 14 | Shortlist | Recruiter action. Refused by the backend for any non-recruiter actor or a provisional pool | HUMAN + BACKEND (enforcement) |
| 15 | Share approval, then send | Two explicit recruiter steps. Sending goes through Graph / Outlook under the Microsoft tenant's mail policy | HUMAN + NATIVE (Outlook send) |
| 16 | Audit | Append-only audit in the database. Microsoft Purview records tenant activity in addition | BACKEND + NATIVE (Purview) |
| 17 | Problem report -> engineering | A flow can create a ticket (Planner / Azure DevOps / Jira). The hub keeps its own report with safe-fields validation | ACTION + BACKEND |

## 2. Where Copilot Studio is attractive (and why that is real)

- **Microsoft 365 reach.** SharePoint, OneDrive, Outlook and Teams are where the recruiters and their documents already are.
  Connectors and Graph access are the shortest route to the folders the team uses today. The current hub has **no**
  SharePoint or OneDrive connection (upload, sourcing form and Excel only). That is its largest gap against Cadence's stack.
- **Identity.** Entra ID sign-in and existing Microsoft permissions give per-person authentication. The hub has two shared role
  tokens and no per-person sign-in.
- **Adoption.** A team that lives in Teams and Outlook will use an agent there without learning another tool.
- **Orchestration.** Triggers, conversation, hand-offs, approvals (Power Automate approvals) and reminders are what the platform is built for.
- **Governance tooling.** Power Platform data-loss-prevention policies, environments and Purview auditing exist in the tenant already.

These reduce integration and adoption friction. They are a strong case for using Copilot Studio as the front door.

## 3. Trade-offs for this specific problem

Support levels: **Direct** = ships as a feature; **Connector/Action** = achievable through connectors or actions;
**Custom service** = needs a service we write; **External infra** = needs infrastructure outside Copilot Studio;
**Validate** = unclear, must be confirmed with Microsoft for this tenant.

| # | Need | Copilot Studio alone | Comment (what would live where) |
|---|---|---|---|
| 1 | Candidate system of record | Connector/Action (Dataverse or SQL via connector) | Copilot can read and write a store. The relational model and its constraints live in the store, not in the agent |
| 2 | CV versioning (current / superseded, history) | Custom service | Needs explicit relationships and transitions; a backend owns them |
| 3 | Duplicate / update detection | Custom service | Weighted signals, thresholds, "filename is not identity", tested on the real corpus. Copilot can orchestrate it, but the business rule would live in a controlled backend |
| 4 | Document parsing (PDF, DOCX, multi-column, Arabic) | Connector/Action (Document Intelligence) / Custom service | Azure AI Document Intelligence covers layout. Page-exact evidence and quote verification remain our logic. **Validate** fidelity on the 488-file corpus |
| 5 | OCR | Connector/Action | Document Intelligence (Azure) or Textract (AWS) via an action |
| 6 | Structured extraction with evidence | Custom service | Every field must quote the source text and be checked. Copilot can call it |
| 7 | Evidence traceability to page | Custom service | Needs stored page/quote pairs and a preview renderer |
| 8 | Vector search equivalent | External infra | Azure AI Search, or PostgreSQL with pgvector on Azure. Copilot Studio knowledge sources index SharePoint/files; **Validate** whether that gives structured filters plus exact-quote evidence per hit |
| 9 | Hybrid search (keyword + fuzzy + semantic + filters) | External infra / Custom service | Azure AI Search supports hybrid queries; filters on extracted fields need a structured index we build |
| 10 | Requirement extraction | Direct (generative) or Custom service | Copilot can propose. The quote-must-exist, no-protected-traits and no-injection checks are deterministic and belong in a validator we control |
| 11 | Deterministic mandatory-requirement rules | Custom service | An unmet mandatory requirement excludes; similarity can never override it. These are pass/fail rules, not prompts |
| 12 | Candidate scoring (70/30) | Custom service | Reproducible arithmetic, explainable per requirement |
| 13 | Approval state machines (provisional -> confirmed, shortlist, share) | Connector/Action + Custom service | Power Automate approvals can collect a decision. The rule that a provisional pool cannot be shortlisted or shared must be enforced where the data changes |
| 14 | Append-only audit | Custom service / External infra | Purview records activity. A domain audit (IDs, action, actor, no CV text) with database-level update/delete refusal is our design |
| 15 | Exact control of the model and provider | Validate | Copilot Studio supports choosing models and Azure AI Foundry. **Validate** per-call provider pinning, region, and fallback behaviour |
| 16 | Model fallback that is visible | Custom service | The hub records model, prompt version and whether the fallback answered |
| 17 | Testing and CI | Validate | Copilot Studio has testing tools. A 488-file regression suite with counts and a 307-test backend suite run in CI are what we have today |
| 18 | Custom security boundaries (PII by role, engineer never sees CV text) | Custom service | Role checks per field belong in the backend; the agent must not hold a broader token than the user |
| 19 | Detailed observability | Validate | Analytics exist; per-request traces with agent_run, latency and validation result are ours |
| 20 | Cost and latency predictability | Validate | Consumption-based licensing for agent messages/actions; the current deterministic pipeline has no per-file model cost |
| 21 | Data movement between Microsoft and AWS | Connector/Action | See section 4 |
| 22 | Work queue UI, shortlist review, evidence view | Custom service | A conversational surface is a poor fit for reviewing 60 candidates with evidence; a purpose-built screen fits |
| 23 | Mobile | Direct (Teams mobile) / Custom service | Teams mobile for conversation; the review screens need their own responsive layout |
| 24 | Reporting / quarterly export | Connector/Action | Excel / Power BI connectors. The field-minimisation rule (no email, phone or CV text) must be in the export code |
| 25 | Problem report -> engineering | Connector/Action | A flow can open a ticket. The safe-fields validation stays in the backend |

The pattern: Copilot Studio is strongest at **orchestration, identity and reach**; the pieces where the **rules must be
exact and testable** are the ones that would live in a controlled backend. This is a statement about where each rule is
easiest to freeze and test, not a statement that Copilot cannot express it.

## 4. Microsoft data boundary vs an AWS application

Isa's question: why would the client have Microsoft data sources while the application runs on AWS?

```text
MICROSOFT DATA LAYER            INTEGRATION BOUNDARY                       AWS APPLICATION LAYER
SharePoint / OneDrive   -->   Microsoft Graph / approved connectors  -->  ALB (HTTPS)
Outlook                       scoped application permissions,            ECS Fargate (API, worker)
Entra ID (identity)           service identity, least privilege,         RDS PostgreSQL + pgvector
                              TLS in transit, explicit allow-list        S3 (CV files, versioned, KMS)
                              of sites/folders, no tenant-wide read      SQS (background jobs, production)
                                                                          KMS / Secrets Manager
                                                                          CloudWatch / CloudTrail
                                                                          approved model provider (Bedrock)
```

- AWS is **not** assumed to be "more secure" than Azure. The case for this layout is only: the client already hosts
  on AWS (Bahrain region), data moves across a **narrow, audited, least-privilege** boundary, and
  residency, encryption, authorisation and model data-processing terms are explicit and reviewable.
- Only what the workflow needs crosses: CV files and request text in, candidate notices out. Nothing is copied tenant-wide.
- **If the client prefers Azure**, the same workflow maps one-for-one: ALB -> Application Gateway, ECS Fargate -> Container Apps,
  RDS PostgreSQL + pgvector -> Azure Database for PostgreSQL (pgvector), S3 -> Blob Storage, SQS -> Service Bus,
  KMS / Secrets Manager -> Key Vault, CloudWatch / CloudTrail -> Azure Monitor / Activity Log, Bedrock -> Azure OpenAI or Foundry,
  Textract -> Document Intelligence. Identity becomes Entra end to end. **The business workflow and code do not change;**
  the environment variables, images and infrastructure do.
- This move is not free: connectors, permissions and data-processing terms must be re-approved (**VALIDATE WITH MICROSOFT / the client's security team**).

## 5. Decision

Copilot Studio is attractive for the Microsoft-native integration, identity and orchestration layer. A dedicated backend
remains useful where the client needs exact control over the candidate data model, CV/version relationships,
deterministic matching rules, evidence, search, approval state, audit, security, model/provider abstraction and testing.

A realistic production architecture is therefore **hybrid**:

```text
Microsoft systems -> Graph / connectors -> Copilot Studio (orchestration / user interaction)
      -> controlled Cadence services -> PostgreSQL / object storage / search / AI
      -> human approval -> Microsoft-controlled external communication
```

A fully dedicated internal application is equally valid if it gives better control and usability for the client's workflow.
The choice should rest on security, integration effort, accuracy, cost, latency, maintainability, workflow complexity,
data residency and operational ownership, **not** on brand.

What the hub does worse than a Copilot Studio pilot **today**: no SharePoint/OneDrive connection, no Entra sign-in,
local Mailpit instead of Outlook. A Copilot pilot would be ahead on those three on day one.

## 6. Three-to-five minute explanation for Isa

1. **Start with the honest scope (20 s).** "What you are seeing is a dedicated hub. It is not built in Copilot Studio. I
   mapped the same workflow onto Microsoft so you can see the boundary."
2. **Where Copilot Studio is strong (45 s).** "Cadence lives in SharePoint, OneDrive, Outlook and Teams, and on Entra ID.
   Copilot Studio gives reach, identity and orchestration with almost no integration work. That is real value and it is
   where the current hub is weakest."
3. **What the hard part is (60 s).** "The costly mistakes here are specific: merging two people, sharing a candidate before a
   recruiter agrees, inventing a skill that is not in the CV, or letting a model clear a mandatory requirement. Those are
   pass/fail rules. You can ask an agent to follow them. You can also put them in code where they are frozen, unit-tested and
   checked on all 488 real CVs. That is the part I would keep in a backend."
4. **The hybrid (60 s).** "So in production I would use Copilot Studio as the front door and orchestrator, and a small set of
   controlled Cadence services behind it for identity, matching, approvals and audit. The recruiter's decisions stay on a
   review screen; the agent calls the same endpoints a person would and is refused the consequential ones."
5. **How it connects (45 s).** "Graph with scoped, least-privilege permissions to named SharePoint sites. Files go into the
   backend; candidates and audit live in PostgreSQL. Outbound mail goes through Outlook under the tenant's policy."
6. **Close (20 s).** "It is a choice between Copilot-front-door, dedicated, or hybrid. I would choose hybrid for production,
   and I would validate the open items with Microsoft first."

## 7. Questions Isa may ask

| Question | Answer |
|---|---|
| If we did this in Copilot Studio, how would you build it? | Agent triggered by Outlook/Forms/SharePoint events; custom actions (OpenAPI tools) call the Cadence backend for ingest, matching and approvals; approvals surface as Teams adaptive cards that call the same recruiter endpoints; Purview plus the domain audit for traceability |
| If Copilot can do most of it, why did you build this? | Most of the *orchestration* yes. The rules that must be exact and testable (identity, evidence, mandatory requirements, approval gates, audit) are easiest to freeze, test and replay as code. I built that layer first and it is what a Copilot front end would call |
| What are the actual limitations? | Unverified for this tenant: per-call model pinning and region, structured filters plus exact-quote evidence from knowledge sources, test/CI tooling for a 488-file regression, licensing cost at volume. I would validate these with Microsoft rather than assert them |
| Could we use Copilot only as the front door? | Yes. That is the hybrid. Copilot for conversation, triggers and identity; the backend for every consequential rule |
| How would SharePoint/OneDrive connect to AWS? | Graph with application permissions scoped to named sites and folders, a service identity, TLS, and an allow-list; a flow or connector pushes new files to the ingest endpoint behind the ALB |
| Where would the candidate database live? | PostgreSQL (RDS in the AWS design; Azure Database for PostgreSQL if the client is on Azure). One canonical profile per person, with documents and audit |
| Where would embeddings live? | In the same PostgreSQL (pgvector) next to the chunks, or Azure AI Search. Today they are a local hash approximation, not a semantic model; production needs an approved embedding model |
| Where would the duplicate/update logic live? | In the backend service. The agent can ask for a relationship assessment and show it to a recruiter; it cannot decide it |
| Who owns the approval decision? | Always a named recruiter. The provisional -> confirmed gate, shortlist and share are refused by the backend for any other actor, including the agent |
| What happens if the model gets it wrong? | For requirements: every quote must exist in the job description, protected traits and injections are rejected, a mandatory item needs requiring language or it is demoted, and HR approves before the pool is confirmed. For matching: a wrong model cannot clear a mandatory gap because scoring is deterministic |
| How do you prevent Copilot from directly making a consequential change? | The agent's identity is a non-human actor. The backend refuses shortlist, share, merge and decision calls from it (403 `human_required`), and the approval state machine only accepts a named recruiter |
| Would you choose Copilot, dedicated or hybrid in production? | Hybrid, after validating the open Microsoft items. Dedicated if the client wants one owner and one security boundary; Copilot-only only if the rules can be frozen and tested there to the same standard |
