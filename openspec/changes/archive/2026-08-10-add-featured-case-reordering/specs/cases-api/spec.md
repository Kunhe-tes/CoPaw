## MODIFIED Requirements

### Requirement: Cases API endpoint for listing cases
The system SHALL provide `GET /featured-cases` to return active featured cases for the requesting source and BBK context.

#### Scenario: Head-office context requests runtime cases
- **WHEN** the client sends `GET /featured-cases` with a valid `X-Source-Id` and a missing, blank, or `100` `X-Bbk-Id`
- **THEN** the system SHALL return active head-office cases for that source ordered by their head-office queue positions

#### Scenario: Branch context requests runtime cases
- **WHEN** the client sends `GET /featured-cases` with a valid `X-Source-Id` and a non-head-office `X-Bbk-Id`
- **THEN** the system SHALL return active exact-branch cases first and active head-office cases second
- **AND** each group SHALL preserve its independent queue order

#### Scenario: Runtime request omits source
- **WHEN** the client sends `GET /featured-cases` without `X-Source-Id`
- **THEN** the system SHALL return an empty case list

### Requirement: Cases API management endpoints
The system SHALL provide exact-scope management endpoints for listing, creating, updating, reordering, and deleting featured cases in the relational store.

#### Scenario: Operator lists an exact branch scope
- **WHEN** the client sends `GET /featured-cases/admin/cases?bbk_id=<branch>&page=<page>&page_size=<size>` with `X-Source-Id`
- **THEN** the system SHALL return only cases whose logical scope matches that source and branch
- **AND** the response SHALL be ordered by `sort_order ASC, id ASC` with an exact-scope total

#### Scenario: Branch operator lists the head-office scope
- **WHEN** a non-head-office client requests `GET /featured-cases/admin/cases?bbk_id=100`
- **THEN** the system SHALL return the head-office scope as readable management data

#### Scenario: Operator creates a case
- **WHEN** the client sends `POST /featured-cases/admin/cases` with valid case data and writable source/BBK headers
- **THEN** the system SHALL create the case in that exact logical scope at the queue's final position
- **AND** the response SHALL include the persisted database ID and final ordering position

#### Scenario: Operator updates case content
- **WHEN** the client sends `PUT /featured-cases/admin/cases/{id}` for a case in its writable source/BBK scope
- **THEN** the system SHALL update the supplied content fields without directly applying `sort_order`

#### Scenario: Operator reorders a case
- **WHEN** the client sends `PUT /featured-cases/admin/cases/{id}/order` with body `{ "sort_order": K }` for a case in its writable source/BBK scope
- **THEN** the system SHALL atomically apply the `featured-case-ordering` rules
- **AND** the response SHALL contain `case_id`, final `sort_order`, and exact-scope `total`

#### Scenario: Operator deletes a case
- **WHEN** the client sends `DELETE /featured-cases/admin/cases/{id}` for a case in its writable source/BBK scope
- **THEN** the system SHALL delete it and atomically compact the surviving exact-scope queue

#### Scenario: Mutation targets another source
- **WHEN** a management mutation identifies a case whose `source_id` differs from `X-Source-Id`
- **THEN** the system SHALL reject the mutation without revealing or modifying that case

#### Scenario: Branch mutation targets a head-office case
- **WHEN** a non-head-office context attempts to create, edit, reorder, or delete a head-office case
- **THEN** the system SHALL reject the mutation without changing the head-office queue

#### Scenario: Mutation targets another branch
- **WHEN** a context attempts to edit, reorder, or delete a case outside its normalized BBK scope
- **THEN** the system SHALL reject the mutation without changing either queue

## REMOVED Requirements

### Requirement: Cases stored in JSON configuration file
**Reason**: Featured cases are already persisted in the `swe_featured_case` relational table, and atomic multi-row ordering requires one transactional store.

**Migration**: No client migration is required. Existing relational rows remain in place; logical head-office values and discontinuous ordering are normalized lazily when the affected queue is mutated.
