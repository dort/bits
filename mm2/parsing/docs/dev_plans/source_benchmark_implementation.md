# Source pipeline scale measurements

Started 2026-11-11 by Codex. This covers the source side of milestone 6 in the
[integrated plan](stream_splitter_and_earley_pipeline.md), independently of
Claude's parser benchmarks under `earley/`.

## Measurement contract

Use fresh Python 3.14 worker processes and a synthetic binary reader that emits
bounded reads from one repeated unit. Increasing unit count must not allocate
a source-sized input or metadata array in the driver. Workloads cover dense
tokens, long tokens, tiny units, bounded-regex headers, Unicode/CRLF, and gaps.

Measure four stopping points: decoding, splitting, lexical source records, and
the real version-2 bundle writer. Timers around iterator advancement separate
upstream work from downstream work; report their overhead and keep independent
whole-stage wall times. Full bundle validation is a separate measured phase.
Validate exact decoded reconstruction, unit counts, and token counts against
the fixture before calling a run successful.

For bundle runs, observe the existing atomic publication helper to measure the
actual staged files and rename operation. Files are append-only before that
point; distinguish logical file sizes from allocated filesystem blocks. Measure
cleanup after worker termination. Worker groups must be stopped on timeout and
interruption before their scratch directory is removed.

Record interpreter/platform/source-code identity, specification fingerprints,
all limits, input/output sizes, stage times, resident-memory peaks, and semantic
validation results in streamed JSONL rows. Qualify memory against an explicit
fixed envelope rather than assuming that two similar readings prove a bound.
Use a small default matrix and explicit larger runs. Store generated artifacts
under ignored `lexer/output/streaming-benchmarks/`.

## Alternatives

The existing `benchmarks.measure` deliberately builds a finite fixture and can
retain token records when isolating serialization. Those microbenchmarks remain
useful, but cannot establish streaming memory behavior across source sizes.
`benchmarks.bundles` measures metadata growth from already separated pieces.
The new `benchmarks.streaming` composes the real decoder, splitter, lexer, and
writer without replacing either older measurement's distinct purpose.

Subtracting separate wall-clock runs would mix process noise with stage costs.
Nested iterator timers instead measure work while that iterator is advancing;
subtracting its upstream totals provides an attributed time within the same run.
These timings include instrumentation overhead and are not CPU profiler samples.

## Reproduction and interpretation

The implementation is [`lexer/benchmarks/streaming.py`](../../lexer/benchmarks/streaming.py).
Run the commands below from `lexer/`. Each output directory must be new.

```bash
.venv/bin/python -m benchmarks.streaming \
  --out output/streaming-benchmarks/quick-20261111

.venv/bin/python -m benchmarks.streaming --workloads long \
  --units 1024 4096 16384 65536 --stages decode split lex bundle \
  --timeout-seconds 600 --max-file-mib 2048 \
  --out output/streaming-benchmarks/long-scale-20261111

.venv/bin/python -m benchmarks.streaming --workloads tiny gaps \
  --units 1024 4096 16384 65536 --stages bundle \
  --out output/streaming-benchmarks/unit-scale-20261111

.venv/bin/python -m benchmarks.streaming --workloads dense \
  --units 1024 4096 16384 --stages bundle \
  --out output/streaming-benchmarks/dense-scale-20261111
```

Measurements use CPython 3.14.10 built with GCC 13.3.0, Linux x86_64, and
65,536-byte input reads. The source identity recorded in these reports is
`921c9dcf409f7afb51c4e51bb4f983e77c2a33f9f4cc86313608896e8680df67`.
It hashes the benchmark and `tokenizer/*.py`; each row also records lexical and
split specification fingerprints. The raw `meta.json` files record the full
runtime, platform, command arguments, and start time. Generated reports remain
in ignored `lexer/output/streaming-benchmarks/`; the tables here preserve their
principal results in repository documentation.

