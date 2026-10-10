# Ciel Improvement Roadmap

**Project:** Ciel / Manas Ciel desktop assistant  
**Current stack:** Flask backend, PyWebView desktop shell, static HTML/CSS/JavaScript frontend, Ollama integration, voice features, desktop automation tools  
**Plan mode:** Direct local implementation; no Git repository or automated test suite was detected in the project root  
**Priority:** Reliability first, then response quality, usability, security, and extensibility

## Executive goal

Make Ciel feel like a dependable local assistant rather than a collection of loosely connected features:

1. It starts predictably and explains failures clearly.
2. The UI always reflects the actual backend state.
3. Ciel answers concisely, acts safely, and reports results consistently.
4. Tool use is permissioned, observable, cancellable, and testable.
5. New features can be added without expanding the large monolithic files indefinitely.

## Baseline findings

- `app/app.py` is a large Flask application with many routes and runtime responsibilities.
- `app/agent_tools.py` is a large tool collection and should be split by capability over time.
- The frontend is a static template plus `app/static/css/ciel.css`, `app/static/js/ciel.js`, and `app/static/js/thinking-orbs.js`.
- The desktop launcher is `app/launch_desktop.py`; native launcher source is `app/launcher.cs`.
- The old compiled `Ciel.exe` previously failed with an unhandled `Win32Exception` because it hard-coded `pythonw.exe` and a fixed user path.
- The launcher source was updated to resolve paths relatively, detect Python, and show a readable startup error. The executable still needs rebuilding to include that fix.
- JavaScript syntax, HTML balance, local assets, DOM IDs, API route names, and duplicate function declarations passed static checks.
- No project-specific Python test files or pytest configuration were found at the root.
- Live server verification must be repeated in the user’s actual running environment; the agent-side probe did not find a listener on `127.0.0.1:5000` during the audit.

## Dependency graph

```text
P0 Startup contract and diagnostics
 ├── P1 Automated backend/frontend smoke tests
 ├── P2 API response and error contract
 │    ├── P3 Response / tool execution quality
 │    └── P4 UI state and error presentation
 ├── P5 Security and permission hardening
 └── P6 Architecture split and maintainability
      └── P7 Packaging, release, and regression gate
```

**Parallelizable after P0:** P1, P3, and the first pass of P5 can proceed independently.  
**Must remain serial:** P0 → P2 → P4; P6 should not begin until the API contract is stable.

---

## Phase P0 — Make startup deterministic

### Context
A user should never see a silent exit or a raw .NET exception. The current native launcher fix exists in `app/launcher.cs`, but the shipped executable must be rebuilt and the Python environment contract must be explicit.

### Work

- Rebuild `Ciel.exe` from the corrected `app/launcher.cs`.
- Replace the `py -3` assumption in launch documentation with a detected absolute interpreter or a clear installation step.
- Add a startup diagnostic mode that records:
  - Python executable and version
  - dependency import failures
  - selected Flask port
  - Ollama availability
  - PyWebView availability
  - final startup exception and traceback
- Make the launcher check port availability before starting Flask.
- Make Flask startup failure return a visible error containing the occupied port or dependency name.
- Add `GET /api/health` fields for `server_version`, `python_version`, `port`, `ollama_online`, and `dependency_errors`.

### Verification

```powershell
where python
python --version
python -c "import flask, requests, webview, psutil; print('imports ok')"
python app\launch_desktop.py
Invoke-WebRequest http://127.0.0.1:5000/api/health
```

### Exit criteria

- Starting from the project directory and from a different working directory both work.
- Missing Python, missing dependency, occupied port, and missing script each produce a readable diagnosis.
- The packaged executable and `RUN_CIEL.bat` use the same startup behavior.

### Rollback
Keep the prior executable as `Ciel.previous.exe` until the rebuilt binary passes the smoke test.

---

## Phase P1 — Add a real automated smoke-test harness

### Context
The project currently has no discoverable root test suite, so frontend and backend regressions can reach the user unnoticed.

### Work

Create `tests/` coverage for the running contract:

