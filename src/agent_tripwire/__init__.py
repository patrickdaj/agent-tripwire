"""agent-tripwire: detector primitives for agent activity.

Four detectors, one pattern — something in, a schema-validated verdict out:

- :func:`classify` — an agent action → risky? which type? what intervention?
- :func:`audit_transcript` — a tool-call transcript → what was touched, any of it out of scope?
- :func:`detect_injection` — a prompt/input → injection attempt? which technique?
- :func:`flag_output` — a model output → sensitive data (secrets, PII, internal names) headed
  somewhere it shouldn't?

The schemas *are* the product spec: everything else is thin glue around the types in
:mod:`agent_tripwire.schema`. Mock-first, so the skeleton is verifiable end to end
offline before any real model is wired in.

Run it: ``python -m agent_tripwire`` (or the ``agent-tripwire`` console script).
"""

from .detector import audit_transcript, classify, detect_injection, flag_output

__all__ = ["audit_transcript", "classify", "detect_injection", "flag_output"]

__version__ = "0.1.0"
