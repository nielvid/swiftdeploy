# SwiftDeploy Audit Report

Generated from `history.jsonl` — 4 snapshots

## Timeline

| Timestamp | Mode | Req/s | P99 (ms) | Error Rate | Chaos | Infra | Canary |
|---|---|---|---|---|---|---|---|
| 2026-05-06T20:00:00Z | stable | 5.2 | 12 | 0.00% | none | PASS | PASS |
| 2026-05-06T20:05:00Z | canary ⬆ | 8.1 | 45 | 0.00% | none | PASS | PASS |
| 2026-05-06T20:10:00Z | canary | 7.3 | 620 | 6.00% | error | PASS | FAIL |
| 2026-05-06T20:15:00Z | canary | 6.0 | 30 | 0.00% | none | PASS | PASS |

## Policy Violations

| Timestamp | Domain | Mode | Detail |
|---|---|---|---|
| 2026-05-06T20:10:00Z | canary | canary | error_rate=6.00% p99=620ms |

## Mode Changes

| Timestamp | From | To |
|---|---|---|
| 2026-05-06T20:05:00Z | stable | canary |

## Chaos Events

| Timestamp | Mode | Chaos Type | Error Rate | P99 (ms) |
|---|---|---|---|---|
| 2026-05-06T20:10:00Z | canary | error | 6.00% | 620 |
