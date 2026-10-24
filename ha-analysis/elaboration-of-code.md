# hive-appliance: Elaboration of Code by Component

This document provides a human-readable description of every Python file listed in §2 ("Architecture by component") of `docs/summary.md`. Files are grouped by component as they appear in that table.

---

## collectors

### `collectors/base.py`
Defines `Collector`, an abstract base class. It specifies the interface that every collector must implement: a `collect()` method that returns a list of `Event` records. It also provides a shared `__init__` that stores a `name` and optional `label` for the collector. The class is intentionally minimal — the real behaviour lives in subclasses.

### `collectors/host_collector.py`
Implements `HostCollector`, a `Collector` subclass that gathers operating-system-level observations. On each `collect()` call it reads:
- OS name and version (via `/etc/os-release` or `platform`)
- Kernel version (`uname`)
- CPU info (model, core count)
- Memory (total and available, from `/proc/meminfo` or `os.psutil`)
- Disk usage on mounted filesystems
- Running process list (PID, name, CPU%, memory%)

Each observation becomes an `Event` with a type like `host.info`, `host.memory`, `host.disk`, or `host.processes`.

### `collectors/service_collector.py`
Implements `ServiceCollector`, a `Collector` subclass that queries systemd for service health. It shells out to `systemctl` (or reads `systemd` D-Bus if available) and records each service's:
- unit name, load state, active state, sub state
- whether it is enabled at boot
- last activation timestamp and any failure message

Events are typed `service.status`.

### `collectors/file_collector.py`
Implements `FileCollector`, a `Collector` subclass that checks the existence and integrity of a configured list of "critical files." For each file it records:
- whether the file exists
- its size and last-modified time
- a SHA-256 checksum (if the file exists)

Events are typed `file.check`. The file list is passed in via `__init__`.

---

## schemas (shared)

### `schemas/types.py`
The central type definitions for the appliance. Defines:
- **`Event`** — a timestamped observation with `source`, `type`, `data` (a dict), and a monotonically increasing `seq`.
- **`Plan`** — a repair plan with a list of `PlanStep` objects. Each step has a `verb` (must be in `ALLOWED_VERBS`), `target`, and `args`.
- **`Receipt`** — evidence of an executed step: exit code, stdout, stderr, timing, and a `simulated` flag for dry runs. Docstring says "Authenticated evidence" but carries no hash or signature.
- **`IncidentReport`** — an incident raised by the reducer: `incident_id`, `severity`, `source_event`, `description`, and `created_at`.
- **`ALLOWED_VERBS`** = `{"touch", "verify", "inspect", "restart", "noop"}` — the closed set of permitted repair actions. This is the safety invariant F1: no plan step may use a verb outside this set.
- **`RebindResult`** — the return type of `rebind_plan_owner()`, with `status` (`"applied"`, `"refused"`, `"uncertain"`) and `durable` flag.

### `schemas/event_store.py`
Implements `EventStore`, an append-only store for `Event` records backed by SQLite in WAL mode. It provides:
- `append(event)` — writes an event and returns its `seq`.
- `events(from_seq)` — reads events in order from a given sequence number.
- `latest_seq()` — the highest sequence number seen so far.
- `close()` — closes the database connection.

The store is thread-safe via a lock and uses a single shared connection per `EventStore` instance.

---

## controller

### `controller/appliance.py` (418 lines)
`Appliance` is the per-agent top-level orchestrator. It wires together:
- a list of `Collector`s
- an `EventStore`
- a `Reducer`

Its `tick()` method runs one full observe-reduce cycle: call every collector, append the resulting events to the store, feed new events to the reducer, and return any `IncidentReport`s the reducer produces. It also exposes `incidents()`, `state()`, and `events()` for the CLI. The appliance can be run in a loop (`run()`) or stepped manually.

### `controller/reducer.py` (899 lines)
`Reducer` maintains the agent's current state model. It processes `Event`s one at a time and produces state updates plus `IncidentReport`s. Key behaviours:
- **State model**: a dict tracking host health (CPU, memory, disk), service statuses, and file integrity.
- **Incident detection**: raises incidents when thresholds are crossed (e.g., memory below a watermark, a critical service inactive, a critical file missing or checksum changed).
- **Deduplication**: tracks the last incident per source to avoid raising the same incident repeatedly on every tick.
- **Resolution**: marks incidents resolved when the underlying condition clears.

