# Engineering reports and investigation history

These reports are optional supporting material. They are useful for understanding why major changes were made, what was tested, and which limitations remain; they are not prerequisites for installing or using Shadow Reader.

For current performance figures, use the [performance benchmark PDF](../../benchmarks/PERFORMANCE_BENCHMARK.pdf), the [benchmark overview](../../benchmarks/README.md), and the [methods and limitations](../../benchmarks/METHODS_AND_LIMITATIONS.md). The files in `benchmarks/` contain the raw CSV observations, environment metadata, charts, and reproducible local harness.

## Reports

- [Overall review and regression history](review-and-test-report.md) — follow-up hardening, test coverage, and unresolved limits.
- [Touchpad scrolling investigation and fix](touchpad-scroll-fix-report.md) — original scroll anchoring/position-correction issue and regression checks.
- [Virtualization performance investigation](virtualization-performance-report.md) — rationale for virtualization, before/after measurements, trade-offs, and limitations.

Paths such as `tests/...` and `benchmarks/...` within these reports refer to locations relative to the project root unless stated otherwise.