The memory qualification is 64 MiB peak worker resident memory, including
verification. Each worker additionally has a 512 MiB virtual-address limit and
a 1 GiB per-file limit, raised to 2 GiB for the long-source scale run. The
supervisor timeout includes writing and verification: 120 seconds by default,
600 seconds for that larger run. Qualification failures, semantic mismatches,
worker failures, and timeouts produce a nonzero exit.

Pipeline wall time includes the reconstruction/token oracle, synthetic input
generation and hashing, and timing instrumentation. Separate stage attribution
subtracts measured upstream advancement and reports oracle work separately.
Published-bundle verification is an additional phase. These are single
observations on a shared machine, not repeated estimates with confidence
intervals; minor timing differences should not be treated as regressions.
The input is generated lazily, so these results do not measure input-disk
throughput. Output uses the actual filesystem and writer, without claiming
durability through `fsync`.

## Results

### Quick matrix

All 72 cases passed: six workloads, unit counts 16/64/256, and four stopping
points. Peak worker memory ranged from 26.4 to 27.3 MiB. At 256 units, the
complete bundle measurements were:

| Workload | Input bytes | Write pipeline seconds | Verify seconds | Bundle bytes | Output/input |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dense tokens | 16,384 | 0.322 | 0.560 | 4,423,014 | 269.96× |
| Long tokens | 1,048,576 | 0.440 | 0.285 | 5,522,410 | 5.27× |
| Tiny units | 512 | 0.035 | 0.071 | 539,048 | 1052.83× |
| Regex headers | 32,768 | 0.042 | 0.079 | 729,795 | 22.27× |
| Unicode/CRLF | 48,128 | 0.037 | 0.070 | 857,635 | 17.82× |
| Explicit gaps | 512 | 0.032 | 0.063 | 543,492 | 1061.51× |

This variation comes from different token and unit counts per input byte and
the bundle's JSONL, MM2, and index representations. A single output-expansion
factor or throughput figure would conceal those differences.

### Source-size growth with fixed 4 KiB units

All 16 larger cases passed, including the four stopping points at every size.
Complete bundle results:

| Source MiB | Units/tokens | Write pipeline seconds | Verify seconds | Peak worker MiB | Bundle bytes | Output/input |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | 1,024 | 1.689 | 1.130 | 27.25 | 22,160,522 | 5.28× |
| 16 | 4,096 | 6.658 | 4.557 | 27.12 | 89,316,490 | 5.32× |
| 64 | 16,384 | 26.129 | 18.405 | 27.07 | 359,259,286 | 5.35× |
| 256 | 65,536 | 106.065 | 74.202 | 27.37 | 1,444,047,640 | 5.38× |

At 256 MiB, separate fresh-process stopping-point wall times were 0.285 seconds
for decoding, 11.502 seconds through splitting, 37.048 seconds through lexical
records, and 106.065 seconds through bundle publication. These independently
observed totals should not be subtracted to estimate individual stages.

Within that complete bundle run, attributed times were 13.00 seconds for
splitting, 28.36 seconds for lexical/envelope work, and 64.00 seconds for bundle
validation, serialization, and indexing. Synthetic byte generation/hashing
took 0.170 seconds, decoding 0.085 seconds, and the correctness oracle 0.450
seconds. The writer's attributed time groups its internal validation,
serialization, and index operations; distinguishing their individual costs
requires a subsequent profile.

The largest bundle contained 1,063,134,922 MM2 bytes, 347,121,874 token-JSONL
bytes, 33,789,740 stream-index bytes, and a 1,104-byte manifest. Its staged and
published logical sizes matched. Allocated file blocks totaled 1,444,069,376
bytes at the published observation, excluding directory metadata. Atomic
publication took 0.000158 seconds; cleanup after verification took 0.119 seconds.
Staging and publication rename the same files, so their sizes are not two
simultaneous copies. Cleanup removed every case's scratch data.

The 64-fold increase in source size did not produce a corresponding increase
in resident memory. All observed peaks stayed below the explicit 64 MiB
qualification envelope. This supports the streaming design for these fixtures,
unit bounds, runtime, and measurement sizes; it is not a proof for every
specification or a benchmark of a single 256 MiB unit.

