# Logging vs Tracing — The Core Idea

**Companion to:** Lab 9 (`marimo/notebooks/lab9-logging-vs-tracing.py`) | **Full reference:** [logging-vs-tracing.md](logging-vs-tracing.md)

---

- **Logs record what happened.** Each line is a single event in one service, such as
  `INFO Loaded table ap_india.products`, with a level, a timestamp and a message.
  They're good for audit trails, errors and security alerts.

- **Traces record how a request flowed.** A trace is a tree of timed spans across services,
  such as Trino → Polaris → S3. They're good for "why is this slow?" and "which step failed?".
  Traces are usually sampled; logs usually aren't.

- **Correlation ties the two together.** Polaris writes the same `trace_id` into its log lines
  and its Jaeger spans. You find a slow span in Jaeger, look up that ID in the logs, and get the
  full story. Part 3 of the Lab 9 notebook does this as a SQL join on `trace_id`.
