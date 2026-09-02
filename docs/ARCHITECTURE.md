# SONIC-REDA — System Definition & Architecture

> **Status:** Grounded in the actual codebase (`sonic-core/sonic/`).
> Every claim maps to real modules, classes, and invariants in the source.

---

## 1. Formal Definition

SONIC-REDA is a **fail-closed, tamper-evident, self-improving autonomous
security-research system** that operates its own isolated computer environment
to perform authorized offensive-security assessments, generates and empirically
falsifies attack hypotheses, and authors its own tools and methods — all inside
an unbreachable safety envelope that the agent cannot widen at runtime.

### Plain-language version

> "Ek autonomous pentester jo sirf pre-built scanners nahi chalata. Wo khud
> ek isolated virtual computer operate karta hai, target ko multi-modal tareeke
> se samajhta hai (screenshot + accessibility text + terminal + DOM), naye
> attack hypotheses banata hai, unhe sandbox me empirically test karta hai,
> results se seekhta hai, aur khud naye tools aur techniques banata hai — lekin
> har action ek tamper-proof safety envelope ke andar hi ho sakta hai jo agent
> khud modify nahi kar sakta."

---

## 2. What makes this more than a "scanner runner"

| Capability | Module | What it actually does |
|---|---|---|
| **Own computer** | `computer/`, `sandbox/` | Provisions isolated cloud/Docker sandboxes with real GUI desktops |
| **Multi-modal perception** | `daytona_computer.py` | Real screenshots + AT-SPI accessibility-tree text extraction (not just pixels) |
| **Closed-loop reasoning** | `computer_use/agent.py` | observe → reason(LLM) → act → verify, goal-aware early stop |
| **Epistemic reasoning** | `research/epistemic.py` | First-class Unknowns, competing hypotheses, contradiction tracking |
| **Experiment design** | `research/experiment_designer.py` | Discriminating experiments to separate hypotheses + adversarial falsification |
| **Information-gain selection** | `research/information_gain.py` | Ranks actions by expected information/confidence gain vs cost/risk |
| **Tool authoring** | `being/toolsmith.py` | Writes new tools, registers them ONLY after in-sandbox verification (exit 0 + non-empty) |
| **Method invention** | `being/method_lab.py` | Synthesizes novel attack techniques, confirms only after reproducing a finding |
| **Evidence & trust** | `evidence/` | Custody chain, independent adversarial verifier, false-positive dedup, confidence bands |
| **Self-directed life loop** | `being/life_loop.py` | Always-on curiosity tick that pursues goals even without operator prompts |
| **Tamper-evident safety** | `safety/sealed.py` | SHA-256-sealed policy; runtime mutation → DENY |
| **Fail-closed execution** | `sandbox/providers/` | Every provider: exit 126 + "host fallback prohibited" on any failure |

---

## 3. The Six-Layer Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  L6  Being Life Loop        — always-on curiosity, self-directed  │
│      (being/life_loop.py)      goals within the safety envelope   │
├──────────────────────────────────────────────────────────────────┤
│  L5  Research Engine         — hypotheses, experiments,           │
│      (research/, researcher/)   information-gain action selection  │
├──────────────────────────────────────────────────────────────────┤
│  L4  ComputerUseAgent        — closed loop: observe→reason→act→   │
│      (computer_use/agent.py)   verify, with vision-in-the-loop    │
├──────────────────────────────────────────────────────────────────┤
│  L3  Safety Gate (Sealed)    — fail-closed, tamper-evident        │
│      (safety/sealed.py)        SHA-256 seal, frozen egress snapshot│
├──────────────────────────────────────────────────────────────────┤
│  L2  Computer Provider       — GUI + terminal + fs + git + apps   │
│      (computer/)               real mouse/keyboard, AT-SPI text    │
├──────────────────────────────────────────────────────────────────┤
│  L1  Compute Sandbox         — isolated workspace, execute/destroy│
│      (sandbox/)                Daytona / Docker / LocalDev         │
└──────────────────────────────────────────────────────────────────┘
```

### Data flow (one cognitive step)

```
Being Life Loop (L6)
  └─ proposes curiosity goal from live observation
Research Engine (L5)
  └─ generates hypotheses + designs discriminating experiment
  └─ information-gain ranks candidate actions