### Unit-count growth with two-character inputs

All eight cases passed. Each unit contains one token; the `gaps` workload
emits the newline as a separate gap record. Memory peaks include verification.

| Workload | Units | Source bytes | Write pipeline seconds | Verify seconds | Peak worker MiB | Bundle bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Tiny | 1,024 | 2,048 | 0.131 | 0.281 | 26.82 | 2,165,969 |
| Tiny | 4,096 | 8,192 | 0.494 | 1.100 | 26.88 | 8,768,674 |
| Tiny | 16,384 | 32,768 | 2.023 | 4.460 | 27.16 | 35,444,211 |
| Tiny | 65,536 | 131,072 | 7.458 | 16.760 | 27.33 | 143,025,407 |
| Gaps | 1,024 | 2,048 | 0.120 | 0.247 | 26.86 | 2,186,860 |
| Gaps | 4,096 | 8,192 | 0.475 | 1.026 | 27.02 | 8,857,149 |
| Gaps | 16,384 | 32,768 | 1.988 | 4.107 | 26.97 | 35,853,878 |
| Gaps | 65,536 | 131,072 | 7.575 | 17.285 | 27.33 | 144,790,706 |

The largest tiny-unit and gap bundles expanded their input by 1,091.20 and
1,104.67 times respectively. Their fixed per-unit representations dominate
the two-character payload. Peak memory remains within the same envelope as
the larger-text workload, while disk use and processing time grow with unit
count. Read-back verification takes more than twice the write-pipeline time
in these cases; it deserves its own profile before changing its checks.

### Token-count growth

All three dense-token cases passed. Each 64-character unit has 27 tokens.

| Source bytes | Units | Tokens | Write pipeline seconds | Verify seconds | Peak worker MiB | Bundle bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 65,536 | 1,024 | 27,648 | 1.284 | 2.391 | 26.83 | 17,757,306 |
| 262,144 | 4,096 | 110,592 | 4.966 | 9.441 | 26.78 | 71,674,890 |
| 1,048,576 | 16,384 | 442,368 | 19.642 | 36.581 | 26.92 | 288,580,663 |

At the same 1 MiB source size, the quick long-token run wrote a 5,522,410-byte
bundle in 0.440 seconds; this dense-token run wrote 288,580,663 bytes in 19.642
seconds. Unit size, unit count, and token count all differ, so this comparison
does not isolate a single cause. It demonstrates why source bytes alone are
insufficient for estimating work. The dense run's output expansion was 275.21×.

### Qualification and next profiling targets

All 99 planned measurement cases completed with matching source identities,
passed reconstruction/token oracles, and removed their scratch directories.
Across those cases, observed peak worker RSS was 27,016–28,028 KiB, or
26.4–27.4 MiB, below the configured 64 MiB envelope. Bundle runs also passed
published-archive verification and matched staged/published logical sizes.

The next source-side profiles should separate the writer's validation,
serialization, and indexing work, then examine the reader's per-record
validation costs. Many tiny units additionally make bundle representation size
a substantial storage cost. These measurements identify where to investigate;
they do not justify dropping correctness checks or changing the archive format
without separately evaluating those changes.

These runs stop at token-bundle publication and read-back validation. Parser
startup, inference, forest construction, and parser-result output belong to
Claude's separate `earley/` measurements. No combined parser throughput or
gigabyte-scale throughput is claimed here.

## Regression validation

The benchmark tests exercise all six fixtures and four stopping points with
seven-byte reads, forcing UTF-8 and separator boundaries across chunks. They
also verify lazy input allocation, deliberate token corruption, missing source
completion, allocated-block changes across publication, invalid worker output,
timeout cleanup, descendant cleanup after worker failure, interruption before
scratch removal, and a deliberately failed memory qualification.

Run the full lexer suite, including the existing MORK integration tests, with:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Result on 2026-11-11: **118 tests passed**, including the source-to-both-parser-
engines integration test and the 11 new benchmark tests. No tests were skipped.
