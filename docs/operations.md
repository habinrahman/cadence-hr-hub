# Local operations

One command from the repository root:

```text
docker compose up --build -d
```

That builds the current backend and frontend, waits until Postgres is ready, runs migrations and provisions the demo users, then starts the API, worker, frontend, and Mailpit. An empty database volume is enough. Do not start a host API or worker first.

Demo tokens are `dev-recruiter-token` and `dev-engineer-token`. The API is on port 8000, the frontend on port 3000, and Mailpit on port 8025.

## Authentication

Local demo authentication is the shared bearer token already used by the API. `ENVIRONMENT=local` is the only mode that accepts tokens beginning with `dev-`. Compose sets that mode and passes the demo recruiter token into the frontend image as `NEXT_PUBLIC_RECRUITER_TOKEN`. The frontend source does not contain a token. A host `npm run dev` needs the same variable in the environment.

Production is a configuration boundary, not a new identity provider. Set `ENVIRONMENT=production` and inject `HUB_RECRUITER_TOKEN` and `HUB_ENGINEER_TOKEN` from a secret store. Those values must differ from each other and must not begin with `dev-`. The process refuses to start when a demo token is configured outside local. Per-person sign-in is still a later replacement of this token check.

`GET /health`, `/docs`, and `/openapi.json` are public. Every other API route requires an `Authorization` header. A missing header is 401. A recruiter token is required for hiring, reviews, shortlist, sharing, merge, Excel import and export, candidate contacts, CV text, the dashboard, and the work queue. An engineer token can list and update problem reports. An engineer token cannot read candidate contacts or CV evidence. System and agent actors are not HTTP callers. They cannot merge profiles, shortlist, share, or import a spreadsheet.

## Audit

`audit_events` accepts inserts. A database trigger rejects `UPDATE` and `DELETE`. Audit payloads stay limited to ids and codes. The table owner can still truncate the table or drop the trigger; the application role is that owner.

## Backup

Local/demo backups are implemented. From the API container:

```text
docker compose exec api python -m app.backup_job
```

That writes a folder of table snapshots and stored files under `BACKUP_DIR` (default `/var/backups` in Compose, a separate volume from Postgres). Source rows are not deleted. `aws_backup_implemented` in the manifest is false.

AWS production backup is a plan only and is not deployed: RDS automated backups with point-in-time recovery, encrypted, kept at least 7 days, and CV files in S3 with versioning.

## Retention

Finished and terminal documents are archived 730 days after they were received. Archived rows stay in the database. Documents still being processed are left alone.

The worker applies this when it starts. It can also be run with:

```text
docker compose exec api python -m app.retention_job
```