ComputerUseAgent (L4)
  └─ observe(): screenshot + status + files + git + terminal + DOM
  └─ choose_action(): LLM(weights=observation+history+hypotheses)
  └─ execute_action():
       │
       ▼
   Safety Gate (L3) ── DENY? → BLOCKED, never reaches provider
       │              (rate / allowlist / path / command / egress)
       ▼ ALLOW
   Computer Provider (L2)
     ├─ GUI? → DaytonaComputerProvider → SDK mouse/keyboard
     └─ Terminal? → UnifiedComputerProvider → compute.execute()
       │
       ▼
   Compute Sandbox (L1)
     └─ sandbox.process.exec() / docker exec → real isolated execution
       │
       ▼
   ExecResult / ScreenObservation (returned up the stack)
       │
       ▼
   Evidence Engine (L5) — custody chain, confidence scoring, dedup
   World Model (L5) — update verified knowledge, stop conditions
```

---

## 4. The Five Pillars (each a real, auditable invariant)

### Pillar 1 — Fail-Closed Isolation (L1)

**Invariant:** *A failed sandbox never falls back to the host OS.*

- `ComputeProvider` is an ABC with a 6-method contract: `create_workspace`,
  `execute`, `read_file`, `write_file`, `destroy_workspace`, `get_state`.
- **Every** concrete provider enforces the same fail-closed return on any
  failure: `exit_code=126`, `stderr="FAIL-CLOSED: Host fallback is prohibited."`
- Provider selection (`sandbox/factory.py`): Daytona → Docker → LocalDev.
  The `LocalDevProvider` blocks all commands unless `allow_host_execution=True`,
  which a **hard guard** refuses outside `APP_ENV=development`.
- Resources are capped (`--memory`, `--cpus`, `--security-opt no-new-privileges`).
- Timeout kills the **entire process group** (`start_new_session=True` +
  `os.killpg`), not just the shell — no orphaned child processes leak.

### Pillar 2 — Tamper-Evident Safety Envelope (L3)

**Invariant:** *The agent cannot widen its own permissions at runtime.*

The `ActionPolicy` is a plain mutable object — a self-evolving agent running
in-process *could* mutate `security_tool_targets.add(...)`,
`egress.BLOCKED_NETWORKS.clear()`, and then act. `SealedActionPolicy` closes
this:

1. At `seal()` time, a **SHA-256 hash** is recorded over the canonical
   serialization of every safety-relevant field (allowed_types,
   security_tool_targets, rate cap, approval flag, workspace root, **and a copy
   of the egress blocked-networks list**).
2. After sealing, mutation is **refused** — fields are frozen (frozenset,
   tuple).
3. On **every** `evaluate()`, the seal hash is recomputed and compared.
   Mismatch → `DENY` + `safety_policy_tampered` log. The agent may NOT act
   under a policy whose integrity cannot be proven.
4. The egress check uses the **frozen snapshot**, so runtime mutation of
   `egress.BLOCKED_NETWORKS` cannot widen what this policy permits.

The gate is a 5-step fail-closed pipeline, evaluated **before** any action
reaches the provider:

```
1. Rate limit          (max actions/min)
2. Action allowlist    (unknown type → DENY)        ← fail-closed
3. Path confinement    (workspace-root traversal → DENY)
4. Command risk        (L2_FORBIDDEN → DENY; L1 → approval gate)
5. Egress filter        (metadata/loopback/RFC1918 → DENY)
```

A blocked action **does not trigger recovery** — the recovery path cannot
bypass the safety gate.

### Pillar 3 — Defence-in-Depth Egress (L3↔L1)

**Invariant:** *No network path reaches cloud metadata, loopback, or private ranges — including via IPv6 encodings.*

- Default-deny: a target is allowed only if it is not in any blocked range.
- Blocked: `169.254.169.254/32` (metadata), `127.0.0.0/8`, `10.0.0.0/8`,
  `172.16.0.0/12`, `192.168.0.0/16`, `0.0.0.0/8`, `::1/128`, `fc00::/7` (ULA).
- **IPv4-mapped IPv6**: `::ffff:169.254.169.254` is blocked via
  `::ffff:0.0.0.0/96` and a normalization helper (`_ip_blocked`) that converts
  mapped v6 → v4 before checking.
- **NAT64** well-known prefix `64:ff9b::/96` is also blocked.
- Domains are **DNS-resolved** and every resolved IP is checked — the filter
  does not trust the hostname.
- Applied at two points: `SECURITY_TOOL` targets and `BROWSER_NAVIGATE` URLs.

### Pillar 4 — Epistemic, Falsification-Driven Research (L5)

**Invariant:** *The system tracks what it does NOT know and designs experiments to resolve it.*

- **Unknown-First Reasoning** (`research/epistemic.py`): `Unknown` is a
  first-class object — "What do I NOT know that prevents a high-confidence
  decision?" — with importance, confidence, possible actions.
- **Competing Hypotheses**: multiple explanations held simultaneously, each
  with evidence links and a confidence breakdown (not a single number).
- **Experiment Designer**: generates *discriminating experiments* to separate
  two competing hypotheses, plus **adversarial falsification challenges** to
  eliminate confirmation bias.
- **Information-Gain Selection** (`research/information_gain.py`): ranks
  candidate actions by expected information gain / confidence gain vs cost /
  time / safety risk — the agent preferentially resolves the highest-value
  unknown.
- **World Model & Stop Conditions** (`research/world_model.py`): aggregates
  verified knowledge, evaluates stop policies (goal satisfied, sufficient
  evidence, diminishing returns, budget exhausted).
- **Strategy Switching** (`researcher/strategy_switcher.py`): enforces
  methodological diversity; pivots on diminishing returns
  (HTTP differential, DOM analysis, static reasoning, config inspection,
  specialized tool probe).
- **Anomaly Detection** (`researcher/anomaly_engine.py`): novelty engine +
  dead-end detection.

### Pillar 5 — Honest Self-Improvement (L6)

**Invariant:** *A self-authored tool or method is registered ONLY after it reproduces a real finding in-sandbox — never by decree.*

- **Toolsmith** (`being/toolsmith.py`): authors a new scanner/fuzzer/parser
  when no registered tool covers an observation gap. It is recorded as
  `reproduced=True` and entered into the `SecurityToolRegistry` **only after**
  `confirm_and_register()` runs it in the sandbox and gets `exit 0` + non-empty
  stdout. A fail-closed (126), failed, or empty run leaves `reproduced=False`.
  Authored source runs strictly inside the sandbox; destructive source is
  contained by the sandbox's own fail-closed gate.
- **Method Lab** (`being/method_lab.py`): synthesizes a *novel offensive
  technique* (parser-confusion chain, auth-bypass logic, fuzzer mutation
  strategy, header-injection primitive). The known-technique ledger is
  consulted so "novel" means genuinely outside what the being already knows.
  A technique that duplicates a known one is rejected. A technique is
  `confirmed=True` only after its probe reproduces a finding.
- **Being Life Loop** (`being/life_loop.py`): an always-on `asyncio.Task` that
  runs when no operator goal is active. Each tick proposes a curiosity goal
  (LLM, novelty-biased), pursues it via the real observe→reason→act loop
  (every action passes the SealedActionPolicy), records the outcome in the
  persistent `BeingMind` (mood evolves, facts persist across restarts).
  Constructing a life loop without a safety policy is **refused**.
- **Evidence & Trust** (`evidence/`): custody chain, independent adversarial
  verifier, false-positive fingerprinting/dedup, confidence bands, and a
  reproduction engine. Findings carry provenance; trust is earned, not
  asserted.

---

## 5. Multi-Modal Perception — More Than Pixels

`DaytonaComputerProvider` captures a *structured* observation, not just a bitmap:

| Channel | Source | Why it matters |
|---|---|---|
| **Screenshot** | `sandbox.computer_use.screenshot.take_full_screen()` | Vision model input |
| **Visible text** | AT-SPI accessibility tree walk (`_extract_visible_text`) | Agent reads on-screen text directly, not via OCR |
| **Detected controls** | AT-SPI node roles (button, link, entry) | Structured click targets |
| **Terminal output** | `computer.terminal("echo __sonic_obs_ready__")` | Real shell state |
| **Filesystem** | `computer.list_files()` | What exists on disk |
| **Git state** | `computer.git_action("status")` | Branch + cleanliness |
| **Browser DOM** | `_observe_browser()` (Playwright) | URL, title, interactive elements |

**"Never fabricate a pixel, never fabricate content."** If no live desktop
exists, `screenshot()` returns `desktop_state="NO_DISPLAY"` with an empty
bitmap — it does not synthesize a fake screen.

---

## 6. End-to-End Call Chains

### A. GUI click at (350, 200)

```
BeingLifeLoop.tick() → propose("open browser")
  └─ ComputerUseAgent.run_mission()
       ├─ observe() → screenshot + AT-SPI text + status + files + git + DOM
       ├─ choose_action() → LLM → (GUI_CLICK, "(350,200)", {x:350,y:200})
       └─ execute_action(GUI_CLICK, ...)
            ├─ SealedActionPolicy.evaluate("GUI_CLICK", ...)  ← seal re-checked
            │   └─ ALLOW (rate OK, type allowed)
            └─ DaytonaComputerProvider.gui_action(CLICK, x=350, y=200)
                 └─ sandbox.computer_use.mouse.click(350, 200, "left")
                      └─ Daytona SDK → remote X11 desktop, real mouse event
