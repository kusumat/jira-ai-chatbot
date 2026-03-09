# PRD: Jira-Aware AI Chatbot (End-to-End Setup + Integration)

## 1. Executive Summary
Build a chatbot that answers project questions using Jira tickets, comments, status, and history. Deliverables include Jira bootstrap (user/project/sample 20 tickets), data integration pipeline, and chatbot Q&A. Goal: users ask plain-language questions and get grounded answers with Jira ticket citations.

## 2. Product Goal
Create a command-driven system to:
- Provision Jira workspace artifacts (where permissions allow)
- Pull Jira data continuously
- Answer user questions with evidence from Jira comments and ticket metadata

## 3. Problem Statement
Teams spend too much time manually searching Jira for updates and discussion context. Existing chatbots answer generically without project-grounded evidence. Need trusted, citation-backed answers from live Jira data.

## 4. Scope
### In Scope
- Create Jira user (if org admin API permission exists)
- Create Jira project
- Create 20 tickets with comments
- Build Jira-to-chatbot ingestion integration
- Build chatbot Q&A with citations

### Out of Scope
- Advanced workflow automation
- Enterprise SSO/governance hardening
- Multi-tool ingestion (Confluence/Slack/GitHub)

## 5. Users
PMs, Engineering Managers, Developers, QA, Scrum Masters.

## 6. Functional Requirements
- Jira setup: service user, project, 20 seed tickets
- Ingestion: full + incremental sync for issues/comments/changelog
- Retrieval: chunk + embed + vector index with metadata filtering
- Chatbot: natural language Q&A with citations
- Fallback: explicit “insufficient evidence” response

## 7. Non-Functional Requirements
- p95 response under 8 seconds
- Data freshness under 10 minutes
- Retries/backoff for upstream failures
- Secrets in env vars only
- Role-based filtering (mock in MVP)

## 8. Architecture (Text Diagram)
User (CLI/Web Chat)
-> Chat API
-> Retrieval Orchestrator
-> Vector DB (FAISS/Chroma) + Metadata DB (MySQL/SQLite)
<- Jira Ingestion Worker <- Jira REST API
-> LLM Provider (OpenAI/Claude)
-> Answer Formatter (citations/confidence)

## 9. Data Flow
1. Bootstrap Jira user/project/tickets
2. Ingestion worker fetches issues/comments/changelog
3. Normalize + chunk + embed + index
4. User asks question
5. Retriever fetches relevant chunks with role/project filtering
6. LLM generates grounded response
7. Return answer with citations

## 10. Jira Bootstrap Requirements
- Create Jira user: needs org admin permissions (or manual invite)
- Create Jira project: Jira admin permissions
- Create 20 tickets: scripted bulk creation with comments/status variation
- Suggested mix: 8 Stories, 7 Tasks, 5 Bugs

## 11. Chatbot Response Requirements
Output structure:
- Summary
- Key findings
- Citations (issue keys, comment snippets)
- Confidence + gaps
No unsupported claims without retrieved evidence.

## 12. Security & Governance
- Least-privilege API tokens
- Redaction option before embedding
- Query + citation audit logs
- Access filters before retrieval

## 13. Milestones
- M1: Jira bootstrap scripts
- M2: Ingestion + vector indexing
- M3: Chatbot Q&A with comment citations
- M4: Reliability hardening

## 14. Success Metrics
- >=90% answers include valid citations
- >=80% relevance rating from stakeholders
- <10 minutes sync lag
- 20/20 seed tickets retrievable

## 15. Risks & Mitigations
- Admin API restrictions: manual setup fallback
- Jira rate limits: backoff + incremental sync
- Low-quality comments: confidence and insufficiency fallback

## 16. Future Extension: Fluid Ticket-to-Code Workflow
This section explores an ambitious add-on that transforms the Jira chatbot into a semi-autonomous developer assistant. The goal is to automate the path from **ticket creation** to **QA-ready code changes** when tickets are authored in a prescribed format.

### 16.1 Objective
Enable a fluid web app that monitors Jira for new issues meeting a structured template. When such a ticket appears, the system:

1. Detects the creation event via Jira webhooks or periodic polling.
2. Authenticates with GitHub using a PAT token (stored securely, rotated regularly).
3. Clones or fetches the relevant project repository branch.
4. Uses **Spring AI** (or equivalent LLM-backed code intelligence) to analyze the ticket description, determine the needed fix or implementation, and generate corresponding code modifications.
5. Applies the patch to the codebase, then runs a lightweight compile/test suite (optional) to validate syntax.
6. Commits the changes and pushes them to a dedicated `qa/<ticket-id>` branch for human review and validation.

### 16.2 Functional Requirements
- **Ticket template enforcement**: only issues with a defined header (e.g. `Fix: <module>` or `Feature: <description>`) trigger the workflow.
- **Webhook listener**: a small service that receives events from Jira and queues work items.
- **Repository mapping**: configuration mapping Jira projects to GitHub repos/branches.
- **Code synthesis engine**: integration with Spring AI or custom LLM prompting for code fix generation.
- **Branch management**: ability to create and name QA branches automatically and clean them up when merged or closed.
- **Audit log**: record of ticket, generated diff, author (bot), and timestamp.
- **Security**: PAT token with minimal scopes (repo:public_repo or repo) stored in a secrets manager; all operations signed.

### 16.3 Non-Functional Requirements
- Processing latency under 5 minutes from ticket creation to QA branch push.
- Fail-safe rollback if code generation or push fails; notify an operator via Slack/email.
- Rate limits/usage caps for GitHub API and Spring AI.
- Ability to disable the pipeline per project or Jira issue type.

### 16.4 Architecture Addendum
Extend the architecture diagram with a new **Automation Worker** branch:
```
Jira Webhook → Automation Service → Scripted Repo Checkout → Spring AI → Patch Apply → GitHub (qa/<ticket>)
``` 
The automation service could be built in Python/Node and run as a serverless function or container.

### 16.5 Success Metrics for Extension
- ≥70% of valid tickets produce a syntactically correct QA branch.
- Developer review acceptance rate ≥50% (less need for manual fixes).
- Mean time from ticket to branch <10 minutes.

### 16.6 Risks & Mitigations (Extension)
- Incorrect code generation: limit to trivial fixes/boilerplate first, require human review.
- Security breach through PAT leak: use vaults + rotate tokens.
- Repository race conditions: lock per repo during automation.
- LLM hallucinations: enforce strict prompt templates and post-generation linting.

This extension paves the way toward a **semi-autonomous development workflow**, where developers can describe small tasks in Jira and see them materialize into code with minimal hands‑on intervention. It complements the core chatbot by closing the loop from issue understanding to actionable code.