# Agent design

Every agent implements `BaseAgent.run(context, task) -> AgentResult`. It receives dependencies through `AgentContext`; it must not create database sessions, call a named LLM SDK, or perform unapproved external side effects directly.

| Agent | Input | Output | Approval boundary |
| --- | --- | --- | --- |
| Research | company name/domain | profile, signals, pains, sources | publishing/enrichment writes |
| Qualification | lead + ICP | 0-100 score, rationale, decision | rejection/routing policy |
| Outreach | lead + research | draft message and rationale | any send |
| Inbound | incoming message | intent, extracted details, next action | reply/send or CRM change |
| Pipeline | lead history | status recommendation, next action | status changes when configured |

## Rules

- Agents return structured results; they do not return free-form UI responses as the system of record.
- Model reasoning is a summary suitable for review, never hidden chain-of-thought.
- Sources, model/provider metadata, and timestamps must be captured for research work.
- Human approval is represented by task metadata initially; the review UI comes later.

## Task states

`pending -> running -> completed | failed | waiting_for_approval | cancelled`

Only the task manager changes state. Retries, leases, and queue workers are deferred to the next implementation phase.