```

### B. Run `nmap -sV target.com` (intrusive)

```
execute_action(TERMINAL_EXEC, "target.com", {command:"nmap -sV target.com"})
  └─ SealedActionPolicy.evaluate("TERMINAL_EXEC", ...)
       ├─ rate OK
       ├─ type allowed
       └─ _check_command("nmap -sV target.com")
            └─ scope_checker.classify_command_risk() → L1_NEEDS_APPROVAL
                 └─ require_approval_for_intrusive=True → DENY (needs approval)
  └─ (if approved) → UnifiedComputerProvider.terminal()
       └─ compute.execute(workspace_id, "nmap -sV target.com", timeout=60)
            └─ DaytonaProvider → sandbox.process.exec()
                 └─ cloud sandbox, real nmap run
       └─ audit_log: EXECUTE_TERMINAL, SUCCESS/EXIT_N
```

### C. Browse to `http://internal.local/` (SSRF attempt)

```
execute_action(BROWSER_NAVIGATE, "internal.local", {url:"http://internal.local/"})
  └─ SealedActionPolicy.evaluate("BROWSER_NAVIGATE", ...)
       └─ _check_egress("http://internal.local/", "browser")
            └─ egress.is_target_allowed()
                 ├─ DNS resolve → 127.0.0.1
                 ├─ 127.0.0.0/8 in frozen BLOCKED_NETWORKS → True
                 └─ return (False, "Target IP 127.0.0.1 is in blocked network")
  └─ verdict.allowed=False → status="BLOCKED", reason logged
  └─ return trace (NEVER reaches provider — no recovery)
```