- Backend route tests using Flask’s test client.
- Health/version/model endpoint tests.
- Chat validation tests for empty input, oversized input, malformed JSON, and provider failure.
- Permission endpoint tests for pending, approve, deny, and reset behavior.
- Memory and chat persistence tests.
- Static asset existence tests.
- A Node-based frontend static check for:
  - JavaScript syntax
  - duplicate IDs
  - missing literal DOM IDs
  - missing local assets
  - API route references not present in Flask
- A Windows smoke script that starts the server, polls `/api/health`, tests key endpoints, and always terminates the child process.

### Verification

```powershell
python -m pytest -q
node --check app\static\js\ciel.js
node --check app\static\js\thinking-orbs.js
```

### Exit criteria

- A clean checkout has one documented command that runs all non-destructive tests.
- The smoke script fails with a useful message when the server never binds.
- Target at least 80% coverage for newly extracted modules; do not inflate coverage by testing implementation details.

### Rollback
Tests are additive. Disable only the failing test group while fixing the underlying issue; do not delete tests to make a build green.

---

## Phase P2 — Standardize the API and error contract

### Context
The backend exposes many capabilities directly from one large file. A consistent envelope will make the UI and future clients more reliable.

### Work

Define a response shape:

```json
{
  "ok": true,
  "data": {},
  "error": null,
  "request_id": "...",
  "meta": {}
}
```

For failures:

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "OLLAMA_UNAVAILABLE",
    "message": "Ollama is not available.",
    "retryable": true
  },
  "request_id": "..."
}
```

- Add centralized request IDs and structured logging.
- Validate JSON body types and string lengths at every POST boundary.
- Normalize HTTP status codes: 400 for invalid input, 401/403 for permission failures, 404 for missing resources, 409 for conflicts, 429 for rate limits, and 500/503 for server/provider failures.
- Preserve backwards compatibility temporarily by keeping legacy fields while the frontend migrates.
- Document all routes in `CONFIG_GUIDE.md` or a new API document only if the existing documentation has no suitable location.

### Verification

- Route tests assert both status codes and response envelopes.
- Frontend displays `error.code` and a user-safe `error.message`.
- Logs contain request IDs but never raw credentials or sensitive prompt contents by default.

### Exit criteria

Every frontend-used endpoint has a predictable success and failure shape.

---

## Phase P3 — Improve Ciel’s response and tool-execution quality

### Context
Ciel needs to be warm and recognizable as the Tensura-inspired Wisdom Core without sacrificing clarity or making every response theatrical.

### Work

- Keep the improved system prompt, but move it into a versioned prompt module rather than embedding a large prompt in `app.py`.
- Define response modes:
  - **Answer:** direct explanation
  - **Plan:** ordered steps before multi-step work
  - **Action:** tool execution with permission status
  - **Report:** result, files changed, and verification
  - **Clarify:** one focused question when intent is ambiguous
- Add a response normalizer that rejects empty replies, accidental raw tool traces, and repeated boilerplate.
- Add a tool-result formatter that separates:
  - what Ciel attempted
  - what succeeded
  - what failed
  - what the user should do next
- Add cancellation and timeout handling to long-running model/tool requests.
- Keep “draw/generate image” requests action-oriented: generate the asset instead of returning a tutorial.

### Verification

Create golden tests for at least:

- simple question
- ambiguous request
- code explanation
- file modification
- denied permission
- tool timeout
- image generation request
- provider unavailable

### Exit criteria

Ciel’s response is concise for simple questions, structured for complex tasks, and never claims an action succeeded without a tool result.

---

## Phase P4 — Make the UI state truthful and easier to use

### Context
The current frontend has many views and controls. The next usability improvement should reduce uncertainty rather than add more decoration.

### Work

- Add a single connection state machine: `starting`, `ready`, `degraded`, `offline`, `busy`.
- Show the state consistently in the top bar, chat composer, model selector, and tool controls.
- Disable actions while a request is active unless cancellation is supported.
- Add visible retry buttons for provider/network failures.
- Show a compact execution timeline for tool calls instead of exposing raw logs by default.
- Add keyboard shortcuts with discoverable help.
- Add accessible labels, focus states, reduced-motion behavior, and keyboard navigation for every view.
- Keep conversation as the primary view; move diagnostics, memory, IDE, image generation, and tasks into clear secondary destinations.
- Add a first-run welcome flow that explains local privacy, model selection, agent permissions, and voice controls.

### Verification

- Manual keyboard-only pass.
- Screen-reader label review.
- Responsive checks at 1280×800, 1024×768, and narrow companion dimensions.
- Browser smoke tests for send, stop, retry, model change, history, memory, and view switching.

### Exit criteria

A new user can send a message, understand whether Ciel is working, see why a request failed, and retry without opening developer tools.

---

## Phase P5 — Harden permissions and sensitive operations

### Context
Ciel can interact with files, processes, the clipboard, keyboard, mouse, voice, and image/model services. Permission behavior must be explicit and auditable.

### Work

- Define capability scopes: filesystem read, filesystem write, process launch, browser/network, input automation, microphone, camera/screen capture, and model management.
- Use least-privilege defaults; agent mode should not silently broaden scopes.
- Add per-request confirmation for destructive or external actions.
- Sanitize paths and reject traversal outside approved workspaces.
- Add size and time limits for uploads, generated files, command execution, and model requests.
- Redact secrets and sensitive data from logs.
- Add an audit record containing request ID, capability, decision, actor, and timestamp.
- Add rate limits and concurrency limits to expensive endpoints.

### Verification

- Negative tests for path traversal, shell metacharacters, oversized payloads, unauthorized scopes, and repeated requests.
- Verify denied actions do not execute side effects.
- Verify audit logs omit raw secrets.

### Exit criteria

Every high-impact tool action has a clearly observable permission decision and cannot bypass validation through alternate routes.

---

## Phase P6 — Split the monolith safely

### Context
`app.py` and `agent_tools.py` are large enough that changes are increasingly risky. Refactoring should follow the stable API contract, not precede it.

### Work

Extract in small, reversible units:

```text
app/
  routes/
    health.py
    chat.py
    voice.py
    memory.py
    tasks.py
    ide.py
    image.py
    permissions.py
  services/
    chat_service.py
    model_service.py
    permission_service.py
    task_service.py
  tools/
    filesystem.py
    computer.py
    browser.py
    media.py
  schemas/
    requests.py
    responses.py
  prompts/
    ciel_system.py
