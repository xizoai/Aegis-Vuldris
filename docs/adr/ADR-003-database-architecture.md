# ADR-003: Database Architecture

## Status

Accepted

## Date

2026-09-10

## Context

Aegis Vuldris requires persistent storage for application data such as users, AI model targets, test configurations, test runs, findings, evaluations, evidence metadata, reports, audit events, and related security information.

The database architecture must support:

- reliable transactional behavior
- strong data integrity
- concurrent application access
- migrations
- automated testing
- secure handling of sensitive assessment data
- future horizontal scaling
- clear separation between application logic and persistence
- reproducible development environments

Because Aegis Vuldris is intended to become a production-grade security testing platform, the database must not be treated as a temporary implementation detail.

## Decision

Aegis Vuldris will use **PostgreSQL** as its primary relational database.

The application will access PostgreSQL through a dedicated persistence layer using:

- SQLAlchemy for database access and ORM functionality
- Alembic for schema migrations
- PostgreSQL transactions for atomic operations
- UUIDs for externally meaningful entity identifiers where appropriate
- UTC timestamps for persisted temporal data

Database access will remain behind application-level repository and service boundaries. Domain logic must not depend directly on database-specific implementation details.

## Database Layer Architecture

The backend will separate persistence responsibilities into clear layers:

1. API layer
2. Application/service layer
3. Domain layer
4. Repository/persistence layer
5. SQLAlchemy models
6. PostgreSQL database

The API layer must not directly construct arbitrary database queries.

Application services will coordinate transactions and business operations.

Repositories will encapsulate database-specific access patterns.

## Schema Management

Database schema changes will be managed exclusively through **Alembic migrations**.

Schema changes must:

- be version controlled
- be reviewed
- be reproducible
- support fresh database initialization
- avoid manual production schema modification
- include appropriate migration tests where necessary

Migration files must be committed to the repository.

The database schema must not be silently modified by application startup.

## Transactions

Operations that modify multiple related records must use explicit transaction boundaries.

Transactions should:

- be as short as practical
- preserve atomicity
- roll back safely on failure
- avoid holding locks unnecessarily
- prevent partially persisted security findings or test results

Long-running AI model calls must not unnecessarily hold database transactions open.

## Identifiers

Aegis Vuldris will use UUID-based identifiers for major externally addressable entities where appropriate.

Identifiers must not expose sequential database implementation details unnecessarily.

Database-generated internal identifiers may be used where they provide a clear implementation benefit, but externally exposed resources should use stable opaque identifiers.

## Timestamps

Persisted timestamps will use UTC.

Entities requiring temporal tracking should maintain appropriate fields such as:

- created_at
- updated_at

Security-sensitive records may additionally require event timestamps or immutable audit timestamps.

Application and database timestamp behavior should be consistent and testable.

## Data Integrity

PostgreSQL constraints should be used wherever practical to enforce data integrity.

Examples include:

- primary keys
- foreign keys
- unique constraints
- non-null constraints
- appropriate check constraints

Application validation remains necessary, but database constraints provide an additional defense-in-depth layer.

## Sensitive Assessment Data

Aegis Vuldris may process sensitive information including:

- prompts
- model responses
- attack payloads
- evaluation evidence
- security findings
- target configuration
- authentication-related metadata
- audit records

Sensitive data must not automatically be treated as safe merely because it is stored in the database.

The application must define appropriate data classification, retention, access-control, and deletion policies.

Secrets such as API keys, passwords, tokens, and private credentials must not be stored in plaintext unless there is a specifically reviewed and justified design requiring secure encrypted storage.

## Authorization

Database access does not replace application authorization.

Every request accessing tenant-, user-, project-, target-, test-, finding-, or report-level data must pass through application authorization controls.

Where appropriate, PostgreSQL capabilities such as roles and row-level security may provide additional defense in depth, but they must not be used as a substitute for the application's authorization model.

## Database Credentials

