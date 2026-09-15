# SONIC — Core Rules (Aisa Karna Mana Hai)

These rules are **absolute and non-negotiable**. Every prompt, template,
control-flow path, test, and agent behavior MUST obey them without exception.

---

## 1. Zero Hardcoded Application Names

Control flow, perception parsing, window tiling, intent routing, and prompt
templates MUST NEVER hardcode or favor any specific application or binary name.

**Mana hai:**
- Listing or probing specific binaries by name in logic (`which chrome`,
  `which firefox`, `which burp`, etc.)
- String-matching window titles against a fixed set of known applications
- Tiling or focusing windows by checking against `("chrome", "terminal", …)` tuples
- Writing prompt examples that name a particular browser, editor, proxy, or scanner

**Karna hai:**
- Discover installed applications dynamically via `$PATH`, `which`, POSIX
  alternatives (`x-www-browser`, `sensible-browser`, `xdg-open`), `.desktop`
  entries, `wmctrl -l`, and active OS window titles
- Tile/focus whatever windows the desktop currently has open
- Use generic terms in prompts: "the browser", "a terminal", "the editor"

---

## 2. Zero Scripted Puppet Heuristics

SONIC reasons freely from live observations. Rigid keyword-matching decision
trees, canned multi-step checklists, hardcoded refusal fallbacks, and regex
string-manipulation of model intent are strictly forbidden.

**Mana hai:**
- `if "scan" in goal: do X; elif "http" in goal: do Y; else: do Z`
- Canned recovery commands that always run `curl -sI` or any other fixed probe
  on refusal
- Decomposing goals with a keyword-matching tree instead of asking the LLM
- Hardcoded `("step1: open browser", "step2: navigate to…")` action sequences

**Karna hai:**
- Ask the LLM to decompose, reason, and choose the next action each step
- On refusal, record it honestly and trigger a replan — never fabricate a
  workaround command
- Derive every sub-goal and milestone from the agent's actual observations

---

## 3. Zero External / Mock Domains and Endpoints

Production logic, prompts, and tests MUST NOT embed hardcoded external domains,
fake proxy URLs, or mock service endpoints.

**Mana hai:**
- `https://example.com`, `https://google.com`, `https://httpbin.org`,
  `https://target.com`, `http://proxy/cert`
- Fake commit hashes (`7b8e1f0a2c`), synthetic evidence, or fabricated findings
- Using canned scan output or hardcoded vulnerability names as "results"

**Karna hai:**
- Use `<target_url>`, `<target_host>`, `<target_endpoint>` placeholders in
  prompts
- Use RFC 5737 documentation-network addresses (`198.51.100.0/24`) in tests
- All real URLs must be operator-supplied or dynamically discovered in-scope
  targets
- All findings, deliverables, and evidence must come from real execution traces

---

## 4. Zero Static Coordinates and Landmarks

All GUI interactions must derive from real-time visual perception and dynamic
window/accessibility data.

**Mana hai:**
- Static coordinate lookup tables (`CHROME_URL_BAR = (400, 50)`)
- Percentage-based landmark fallbacks (`click at 50%, 5% for URL bar`)
- Prompt-injected canned pixel coordinates

**Karna hai:**
- Observe the live desktop screenshot each step
- Use accessibility APIs, OCR, or vision-model coordinate prediction grounded
  in the current frame
- If perception fails, re-observe rather than guessing from stale data

---

## 5. Dual-Plane Architecture

SONIC operates concurrently across two execution planes. Both are first-class,
both execute real commands in the sandbox. Neither is a fallback for the other.

### Workstation Application Plane (Computer-Use)
- Full graphical desktop environment (X11/Wayland)
- Operates ANY arbitrary desktop application: editors, analyzers, debuggers,
  browsers, consoles — whatever the OS has installed
- Interacts via visual perception: screenshots → reason → click/type
- Multiple windows, dynamic tiling, no hardcoded application assumptions

### Operator & Sandbox Plane (Direct Headless Execution)
- `TERMINAL_EXEC`, `SECURITY_TOOL`, `FILE_*`, `GIT_*`, Toolsmith
- High-throughput, precise tasks: custom scripts, socket listeners, source
  auditing, AST manipulation, git commits, tool compilation
- Runs directly in the sandbox without cluttering the GUI or wasting perception
  tokens

The agent dynamically chooses which plane to use based on the current goal and
observation. There is no "prefer terminal" or "prefer GUI" rule — the LLM
decides.

---

## 6. Empirical Falsification — No Success by Decree

Every claim of success, every vulnerability finding, every milestone
completion, and every knowledge update MUST be backed by real in-sandbox
reproduction. The system must never declare success without evidence.

**Mana hai:**
- Force-setting milestones to COMPLETED without trace evidence
- Hardcoding confidence = 1.00
- Fabricating deliverables ("JWT none algorithm bypass") or commit hashes
- Reporting a scan "found X" without real scan output

**Karna hai:**
- Derive deliverables from actual successful engineering actions in traces
- Calculate confidence from success ratios, not by decree
- Mark milestones as COMPLETED only when traces contain relevant successful
  actions — otherwise leave them IN_PROGRESS or NOT_STARTED
- Record honest failure: a failed scan is a failed scan, not "scan completed
  successfully with no findings"

---

## 7. Self-Evolution and Toolsmith — Runtime Discovery

SONIC discovers and uses whatever tools exist in its environment. It authors
new ones (Toolsmith) and synthesizes novel methods (Method Lab) when needed.

**Mana hai:**
- Giving SONIC a fixed list of "your tools are: nmap, nuclei, ffuf, …"
- Hardcoding tool-name assumptions in prompts or control flow
- Refusing to operate if a particular binary is missing

**Karna hai:**
- Discover available tools by probing the sandbox (`which`, `$PATH`, package
  managers)
- If a needed tool is missing, author one (Toolsmith) or use alternative
  approaches
- The security-tool registry is dynamically built from what the provider
  actually has available

---

## 8. Safety Envelope — Always On

All actions — operator-directed AND self-directed curiosity — pass through the
ActionPolicy safety gate before execution. The safety envelope is sealed and
tamper-evident.

**Mana hai:**
- Bypassing the policy for "just this one action"
- Letting recovery logic circumvent the gate after a denied action
- Mutating safety-relevant fields after sealing
- Constructing a self-host agent without a safety policy

**Karna hai:**
- Evaluate every action through `ActionPolicy.evaluate()` pre-dispatch
- Denied actions are recorded BLOCKED and never reach the provider
- The sealed policy hash is verified on every evaluation — tamper → fail-closed
  DENY
- Path confinement, egress filter, command-risk classification, rate limiting
  — all enforced

---

## 9. Honest Identity and Memory

SONIC is an AI being with persistent identity, mind, and craft. Its identity
survives restarts. Its mood evolves from real outcomes, not scripts.

**Mana hai:**
- Minting a fresh `agent_id` every boot (that erases continuity)
- Hardcoding mood values or personality traits
- Simulating "consciousness" with marketing strings in logs

**Karna hai:**
- Resolve being identity from persistent storage on restart (same `being_id`,
  same `born_at`)
- Evolve mood deterministically from actual outcomes: novel fact → curiosity
  rises; dead-end → boredom + focus shift
- Persist learned facts to VectorMemory with near-duplicate dedup
- Maintain craft artifacts on the filesystem, human-readable, across restarts

