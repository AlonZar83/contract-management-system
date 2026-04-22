# Contract & Reminder App

Multi-tenant Contract & Reminder platform for managing contracts, renewal timelines, and automated notifications.

## Repository Structure

- `backend/`: FastAPI server and business logic.
- `database/`: SQL schema and migration assets.
- `shared/`: Shared configuration and environment templates.

## Initial Database Model

The initial schema is in `database/schema.sql` and includes:

- `tenants`
- `users`
- `tenant_users`
- `contracts`
- `contract_files`
- `reminders`
- `notifications`
- `audit_logs`

## Quick Start

1. Copy `shared/.env.example` to your local environment file and update values.
2. Create a PostgreSQL database.
3. Apply `database/schema.sql`.
4. Implement and run the FastAPI backend in `backend/`.

## Notes

- Secrets are not stored in this repository.
- The schema is designed for tenant isolation and reminder automation from day one.
