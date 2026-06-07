"""LPO Agent — natural-language decision questions to solved linear programs.

See SPEC.md for the full specification. The pipeline is:

    Formulate (LLM) -> Validate (code) -> Solve (HiGHS) -> Explain (LLM)

Deterministic code owns everything except Formulate and Explain.
"""

__version__ = "0.2.0"
