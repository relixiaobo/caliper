"""Report layer — placeholder for M1.4 / M1.5.

Lands in roadmap milestones M1.4 (bucket aggregation) and M1.5 (A/B
compare with noise-floor analysis). Phase 3 adds multi-dim reports for
the chatbot scenario.

Planned modules:
    bucket.py    — aggregate Inspect AI .eval logs by metadata.bucket
    ab.py        — diff two .eval files; refuse to label improvements
                   that fall within 2σ of the noise floor
    multi_dim.py — Phase 3: per-dimension breakdown for multi-dim scorers
"""
