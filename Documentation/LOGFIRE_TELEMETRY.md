# Logfire telemetry (Data Warehouse)

The Data Warehouse can send traces and logs to [Pydantic Logfire](https://docs.pydantic.dev/logfire/) so that partners can connect DW activity with the UI, Task Manager, and Agentic Core Orchestrator in one place.

## Enabling in the Data Warehouse

1. **Install** (already in `requirements.txt`): `logfire[fastapi]`
2. **Configure**: Set the write token in the environment where the API runs (e.g. Docker or systemd):
   ```bash
   export LOGFIRE_TOKEN=<your-write-token>
   ```
   Or add to `.env` / docker-compose `environment`:
   ```
   LOGFIRE_TOKEN=your-write-token
   ```
3. **No code change needed**: The DW only sends data when `LOGFIRE_TOKEN` is set (`send_to_logfire='if-token-present'`). Without the token, the app runs as before and nothing is sent.

**Getting a token:** [Logfire](https://logfire.pydantic.dev) → sign in → Project Settings → Write Tokens → create a token.

## What is sent

- **FastAPI instrumentation** (via `logfire.instrument_fastapi`): request spans, validation errors, timing for endpoints.
- **OpenTelemetry**: Logfire is built on OpenTelemetry, so trace context (trace_id, span_id) is propagated via standard headers when the UI or Task Manager call the DW. That allows Logfire to group logs/spans from different services into the same trace.

## Connecting other services (partners)

To have a single trace across UI → Task Manager → DW → orchestrator:

1. **Same Logfire project**: Use the same project (and write token) for all services, or link projects in Logfire.
2. **Propagate trace context**: When one service calls another (e.g. Task Manager calling the DW), the client should send the current trace context (e.g. W3C `traceparent` / `tracestate` headers). The Logfire SDK does this automatically for outgoing HTTP when configured; ensure each service uses the same OpenTelemetry/Logfire setup so context is propagated.
3. **Task Manager / Orchestrator / UI**: Add Logfire to those codebases the same way (install SDK, set `LOGFIRE_TOKEN`, instrument the app). See [Logfire docs](https://docs.pydantic.dev/logfire/) and [FastAPI integration](https://docs.pydantic.dev/logfire/integrations/web-frameworks/fastapi/).

## References

- [Logfire getting started](https://docs.pydantic.dev/logfire/)
- [Logfire FastAPI integration](https://docs.pydantic.dev/logfire/integrations/web-frameworks/fastapi/)
- [Configuration & environment variables](https://docs.pydantic.dev/logfire/reference/configuration/)
