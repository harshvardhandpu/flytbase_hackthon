# Database schema

PostgreSQL is the source of truth. UUID primary keys and UTC timestamps are used throughout. JSONB fields retain evolving agent payloads without blocking the hackathon; promote stable fields to typed columns only after usage is proven.

| Table | Purpose | Key relationships |
| --- | --- | --- |
| `companies` | account/profile facts | has leads, contacts, reports |
| `leads` | qualified prospect/pipeline record | belongs to company; optional contact |
| `contacts` | people at a company | belongs to company |
| `research_reports` | research result and sources | belongs to company; optional lead/task |
| `agent_tasks` | unit of agent work and approval state | optional company/lead; has logs |
| `agent_logs` | auditable execution events | belongs to task |
| `conversations` | inbound/outbound message threads | optional company/lead/contact |

`lead.status` is intentionally a string during Phase 1: `new`, `researching`, `qualified`, `nurturing`, `meeting_booked`, `disqualified`. Application validation will be added with pipeline workflow logic. Indexes support company domain, lead status/email, task status/type, report company, and conversation lead.

Run `alembic upgrade head` after PostgreSQL is configured. The initial migration is the baseline; create new migrations for all schema changes.