---

## reasoning

### `reasoning/planner.py` (141 lines)
`Planner` turns `IncidentReport`s into `Plan`s. For each incident it:
1. Looks up the incident type and its associated repair recipe (a mapping from incident type to a list of plan steps).
2. Constructs a `Plan` with the appropriate steps, each using a verb from `ALLOWED_VERBS`.
3. Validates every step's verb against `ALLOWED_VERBS` (invariant F1) — if any step uses a disallowed verb, the plan is rejected.

The README mentions "runbooks, optional LLM/PLN projections" for this layer, but **no LLM, PLN, or runbook code exists** in `reasoning/` at this commit. The planner is a pure rule-based lookup.

---

## executor

### `executor/base.py`
Defines `Executor`, an abstract base class. It specifies the `execute(plan)` interface: take a `Plan`, run each `PlanStep`, and return a list of `Receipt`s (one per step). The base class provides a `_make_receipt()` helper that constructs a `Receipt` from a step, its result, and the `simulated` flag.

### `executor/shell_executor.py`
`ShellExecutor` is the production executor. It runs each `PlanStep` as a subprocess:
- For `verb = "restart"`: runs the configured restart command (e.g., `systemctl restart <service>`).
- For `verb = "touch"`: creates or updates the target file.
- For `verb = "inspect"`: runs an inspection command and captures output.
- For `verb = "verify"`: delegates to the verifier (but can also run a verification command).
- For `verb = "noop"`: does nothing.

Each step's stdout, stderr, exit code, and timing are captured into a `Receipt` with `simulated=False`.

### `executor/noop_executor.py`
`NoopExecutor` is the dry-run executor. It accepts any `Plan` and produces a `Receipt` for each step with `simulated=True`, exit code `0`, and empty output. It is used for testing, simulation, and the `--dry-run` CLI flag. The contract is that simulated receipts are never verified (invariant F6).

---

## verifier

### `verifier/base.py`
Defines `Verifier`, an abstract base class with a `verify(receipt)` method returning a boolean. It encodes the F6 contract in its docstring: **simulated receipts must never be verified as successful**. Subclasses are expected to check `receipt.simulated` and return `False` for any simulated receipt.

### `verifier/exit_code_verifier.py`
`ExitCodeVerifier` checks that a step succeeded by examining its exit code. It enforces F6 at line 29: if `receipt.simulated` is `True`, it returns `False` without checking the exit code. Otherwise it returns `receipt.exit_code == 0`.

### `verifier/file_verifier.py`
`FileVerifier` checks that a target file exists (and optionally matches an expected checksum) after a repair. **It does not enforce F6**: it never checks `receipt.simulated`, so a simulated receipt with exit code `0` would verify as `True`. This is a known discrepancy flagged in the summary — `ExitCodeVerifier` enforces the invariant but `FileVerifier` does not.

---

## recovery

### `recovery/checkpoint.py` (C09)
`CheckpointManager` snapshots the appliance's state (event store position, reducer state, open incidents) to a checkpoint file or directory. It provides:
- `checkpoint()` — serializes and writes the state atomically (temp file + rename).
- `restore()` — reads a checkpoint and replays the reducer to the saved state.
- `list_checkpoints()` — enumerates available checkpoints.

### `recovery/upgrade.py` (C10)
`UpgradeController` orchestrates controlled upgrades of the appliance itself. It implements the pre-flight → checkpoint → upgrade → verify → rollback pattern:
1. **Pre-flight**: checks that the new version's requirements are met.
2. **Checkpoint**: calls `CheckpointManager.checkpoint()` before proceeding.
3. **Upgrade**: applies the upgrade (e.g., pip install, nixos-rebuild).
4. **Verify**: runs the test suite or a health check.
5. **Rollback**: if verification fails, restores from the checkpoint.

---

## adapters

### `adapters/local_adapter.py`
`LocalAdapter` is the backend for the local host. It implements the `Adapter` interface: it knows how to run collectors against `localhost`, how to execute plans locally, and how to read local state. It is the default adapter used when no NixOS VM backend is configured.