```

- Keep route handlers thin.
- Keep business logic testable without Flask or PyWebView.
- Use immutable request/response objects where practical.
- Remove duplicated model, permission, and error-handling logic only after tests cover the behavior.

### Verification

- All existing smoke tests pass after each extraction.
- No route changes without an API compatibility test.
- Import graph check prevents tool modules from importing the Flask app circularly.

### Exit criteria

A new capability can be added to one focused service/module without editing a giant shared file in multiple unrelated locations.

---

## Phase P7 — Packaging and release gate

### Context
The source can be healthy while the shipped executable is stale or broken. Packaging must become a tested release artifact.

### Work

- Rebuild `Ciel.exe` from the corrected launcher.
- Bundle or clearly require Python and dependencies; choose one supported distribution model.
- Add a packaging manifest listing Python version, required packages, static assets, model directories, and configuration files.
- Run a clean-machine smoke test or isolated environment test.
- Add a version endpoint and show the version in the UI and logs.
- Add a release checklist:
  - launcher starts
  - port binds
  - `/api/health` is healthy
  - main page loads
  - chat round trip succeeds
  - permission denial works
  - shutdown is clean
  - no secrets are packaged

### Exit criteria

A user can run the documented launcher from a clean supported Windows environment and receive either a working Ciel window or a specific actionable setup message.

---

## Recommended first sprint

Do these in order before adding new features:

1. **Rebuild the native launcher** from `app/launcher.cs`.
2. **Install/validate the supported Python runtime** and dependencies.
3. **Add `/api/health` startup diagnostics** and a Windows smoke script.
4. **Create backend route tests** for health, chat, permission, memory, and models.
5. **Standardize error envelopes** for the endpoints already used by the UI.
6. **Add truthful frontend connection state** and retry behavior.
7. **Add golden response tests** for Ciel’s most important response modes.

## Definition of done for the roadmap

- Startup failures are visible, specific, and recoverable.
- Automated smoke tests run on every future change.
- The API contract is consistent.
- Ciel’s responses are concise, honest, and action-oriented.
- Permissions and sensitive tools are auditable.
- The UI makes system state and next actions obvious.
- The packaged executable is rebuilt and tested, not assumed to match source.
