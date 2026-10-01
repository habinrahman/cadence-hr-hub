# Cadence HR Intelligence Hub: 48-hour build challenge

Build a working internal tool for Cadence's HR team in 48 hours.

Cadence's HR team hires for Cadence and supports its subsidiaries with their external hiring. A subsidiary asks for help filling a role. The team searches the CVs it holds and sends back a shortlist. Today every step of that is manual.

Your job is to build the **HR Intelligence Hub**: a private, AI-integrated operations layer that connects the team's CVs, files, templates, emails and hiring rules in one internal tool. AI agents do the reading and the checking in the background. The HR team reviews and approves every decision.

We give you the CVs and the requirements. Anything else you need to test with, such as hiring requests, email templates or hiring rules, create your own samples of.

This repo holds three things:

| | |
|---|---|
| `README.md` | This brief: the problem, the rules, what to hand in and how we judge |
| `REQUIREMENTS.md` | The HR team's full list of what the system must do. This is your scope |
| `cvs/` | The bulk CV folder you build and test against |

---

## 1. The problems

The HR team has described seven problems. Your hub has to solve all of them.

1. **Candidate information is not in one place.** A candidate's CV sits in SharePoint or OneDrive. Their contact details and application history sit in an Excel sheet. No single record holds all of it.
2. **CVs cannot be searched.** The folders search by file name only. `CV_Ahmed.pdf` does not say whether Ahmed holds an AMM certificate or has eight years in manufacturing. Finding every candidate with a CFA, or everyone with five years in banking, means opening files one at a time.
3. **Duplicate applicants.** A CV sent through the careers site is saved as another file. Nothing decides whether it is a duplicate, an update or a new person. One candidate can sit in the folder as five separate people, and nobody can tell which of the five CVs is current.
4. **Companies have no route to submit a hiring request.** A company emails the HR team. One email says "we need two accountants". Another attaches a full job description. Someone reads every email, pulls out the details by hand and chases whatever is missing before the search can start.
5. **Matching CVs to requests is manual.** To shortlist for a role, the team opens each CV and reads it against the company's requirements. That costs about 480 hours a year. Nothing records why a candidate was picked or passed over.
6. **Requests are not tracked.** Nobody can say how many hiring requests are still open, from which companies or for which roles. Nobody can say which CVs went to which company, or who on the team handled each request.
7. **Sourced candidates cannot be added.** A candidate found on LinkedIn or through a referral has no CV in SharePoint and no entry anywhere. Nothing records their details, where they were found, or whether the team already holds them.

**Read [REQUIREMENTS.md](REQUIREMENTS.md) line by line before you design anything.** The problems above are the summary. The requirements are the detail, in eight sections: one place for candidate data, search, matching, duplicates, request tracking, sourced candidates, keeping information safe, and ease of use. Every line must map to something in your build.

---

## 2. What the hub must be

These are fixed. How you meet them is up to you.

### 2.1 It runs on AI agents

The hub is built around AI agents that work in the background. An agent notices that something new has arrived, works out what it is, does the work, and passes anything that needs a decision to a person. Nobody should have to press "process" for the hub to do its job.

Decide which agents you need, what each one is responsible for, what triggers it, what tools it can use, and what it is not allowed to do. Be ready to draw them.

The hub is not a chatbot. A search bar is fine. A chat window as the main way to use the tool is not.

### 2.2 It mixes deterministic code with AI, and AI means more than LLMs

Some parts of this problem have one right answer and should be plain code. Some need judgment on messy language and should use a model. Some sit in between.

Large language models are one kind of AI. Also consider OCR, embedding models, classifiers, similarity scoring and ranking. Use each where it fits. For every AI component, you will be asked:

- why code could not do it
- why this kind of model and not another
- what happens when it is wrong, slow or unavailable
- what it costs

Use a relational database for the structured data and vector embeddings for search and matching.

### 2.3 The HR team has the final say

Agents can read, extract, classify, score, suggest and draft. A named person on the HR team decides anything that changes a record others rely on, and anything sent outside Cadence. Work out which actions those are. Every decision is saved with who made it, when, and what the agent had suggested.

### 2.4 Every action is logged, and problems reach an engineer

Keep a log of every action a person takes and every step an agent takes. An HR user should be able to see what happened to a candidate or a request. An engineer should be able to see exactly what an agent did, with what input, and what it produced.