### `adapters/nixos/adapter.py`
`NixOSAdapter` is the NixOS VM backend (M4). It implements the same `Adapter` interface but delegates to NixOS-specific tooling: it uses `NixOSConfigGenerator` to build configs, `NixOSVMManager` to manage VMs, and `NixOSExecutor` to run steps inside a VM.

### `adapters/nixos/config_generator.py`
`NixOSConfigGenerator` generates a NixOS configuration file (`.nix`) from the appliance's service definitions. It maps each service to its NixOS module, sets up networking, users, and systemd services, and writes the result to a temp file for `nix build` to consume.

### `adapters/nixos/nix_builder.py`
`NixOSNixBuilder` wraps `nix build` and `nix eval` invocations. It handles:
- building a NixOS configuration into a VM image
- evaluating Nix expressions (e.g., checking that a config type-checks)
- capturing build logs and exit codes

### `adapters/nixos/service_module.py`
`NixOSServiceModule` maps a logical service definition (name, command, restart policy, dependencies) to a NixOS `systemd.services` entry. It translates the appliance's service model into NixOS module syntax.

### `adapters/nixos/vm_manager.py`
`NixOSVMManager` manages the lifecycle of NixOS VMs used as test or deployment targets:
- `create()` — builds a VM from a NixOS config.
- `start()` — boots the VM.
- `stop()` — shuts it down.
- `destroy()` — removes the VM and its disk image.
- `status()` — checks if the VM is running.

### `adapters/nixos/executor.py`
`NixOSExecutor` runs plan steps inside a NixOS VM. It shares the same `Plan`/`Receipt` contract as `ShellExecutor`, but commands are executed via `nixos-shell` or `ssh` against the VM rather than locally. It produces `Receipt` objects with `simulated=False`.

---

## profiles

### `profiles/manager.py`
`ProfileManager` discovers the hive profile by running `hive-appliance profile`. It reads the appliance's configuration directory, finds the active profile (a YAML or JSON file describing which collectors, services, and critical files to monitor), and returns it. It is used by `Appliance.__init__` to configure itself at startup.

---

## hive (M5)

### `hive/adapter.py`
`AgentApplianceAdapter` wraps a per-agent `Appliance` and exposes it through a uniform interface that the hive layer can use. It delegates `tick()`, `incidents()`, `state()`, and `events()` to the underlying appliance, and adds an `agent_id` so the hive can distinguish one agent from another.

### `hive/event_bus.py`
`HiveEventBus` merges the event streams from all registered `AgentApplianceAdapter`s into one stream. It maintains a per-agent cursor (last `seq` seen) and on each `drain()` returns new events from every agent, tagged with their `agent_id`. This is the foundation for cross-agent correlation.

### `hive/reducer.py` (2021 lines — the largest module)
`HiveReducer` is the hive-level state machine. It consumes merged events from `HiveEventBus` and maintains a hive-wide state model. Key responsibilities:
- **Health rollup**: aggregates each agent's health into a hive-level summary (healthy, degraded, failed).
- **Cross-agent incident correlation**: when multiple agents report related incidents within a time window (e.g., ENOSPC within 60 seconds), they are merged into a single `HiveIncident`.
- **Plan ownership**: tracks which agent owns which plan. Plans can be owned by agents or by the hive itself.
- **Multi-plan supersession**: an incident may have several repair plans; when any one completes, the others are superseded (per `POLICY_MULTI_PLAN_SUPERSESSION.md`, decided by Ben Goertzel, 2026-10-06).
- **Rebind journal**: the write-ahead JSONL journal that makes `rebind_plan_owner()` durable across restarts. This is the most reviewed code in the repo (29 Astra reviews, 6949–7805). The journal uses SHA-256 hash chaining, fsync per append, and a two-phase pending/commit protocol. On restart, the full event stream is replayed from the beginning and committed rebinds are re-applied at their original `seq` position if the stream hash matches. See `docs/summary.md` §6 for full durability guarantees and failure modes.

