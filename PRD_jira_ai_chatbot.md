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