When something looks wrong, an HR user must be able to flag it from where they are, in a sentence or two. The hub then raises an engineering ticket with the logs an engineer needs to fix it, without the HR user copying anything by hand. For the demo, the tickets can live in the hub itself, seen by an engineer account.

### 2.5 The interface is a core deliverable

A hub with good agents and a confusing screen will not get used. The HR team does not want to learn a new kind of tool. They live in Outlook, Excel and SharePoint. Anyone on the team should be able to open your hub and know what to do without training.

Aim for a hub where a recruiter always knows what needs them next, what the agents are doing, and how to undo a mistake. Borrow from the tools they already use. It must also work on a phone.

We judge this as heavily as security. On judging day we hand your app to someone who has never seen it and watch them work.

### 2.6 It holds personal data, so build it to be defended

We will try to break it. Assume every file, form and field comes from someone you do not trust, and be ready to show how the hub holds up. Never infer nationality, age, gender or religion from a name, a photo or a school. Passwords, if you have any, are hashed properly. Secrets stay out of the repo.

### 2.7 It will be hosted on AWS

Cadence runs on AWS, and this hub will be hosted there. You do not have to deploy it in 48 hours. You do have to come prepared to walk us through exactly how you would: the services, the network, how staff sign in, permissions, encryption, secrets, how background work scales, where logs live, the region, backups, how code reaches production, and what it costs each month. Build so the move to AWS changes configuration, not code.

Locally, the whole hub starts with one command.

---

## 3. How to approach it

We will not tell you how to build this. This section tells you what a good result looks like and how strong engineers tend to get there. Use it to check your design, not as a list of features to copy.

### 3.1 Start with the people who will use it

- Walk through a recruiter's week today, from a company asking for help to a shortlist going out. Where does the time go, and where does information get lost?
- Walk through the same week with your hub. What does the recruiter still do, what do your agents do, and where do the two meet?
- For each numbered requirement in `REQUIREMENTS.md`, decide whether it is best met by code, by AI, by a person, or by a mix. That table is the skeleton of your design.

### 3.2 What a good result looks like to the HR team

Each point describes an outcome. How you get there is your design.

- **Getting CVs in.** A recruiter never has to open a file to know what is in it. The hub copes with whatever a real shared drive holds, and anything it could not handle reaches a person with a reason. Nothing disappears silently.
- **One person, one profile.** The team can trust that a candidate appears once, with their latest details, and that nothing from their history was lost. When the hub is unsure whether two records are the same person, a person decides, and can see what the hub based its view on. Joining two different people is worse than missing a duplicate.
- **Finding people.** A recruiter can ask for the things they ask for today, such as a certificate, years in an industry or a past job title, and get an answer they can check.
- **Hiring requests.** A company can get a complete request to the team without a chain of emails. The team knows what was asked, when, by whom, and who on the team owns it.
- **Shortlists.** A recruiter can read why each candidate is on the list, in plain words, backed by the CV. They can change the list before anything leaves. Think about what a company should receive and what should stay inside Cadence.
- **Tracking and reports.** Any question a manager asks about the team's work this quarter can be answered from the hub without counting by hand.
- **Trust over time.** When an agent gets something wrong, the team can tell, can say so in a sentence, and can see it get fixed.

### 3.3 Principles that lead to strong submissions

- **Code for what has one right answer, AI for what needs judgment, people for what matters.** If you can write the rule down, write it as code.
- **Show your working.** Every AI output should trace back to the text it came from, the model that produced it and when.
- **Earn autonomy.** Let agents act alone only where you can show they are reliable, and make it easy for a person to step in everywhere else.
- **Measure before you trust.** Hand-label a sample of CVs from the folder, decide what the right answers are, and test your agents against it. Report the numbers.
- **Fail loudly and safely.** A slow model, a broken file or a bad input should never stop the rest of the work or corrupt a record.
- **Build for the day after the demo.** Real volumes, real staff, and AWS. Choose things you can run, monitor and explain.

### 3.4 A sensible order for 48 hours

1. Read `REQUIREMENTS.md` and sketch the current and new process flows (section 5, items 3 and 4) before writing code.
2. Get one CV all the way through: in, read, profiled, searchable, logged.
3. Run the whole folder and look hard at what went wrong. Most of the lessons are there.
4. Add duplicates, then requests, then matching and shortlists, with a person approving at each step that needs one.
5. Add logs, problem reports, tracking and the report.
6. Spend real time on the interface. Put it in front of someone who has not seen it before judging day.
7. Write the AWS plan and the submission as you go, not in the last hour.