### `hive/planner.py`
`HivePlanner` proposes hive-level actions. It has five rules:
1. **Restart failed agents**: if an agent is in a failed state, emit a `RESTART_AGENT` action.
2. **Delegate repairs**: if a per-agent incident is unowned, emit a `DELEGATE_REPAIR` action targeting that agent.
3. **Rebalance resources**: if one agent is overloaded and another has spare capacity, emit a `REBALANCE` action.
4. **Checkpoint healthy agents**: when any agent has failed and at least one healthy agent remains, emit `CHECKPOINT_ALL` targeting the healthy agents (reason: `agent_failed`). Note: the rule is named `_rule_checkpoint_failed` but it checkpoints the *healthy* agents, not the failed one.
5. **Handle stale agents**: if an agent has not reported in a configurable timeout, emit a `STALE_AGENT` action.

A `ROLLING_UPGRADE` action kind is defined in `hive/types.py` but **no planner rule emits it** and nothing in `hive/` or `tests/` uses it.

### `hive/shared_store.py`
`SharedStoreAdapter` adapts a shared store (e.g., the Conversation Store) so its health can be monitored by the hive. It exposes the same interface as `AgentApplianceAdapter` — `tick()`, `incidents()`, `state()`, `events()` — so the hive treats it like another agent for health purposes.

### `hive/dashboard.py`
`HealthDashboard` produces human-readable reports of hive health. It provides:
- `summary()` — a dict with per-agent status and hive rollup.
- `report()` — a text report suitable for display or logging.
- `trends()` — time-series of health metrics over recent ticks.

### `hive/appliance.py`
`HiveAppliance` is the top-level hive orchestrator. It:
- registers per-agent `AgentApplianceAdapter`s and `SharedStoreAdapter`s
- runs the `HiveEventBus`, `HiveReducer`, `HivePlanner` in a `tick()` loop
- owns the **rebind journal** (§6) — configures it, checks its health on startup, and refuses rebinds unless a journal path is set or `volatile_rebinds=True`
- exposes `rebind_plan_owner()` for operator rebinds
- exposes `status()` and `report()` (delegating to `HealthDashboard`)

### `hive/types.py`
Defines hive-level types:
- `HiveIncident` — a correlated incident spanning one or more agents.
- `HiveAction` and `HiveActionKind` — action kinds: `RESTART_AGENT`, `DELEGATE_REPAIR`, `REBALANCE`, `CHECKPOINT_ALL`, `STALE_AGENT`, and `ROLLING_UPGRADE` (defined but unused).
- `AgentHealth` — enum-like values: `healthy`, `degraded`, `failed`, `stale`.
- `JournalRecord` types: `journal_header`, `rebind_pending`, `rebind_commit` — the record types written to the rebind journal.

---

## conversation

### `conversation/store.py` (477 lines)
`MessageStore` is the core conversation store — an append-only SQLite database in WAL mode with FTS5 full-text search. It provides:
- `append(message)` — inserts a message, deduplicating on `(venue, venue_id, venue_message_id)`.
- `search(query)` — FTS5 full-text search over message content.
- `messages(from_ts)` — reads messages from a timestamp onward.
- Thread-local connections for safety under concurrent access.
- Schema includes tables for messages, threads, and attachment metadata.

### `conversation/threading.py` (375 lines)
`ThreadAssembler` groups messages into conversation threads. It uses three strategies in order:
1. **Reply chains**: messages with explicit `reply_to` fields are linked into chains.
2. **Time proximity**: messages within a configurable window (default 5 minutes) of each other in the same venue are grouped.
3. **Speaker-change heuristic**: when the speaker changes after a long silence, a new thread boundary is inferred.

The output is a set of `Thread` objects, each with a list of message IDs, a start time, and a summary.

### `conversation/semantic.py` (195 lines)
`SemanticIndex` provides embedding-based semantic search backed by ChromaDB. It:
- embeds each message using a configured embedding model
- stores embeddings in a ChromaDB collection keyed by message ID
- exposes `search(query_text, k)` — embeds the query, does a nearest-neighbour lookup, and returns the top-k message IDs with similarity scores
- supports incremental updates: `index(message)` adds a single message without rebuilding the collection

This component requires the `semantic` extra (`chromadb>=1.0`).

### `conversation/client.py` (544 lines)
`ConversationStoreClient` is the unified query API for the Conversation Store. It composes `MessageStore`, `SemanticIndex`, and `ThreadAssembler` and exposes:
- `search(query)` — full-text + semantic search, merged and ranked
- `thread_for(message_id)` — returns the thread containing a given message
- `recent_threads(n)` — the n most recent threads
- `messages_in_thread(thread_id)` — all messages in a thread
- `stats()` — store statistics (message count, thread count, venues)