The application must use a dedicated database account with the minimum privileges required by the application.

Administrative database credentials must not be used by the normal application runtime.

Database credentials must be supplied through secure configuration or secret-management mechanisms and must never be committed to Git.

Development credentials must be separate from production credentials.

## Connection Management

The backend will use a managed database connection pool.

The implementation must define safe limits for:

- maximum connections
- connection lifetime
- connection timeout
- idle behavior

The application must handle temporary database connectivity failures without exposing sensitive internal information.

## Local Development

PostgreSQL will be available through Docker Compose for local development.

The development database must be disposable and reproducible.

Local database storage must not be committed to Git.

Database credentials used for local development must come from environment configuration rather than hard-coded source code.

## Testing

Database-dependent functionality will be tested using isolated test databases or appropriately isolated PostgreSQL test environments.

Tests must verify:

- migrations
- constraints
- repository behavior
- transaction rollback
- authorization boundaries
- concurrent behavior where relevant
- persistence of security findings and evidence metadata

Tests must not depend on a developer's personal production database.

## Performance and Scaling

PostgreSQL is selected because it provides mature transactional guarantees, indexing, concurrency control, and operational tooling.

Initial development will favor correctness and maintainability over premature optimization.

Performance optimization will use evidence from measurements such as:

- query latency
- database load
- connection utilization
- index effectiveness
- transaction duration

Indexes will be introduced based on known access patterns and measured requirements.

## Backup and Recovery

Production deployments must implement:

- automated database backups
- tested restore procedures
- appropriate backup retention
- recovery objectives
- monitoring for backup failures

A backup that has never been restored successfully must not be considered a verified recovery mechanism.

## Security Considerations

The database architecture follows the Aegis Vuldris security baseline and threat model.

Relevant controls include:

- least-privilege database accounts
- encrypted database connections where supported
- strict application authorization
- parameterized queries
- migration review
- secret protection
- auditability
- data retention controls
- backup protection
- isolation between environments

Database queries must never be constructed through unsafe string concatenation using untrusted input.

## Alternatives Considered

### SQLite

Rejected as the primary production database because Aegis Vuldris is expected to support concurrent workloads, background test execution, multiple users, and production deployments.

SQLite may still be useful for narrowly scoped local tooling or tests where its limitations are explicitly understood.

### MySQL / MariaDB

Not selected because PostgreSQL provides the desired feature set and ecosystem for the project's expected relational, transactional, and security requirements.

### MongoDB

Not selected as the primary database because Aegis Vuldris's core entities have strong relationships and transactional requirements that map naturally to a relational model.

Document-oriented storage may be considered later for specialized workloads if a demonstrated requirement exists.

## Consequences

### Positive

- mature relational database
- strong transactional guarantees
- excellent integrity constraints
- strong ecosystem
- good support for complex queries
- suitable for production workloads
- well supported by Python tooling
- straightforward Docker-based development
- clear migration workflow

### Negative

- additional operational complexity compared with SQLite
- requires database lifecycle management
- requires migration discipline
- requires backup and recovery planning
- connection pooling and transaction management add application complexity

These costs are accepted because production reliability and data integrity are more important than minimizing initial setup complexity.

## Future Considerations

The architecture leaves room for future additions such as:

- PostgreSQL read replicas
- connection poolers
- partitioning for very large test-result datasets
- row-level security
- encrypted sensitive fields
- database-level auditing
- object storage for large evidence artifacts
- separate analytics storage
- caching
- search infrastructure

These technologies should only be introduced when justified by measurable requirements.

## Related Decisions

- `docs/adr/ADR-001-backend-framework.md`
- `docs/security-baseline.md`
- `docs/security-boundaries.md`
- `docs/threat-model.md`

## Decision Summary

**PostgreSQL is the primary Aegis Vuldris database, accessed through SQLAlchemy and managed through Alembic migrations, with application-level authorization, explicit transaction boundaries, least-privilege credentials, and defense-in-depth database controls.**