We would rather see every problem in section 1 handled simply than two handled beautifully.

Where the brief leaves something open, make a decision, write down the assumption, and be ready to defend it.

---

## 4. The CVs

`cvs/` holds about 490 files taken from the HR team's shared CV folder. **Build and test against these files.** Do not bring in other CVs. On judging day we run your hub against this folder and compare the results with our answer key.

The folder is what years of shared-drive use looks like: PDFs, Word files and images saved by different people over time. File names were chosen by whoever saved them and sometimes mention other organisations. Many of the candidates are students and recent graduates, and many are based outside Bahrain. Treat the folder as you would the real thing.

You will need hiring requests to test matching. Write your own. On judging day we will give you new CVs, an Excel list of existing candidates, and hiring requests written the way companies write them today: short notes, full job descriptions and attachments. We will play the company and enter each request through whatever route your hub gives companies.

**Most of these CVs belong to real people.** They contain names, phone numbers, emails, addresses and photos. By cloning this repo you agree to these rules:

1. Use the files only for this challenge.
2. Keep your own repository private. Do not commit the CVs, extracted text, embeddings or database dumps to it. Point your app at your local clone of this repo.
3. Send CV content only to model providers that do not train on it, under commercial terms you have checked. No consumer chat apps or free online tools.
4. Do not contact anyone in the CVs. Any email your hub sends goes to a local mail catcher.
5. After judging, delete every copy: files, databases, indexes, logs and cloud resources, and confirm to Isa at isa@usecadence.tech.

---

## 5. What to hand in

Build in your own private repository and invite `isa-cadence` before the deadline. The 48 hours start at kickoff, where we confirm the exact deadline. At its root, add a `SUBMISSION.md` covering:

1. **How to run it.** One command from a fresh clone, plus the demo sign-in accounts.
2. **Requirements coverage.** One row per numbered requirement in `REQUIREMENTS.md` (1.1 to 8.5): where it is covered, how to see it, and whether it is done, partial or not built, with the reason.
3. **Current process flow.** A diagram of how the HR team works today, from a company's request to a shortlist. Show where time goes and where information is lost.
4. **New process flow.** A diagram of the same journey through your hub. Mark every step as deterministic code, AI, or a human decision. Show your agents, what triggers them, where people approve, and where problem reports go.
5. **Architecture and AWS plan.** Your components, and how you would host them on AWS, with a monthly cost for processing 5,000 new CVs and handling 20 hiring requests each month. Show the working.
6. **Every AI component.** What it does, which model or method, why not code, how it fails, what it costs.
7. **The case against Copilot Studio.** Cadence is considering building this in Microsoft Copilot Studio. Write one page on why your approach is better for this problem. Say what Copilot Studio would do well, too. One-sided arguments score lower.
8. **Results on the CV folder.** Run the whole `cvs/` folder and report what happened: profiles created, files rejected and why, duplicates found, failures, run time and model cost.
9. **Known gaps.** What does not work yet, what you would do next, and what you would need from Cadence to go live.

Diagrams can be Mermaid, Excalidraw, draw.io or images, committed to your repo.

---

## 6. Judging day

1. **Live demo, about 30 minutes.** You start from an empty database with one command and load `cvs/`. We then give you inputs you have not seen and ask you to take them through the hub.
2. **Hand-over test, about 10 minutes.** Someone who has never seen your hub uses it on their own.
3. **Code walkthrough, about 45 minutes.** We pick where to start. For any line we point at, you explain what it does, why it is there and what happens if its input is wrong.
4. **AWS walkthrough, about 15 minutes.** You take us through how the hub would run in production.

| Area | Weight |
|---|---|
| Works end to end | 15% |
| Accuracy against our answer key | 15% |
| Interface and ease of use | 15% |
| Agents, and the split between code and AI | 15% |
| Human control, logs and problem reports | 15% |
| Security and edge cases | 15% |
| AWS plan and the Copilot Studio case | 10% |

---

## 7. Rules

- Write your own code. You may use AI coding assistants, but you must be able to explain every line. "The assistant wrote that" is not an answer in the walkthrough.
- Open-source libraries and managed AWS services are fine.
- Questions during the 48 hours go to Isa at isa@usecadence.tech. Answers are shared with every candidate.