This is the primary interface agents use to query conversation memory.

### `conversation/attachments.py` (930 lines)
Implements the attachment service. Manages:
- **Attachment metadata** in SQLite (same database as `MessageStore`): file path, venue, content type, size, download status.
- **Download queue**: work is claimed with a durable attempt ID and a lease. Only the owning attempt may publish its result; expired attempts are recovered.
- **Path safety**: generated paths stay under the configured root; external paths from callers are rejected.
- **Atomic downloads**: files are written to attempt-specific temp files, then atomically renamed on completion. A size limit (`max_bytes`) is enforced.
- **Reconciliation**: missing files, expired work, and orphaned partial downloads are cleaned up.

The contract (`docs/attachment-service.md`) lists invariants: message identification by `(venue, venue_id, venue_message_id)`, durable metadata, parent existence checks, path containment, durable work claiming, atomic completion, and reconciliation. Thumbnails and content-based MIME inspection are deliberately excluded.

### `conversation/downloaders.py`
Implements downloaders for each venue type. Downloaders are registered per `(venue, account_id)` pair and implement a `download(url, max_bytes)` interface that fetches a file up to `max_bytes` and writes it to a local path. A `DownloadManager.start()`/`stop()` controls the worker pool. Legacy two-argument downloaders (without `max_bytes`) are checked after the transfer, not during it, so they are **not qualified for untrusted remote content**.

### `conversation/bootstrap.py` (334 lines)
`ConversationBootstrapper` finds agent transcript files across the hive and bulk-ingests them. It:
- scans configured directories for `transcript.txt` files
- parses each file using the transcript collector
- inserts all messages into `MessageStore`
- indexes them in `SemanticIndex`
- threads them with `ThreadAssembler`
- reports statistics on completion

This is the one-time setup tool for populating the store from historical data.

### `conversation/types.py`
Defines conversation-level types:
- `Message` — `venue`, `venue_id`, `venue_message_id`, `sender`, `text`, `timestamp`, `reply_to` (optional), `attachments` (list).
- `Thread` — `thread_id`, `message_ids`, `start_ts`, `end_ts`, `summary`, `participant_count`.
- `Attachment` — `file_path`, `content_type`, `size`, `venue`, `download_status`, `attempt_id`.

### `conversation/collectors/base.py`
Defines `ConversationCollector`, an abstract base class for venue-specific message collectors. It specifies `collect()` returning a list of `Message` objects and `stop()` for graceful shutdown. This mirrors `collectors/base.py` but for conversation data.

### `conversation/collectors/telegram.py`
`TelegramCollector` is a pure adapter for Telegram Bot API message dicts. It transforms Telegram message JSON into the `Message` type. It does **not** handle credentials, polling, or webhook setup — those are the integrating service's responsibility. It exists only to normalize the Telegram message format.

### `conversation/collectors/transcript_file.py`
`TranscriptFileCollector` parses `transcript.txt` files. Each line is expected to match `[YYYY-MM-DD HH:MM:SS] sender: text`, with continuation lines (lines not starting with a timestamp) appended to the previous message. It produces `Message` objects with the parsed timestamp, sender, and text, and groups them into the venue `transcript`.

---

## cli

### `cli/cli.py`
The command-line entry point (`hive-appliance`). It parses subcommands and dispatches to the appropriate `Appliance` or `HiveAppliance` method. Subcommands:
- `observe` — run one collection tick and print events
- `profile` — discover and print the hive profile
- `incidents` — list open incidents
- `state` — print the current appliance state
- `events` — print events from the store
- `repair` — run the observe → plan → execute → verify cycle for one incident
- `run-plan` — execute a given plan file
- `checkpoint` — write a state checkpoint
- `restore` — restore from a checkpoint
- `upgrade` — run the upgrade controller

Supports `--dry-run` (uses `NoopExecutor`), `--agent` (selects a specific agent in hive mode), and `--json` (machine-readable output).

---

*Prepared by the Omega agent (derp) on 24 October 2026 for Charlie, per request to audit the codebase starting with §2 of `docs/summary.md`.*