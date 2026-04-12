# Change Governance: Approval Queue

> Back to [README](../README.md)

CogniMesh enforces a simple invariant: **nothing changes in Gold without human approval.** This is implemented as a DB-backed approval workflow, not a checkbox.

## Governance Flow

```
Register/Update UC ──→ UC status: "pending_approval"
                              │
                              ▼
                    approval_queue table (status: "pending")
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
              POST /approve        POST /reject
                    │                   │
                    ▼                   ▼
            UC activated           UC stays inactive
            Gold refreshed         No Gold changes
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/approvals` | GET | List all pending approval requests |
| `/approvals/history` | GET | Approval history (filterable by UC, with limit) |
| `/approvals/{id}` | GET | Get details of a specific approval request |
| `/approvals/{id}/approve` | POST | Approve — activates UC + triggers Gold refresh |
| `/approvals/{id}/reject` | POST | Reject — UC stays inactive, Gold unchanged |

## Example Workflow

### List pending approvals

```bash
curl -s localhost:8000/approvals | jq '.[].id'
```

### Review a specific approval

```bash
curl -s localhost:8000/approvals/1 | jq
```

### Approve it (triggers Gold refresh)

```bash
curl -X POST "localhost:8000/approvals/1/approve?reviewed_by=alice&note=LGTM"
```

### Or reject it

```bash
curl -X POST "localhost:8000/approvals/1/reject?reviewed_by=alice&reason=needs+schema+review"
```

## What Gets Stored

The `cognimesh_internal.approval_queue` table captures:

| Column | Description |
|--------|-------------|
| `uc_id` | Which UC is being changed |
| `action` | What's happening: `register`, `update`, `deactivate`, `refresh` |
| `status` | `pending` → `approved` or `rejected` |
| `request_data` | Full UC definition at time of submission (JSONB) |
| `requested_by` / `reviewed_by` | Who submitted / who approved |
| `reviewed_at` | When the decision was made |
| `review_note` | Optional comment explaining the decision |

## What This Is NOT

- **No UI** — API-only. Integrate with your existing review tooling.
- **No Slack/email notifications** — Add a webhook in your deployment.
- **No multi-stage approval** — Single approver, not a committee.

This is deliberately minimal. The goal is enforcing the invariant (no unreviewed Gold changes), not replacing your organization's review process. Wire the API into Slack, PagerDuty, or a custom dashboard as needed.
