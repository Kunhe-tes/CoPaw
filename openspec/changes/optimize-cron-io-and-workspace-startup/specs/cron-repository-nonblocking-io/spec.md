## ADDED Requirements

### Requirement: Cron job repository operations avoid event loop blocking

The cron job JSON repository SHALL execute file reads, file writes, JSON serialization, JSON parsing, and pydantic validation outside the event loop.

#### Scenario: Loading jobs does not run synchronous file work on the event loop
- **WHEN** `JsonJobRepository.load()` is awaited
- **THEN** the repository MUST perform the blocking filesystem and JSON/model work through a worker thread boundary

#### Scenario: Saving jobs does not run synchronous file work on the event loop
- **WHEN** `JsonJobRepository.save()` is awaited
- **THEN** the repository MUST perform directory creation, JSON/model work, temporary file write, and atomic replacement through a worker thread boundary

### Requirement: Cron job lookup reuses valid repository snapshots

The cron job JSON repository SHALL maintain an in-process job index keyed by job id and SHALL reuse it when the backing `jobs.json` file signature has not changed.

#### Scenario: Repeated job lookup uses cached index
- **WHEN** `get_job(job_id)` is called repeatedly and `jobs.json` has the same file signature
- **THEN** the repository MUST return the matching job from the cached index without reloading and revalidating the full file

#### Scenario: Changed jobs file refreshes cache
- **WHEN** `jobs.json` has a changed file signature
- **THEN** the next `get_job(job_id)` MUST reload the file, rebuild the job index, and return data from the refreshed snapshot

#### Scenario: Save updates repository snapshot
- **WHEN** `save(jobs_file)` completes successfully
- **THEN** subsequent `get_job(job_id)` calls in the same process MUST observe the saved data without requiring another file read

#### Scenario: Failed load does not hide invalid storage
- **WHEN** `jobs.json` cannot be parsed or validated
- **THEN** the repository MUST raise the load error and MUST NOT silently return stale cached jobs

### Requirement: Dream cron file processing avoids event loop blocking

Dream cron file processing SHALL execute `dream_logs.json` reads and synchronous dream archive maintenance outside the event loop.

#### Scenario: Dream record id loading is offloaded
- **WHEN** dream cron collects existing dream record ids before execution
- **THEN** reading and parsing `dream_logs.json` MUST happen through a worker thread boundary

#### Scenario: Dream record dual-write reads are offloaded
- **WHEN** dream cron reads new dream records after execution for dual-write
- **THEN** reading and parsing `dream_logs.json` MUST happen through a worker thread boundary

#### Scenario: Dream archive maintenance is offloaded
- **WHEN** dream cron runs archive maintenance after memory dreaming
- **THEN** the synchronous maintenance function MUST execute through a worker thread boundary