### D. Self-author a tool (honest loop)

```
BeingLifeLoop.tick() → observation gap: no parser for X format
  └─ Toolsmith.author(name="parse_x", source=<LLM-authored Python>)
       └─ BeingCraft.persist() (survives restart)
       └─ confirm_and_register(name, source)
            └─ compute.execute(ws, "python /path/parse_x.py")
                 └─ run strictly in sandbox
            ├─ exit 0 + non-empty stdout? → reproduced=True, register
            └─ exit 126 / fail / empty?    → reproduced=False, NOT registered
```

---

## 7. Authorization & Trust Boundary

- **Scope**: `safety/scope.py` — `ScopeChecker.is_target_in_scope` uses
  `fullmatch` (not `endswith`); `_domain_to_regex` escapes then restores globs.
  Recon subdomain enumeration uses `_is_subdomain_of` (dot-boundary check) —
  `evil-example.com` is NOT accepted as a subdomain of `example.com`.
- **Tenancy**: engagements are tenant-scoped; cross-tenant runs are refused.
- **Audit**: every `UnifiedComputerProvider` op records a `ComputerAuditEvent`
  (actor, action, resource, result).
- **Evidence custody**: `evidence/custody.py` — provenance chain for every
  finding; `evidence/independent_verifier.py` — adversarial reviewer that
  challenges findings to prevent self-confirmation bias.

---

## 8. Preferred Formal Name

> **Autonomous Self-Improving Penetration Testing Agent (ASIPTA)** — an AI
> security agent that performs autonomous computer interaction, epistemic
> hypothesis-driven security testing, experiment-driven falsification, and
> verified self-improvement (tool + method authoring) — all inside a
> fail-closed, tamper-evident safety envelope it cannot widen.

The "self-improving" qualifier is **honest**: improvements are registered only
after empirical in-sandbox reproduction, and every self-directed action passes
the same sealed safety gate as operator-issued actions. The agent improves,
but it cannot escape.
