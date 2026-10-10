# 🛡️ ECC (Everything Claude Code) & `.agents` Complete User Guide

> **Your Personal Agent Harness & AI Engineering Operating System**  
> Integrated natively with **Google Antigravity IDE** and **Manas Ciel Desktop Assistant**.

---

## 📑 Table of Contents
1. [Overview & What Was Installed](#-1-overview--what-was-installed)
2. [How to Use in Antigravity IDE](#-2-how-to-use-in-antigravity-ide)
   - [Slash Workflows (`/command`)](#a-slash-workflows)
   - [Specialized Subagents (`@agent`)](#b-specialized-subagents)
   - [Activating Domain Skills](#c-activating-domain-skills)
   - [Automatic Workspace Rules](#d-automatic-workspace-rules)
3. [How to Use via Ciel (Voice & Chat)](#-3-how-to-use-via-ciel-voice--chat)
4. [Top 15 Most Useful Agents](#-4-top-15-most-useful-agents)
5. [Top 20 Most Powerful Skills](#-5-top-20-most-powerful-skills)
6. [Practical Real-World Examples](#-6-practical-real-world-examples)
7. [Directory Structure Reference](#-7-directory-structure-reference)

---

## 🌟 1. Overview & What Was Installed

The ECC system turns your AI from a simple code completion tool into a complete, disciplined software engineering organization.

| Component | Count | Location | Purpose |
| :--- | :---: | :--- | :--- |
| **Specialized Agents** | **68** | `.agents/agents/` | Expert personas for code review, security, performance, architecture, and bug fixing. |
| **Domain Skills** | **286** | `.agents/skills/` | Curated best practices, rules, and code patterns across all major tech stacks. |
| **Workspace Rules** | **122** | `.agents/rules/` | Coding conventions automatically applied whenever you write code. |
| **Slash Workflows** | **94** | `.agents/workflows/` | Multi-step standard operating procedures executed via quick slash commands. |

**Locations on your computer:**
- **Scratch Workspace**: `C:\Users\Lenovo\.gemini\antigravity-ide\scratch\.agents\`
- **Ciel Assistant Root**: `C:\Users\Lenovo\Ciel\.agents\`

---

## 🖥️ 2. How to Use in Antigravity IDE

Whenever you open a project or conversation in Antigravity, the IDE automatically detects the `.agents/` folder in your workspace root.

### A. Slash Workflows
Type these slash commands at the beginning of your prompt:

| Command | What It Does | When to Use |
| :--- | :--- | :--- |
| `/plan` | Creates a comprehensive architectural implementation plan before touching code. | Before building any new feature or project. |
| `/code-review` | Performs a strict senior-level review of staged or recent code modifications. | After finishing code edits before committing. |
| `/security-scan` | Audits files for secrets, OWASP top 10 vulnerabilities, and injection attacks. | When dealing with auth, user input, or network endpoints. |
| `/build-fix` | Systematically diagnoses compiler errors, missing modules, and broken imports. | When you hit dependencies or build failures. |
| `/test-coverage` | Analyzes test gaps and generates edge-case unit tests. | When writing tests for Python, JS/TS, or Go code. |
| `/refactor-clean` | Simplifies bloated files and cleans dead code without breaking functionality. | When a file gets too long or messy. |

---

### B. Specialized Subagents
Invoke dedicated personas directly in your chat prompt using the `@` symbol:

```markdown
@code-reviewer review C:\Users\Lenovo\OneDrive\Documents\python\hand.py
@performance-optimizer how can we speed up OpenCV frame processing in air_draw.py?
@security-reviewer inspect my backend API for credential leaks and open endpoints
@silent-failure-hunter find any swallowed exceptions or unhandled errors in this script
@architect design a scalable state system for my desktop overlay application
```

Each subagent runs with specialized prompt defense baselines and focuses exclusively on its domain.

---

### C. Activating Domain Skills
You can explicitly tell Antigravity to adhere to any of the 286 engineered skills:

```markdown
"Use the react-performance skill to optimize this dashboard component."
"Apply the python-testing skill to write pytest tests with fixtures."
"Follow the fastapi-patterns skill to structure this REST API."
"Use the database-migrations skill to write a safe rollback plan."
```

---

### D. Automatic Workspace Rules
You don't need to manually configure coding standards. The rules inside `.agents/rules/` automatically guide the AI:
- **Python**: Enforces type hints, context managers, PEP 8, and proper error handling.
- **Frontend / React**: Enforces clean hooks, server/client boundaries, and memoization where needed.
- **Security**: Forbids hardcoding API keys, passwords, or tokens in any generated code.

---

## 🎙️ 3. How to Use via Ciel (Voice & Chat)

Your personal assistant **Ciel** is directly connected to the ECC harness via [`agent_tools.py`](file:///C:/Users/Lenovo/Ciel/app/agent_tools.py). You can speak to Ciel or type into her chat:

### 1. Instant Engineering Lookups (`ecc_consult`)
Ask Ciel for best practices, patterns, or architecture rules with zero latency:
- *"Ciel, consult ECC on React performance"*
- *"Ciel, consult ECC on Python async"*
- *"Ciel, consult ECC on Docker patterns"*
- *"Ciel, what does ECC say about FastAPI architecture?"*

### 2. Autonomous Code Reviews (`ecc_agent_run`)
Ask Ciel to run specialized ECC personas on your files:
- *"Ciel, ECC review `C:\Users\Lenovo\OneDrive\Documents\python\hand.py`"*
- *"Ciel, ECC security review `C:\Users\Lenovo\Ciel\app\app.py`"*
- *"Ciel, review file `air_draw.py`"*

---

## 🧙 4. Top 15 Most Useful Agents

| Agent Name | Specialty | Best Prompt |
| :--- | :--- | :--- |
| **`code-reviewer`** | Code quality, readability, maintainability, and bug detection. | `@code-reviewer review [file]` |
| **`security-reviewer`** | Vulnerability scanning, injection checks, and token safety. | `@security-reviewer audit [file/folder]` |
| **`performance-optimizer`** | Latency reduction, algorithmic complexity, memory profiling. | `@performance-optimizer profile [file]` |
| **`silent-failure-hunter`** | Finds empty `except:`, unhandled promises, and ignored errors. | `@silent-failure-hunter inspect [file]` |
| **`architect`** | High-level system design, separation of concerns, ADRs. | `@architect plan [project concept]` |
| **`tdd-guide`** | Enforces test-driven development (red -> green -> refactor). | `@tdd-guide write tests for [feature]` |
| **`build-error-resolver`** | Dissects compiler errors, circular imports, and broken configs. | `@build-error-resolver fix build failure` |
| **`python-reviewer`** | Pythonic standards, GIL/async concurrency, type checking. | `@python-reviewer check [file.py]` |
| **`react-reviewer`** | Hook dependencies, re-render waterfalls, component isolation. | `@react-reviewer check [component.tsx]` |
| **`fastapi-reviewer`** | Endpoint routing, dependency injection, and Pydantic validation. | `@fastapi-reviewer audit [api.py]` |
| **`database-reviewer`** | Indexing, N+1 query prevention, migration safety, transactions. | `@database-reviewer review query [sql/orm]` |
| **`refactor-cleaner`** | Eliminates duplication and streamlines control flow. | `@refactor-cleaner clean [file]` |
| **`doc-updater`** | Generates clear docstrings, API reference docs, and READMEs. | `@doc-updater document [file]` |
| **`e2e-runner`** | End-to-end integration and browser automation testing. | `@e2e-runner write tests for [flow]` |
| **`type-design-analyzer`** | Strict type system design in TypeScript and Python typing. | `@type-design-analyzer review types in [file]` |

---

## 📚 5. Top 20 Most Powerful Skills

| Skill Folder | Description |
| :--- | :--- |
| **`coding-standards`** | The baseline cross-project standard for naming, immutability, and structure. |
| **`react-performance`** | 70+ performance rules adapted from Vercel Labs (waterfalls, bundle size, re-renders). |
| **`python-testing`** | Pytest fixtures, mocking, parametrization, and async test standards. |
| **`fastapi-patterns`** | Production-ready FastAPI architecture with Pydantic v2. |
| **`database-migrations`** | Safe zero-downtime database migrations with rollback scripts. |
| **`deep-research`** | Rigorous multi-source technical analysis and citation. |
| **`docker-patterns`** | Multi-stage Dockerfiles, minimal base images, and caching tricks. |
| **`security-review`** | Comprehensive security assessment covering OWASP Top 10. |
| **`tdd-workflow`** | Test-first implementation lifecycle. |
| **`api-design`** | RESTful resource design, idempotency keys, and error responses. |
| **`error-handling`** | Typed errors, circuit breakers, retry backoffs, and user-facing messages. |
| **`git-workflow`** | Clean commit conventions, feature branches, and safe rebasing. |
| **`latency-critical-systems`**| Low-latency algorithmic tricks, buffer management, and CPU cache friendliness. |
| **`kubernetes-patterns`** | Pod disruption budgets, health probes, resource requests/limits. |
| **`e2e-testing`** | Playwright and end-to-end UI verification standards. |
| **`motion-ui`** | Micro-animations, spring physics, and fluid CSS transitions. |
| **`unified-memory`** | Cross-session context management and architectural memory. |
| **`redis-patterns`** | Caching strategies, distributed locks, and pub/sub patterns. |
| **`windows-desktop-e2e`** | Native Windows automation, UI automation, and desktop testing. |
| **`prompt-optimizer`** | Engineering precise prompts for LLM accuracy and cost control. |

---

## 🛠️ 6. Practical Real-World Examples

### Example 1: Optimizing Your Hand Tracking Code
**Prompt in Antigravity or speak to Ciel:**
```text
@performance-optimizer Please review C:\Users\Lenovo\OneDrive\Documents\python\hand.py.
Focus on:
1. Minimizing frame latency during cv2 capture
2. Reducing MediaPipe memory allocations per frame
3. Adding graceful webcam disconnection handling
```

---

### Example 2: Building a New Feature with TDD
**Prompt in Antigravity:**
```text
/plan I want to add a gesture-based volume control to my air drawing script.
First generate a plan, then let @tdd-guide write the unit tests for gesture detection before implementing the code.
```

---

### Example 3: Running a Fast Security & Bug Scan
**Prompt in Antigravity:**
```text
@silent-failure-hunter and @security-reviewer audit my Ciel backend files in C:\Users\Lenovo\Ciel\app.
Find any swallowed exceptions or unvalidated endpoints.
```

---

## 📁 7. Directory Structure Reference

```text
.agents/
├── agents/                       # 68 Agent personas (*.md)
│   ├── code-reviewer.md
│   ├── security-reviewer.md
│   ├── architect.md
│   └── ...
├── rules/                        # 122 Categorized rules (*.md)
│   ├── common-coding-style.md
│   ├── python-testing.md
│   ├── react-state.md
│   └── ...
├── skills/                       # 286 Domain skills (with SKILL.md)
│   ├── react-performance/SKILL.md
│   ├── fastapi-patterns/SKILL.md
│   ├── database-migrations/SKILL.md
│   └── ...
├── workflows/                    # 94 Slash command workflows (*.md)
│   ├── plan.md
│   ├── code-review.md
│   ├── security-scan.md
│   └── ...
└── ecc-install-state.json        # Harness metadata and installation state
```

---

*This guide was generated by Ciel. To view or consult skills at any time, ask Ciel or open any file in `.agents/`.*
