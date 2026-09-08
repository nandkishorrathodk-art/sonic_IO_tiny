# UPCOMING PLAN: Autonomous Human-Like Cyber Workstation (Phase 8)

> **Status:** Saved for Upcoming Implementation (Testing Current Baseline First)  
> **Reference Architecture:** Dual-Brain Cyber Workstation (Motor Reflexes + Cognitive Vision)

---

## 1. Context & User Strategy
The user's directive:
> *"ye upcoming plan main add karo kyu ki main ne abhi current main sonic ko test nhi kia hai . tum batao karna chahiye impliments then test ?"*

We keep this complete roadmap locked in the plan so no insight is lost, while prioritizing testing of the **current existing SONIC workstation** to establish a baseline before writing the Phase 8 layer.

---

## 2. The 6 Dark Realities & Targeted Solutions

### A. GTK File Chooser Dialog Trap
- **Issue:** File chooser dialogs in Linux have no DOM. Trying to click folders via VLM coordinates often leads to missed clicks or navigating to the wrong directory.
- **Solution:** Pro-Hacker GTK Reflex in `MotorReflexes`:
  - Detect file chooser dialog on screen.
  - Send hotkey `Ctrl + L` to open direct path bar (`Location:`).
  - Type target file path (`/tmp/cacert.der`) with human typing cadence.
  - Send `Return`.

### B. Java Swing Micro-Target Trap (Burp Suite)
- **Issue:** Burp Suite buttons ("Forward", "Drop", "Repeater") are only 14-18 pixels wide. VLM coordinates across a 1280x800 canvas have a ±12px error margin, hitting empty grey space or wrong buttons.
- **Solution:** Hierarchical Micro-Crop in `grounding.py`:
  - Crop active window toolbar (top 100px region).
  - Pass cropped image to vision model so 14px buttons appear as 70px targets.
  - Map predicted coordinates back to global canvas space.

### C. Proxy Intercept Deadlock
- **Issue:** When Burp has "Intercept is on" and Chrome triggers a request, Chrome enters an indefinite loading spinner. If the agent waits for Chrome to finish loading while Burp waits for a human to click "Forward", the system freezes in a deadlock.
- **Solution:** Dual-State Deadlock Detector in `agent.py`:
  - If Chrome is spinning > 1.0s after an action, auto-switch window focus to Burp Suite (`wmctrl -a "Burp Suite"`).
  - Check if a request is waiting in the Intercept tab.
  - Extract payload into `HackerScratchpad`, click "Forward", and return focus to Chrome.

### D. X11 Click-to-Focus Dropped Events
- **Issue:** Clicking an inactive X11 window only raises it to the foreground; the initial click event does not reach the underlying button.
- **Solution:** Two-Stage Click Reflex:
  1. Determine window at `(x, y)`.
  2. If inactive, raise window via `wmctrl -a` or `xdotool windowactivate`.
  3. Settle screen for 150ms.
  4. Dispatch physical click at `(x, y)`.
  5. Compare pre- and post-action screenshot hashes to verify visual reaction.

### E. Token Burn & Vision Delay (429 Rate Limits)
- **Issue:** Sending full 1280x800 screenshots to VLM for every single click burns ~3,000 tokens per action and takes 6-8 seconds per step.
- **Solution:**
  - Strict CLI-First execution for scanning and directory discovery.
  - Hotkey reflexes for address bar (`Ctrl+L`), tab closing (`Ctrl+W`), and modal dismissal (`Escape`).
  - Local heuristic coordinate lookup for standard controls before falling back to remote VLM calls.

### F. Zero-Click Burp Suite Startup & CA Trust Handshake
- **Issue:** Launching Burp manually triggers interactive EULA and project wizards. Fetching `http://127.0.0.1:8080/cert` before the JVM fully binds port 8080 results in connection refused.
- **Solution:**
  - Launch with pre-seeded `/root/.BurpSuite/user_options.json` and `-Xmx512m` memory bounds.
  - Synchronous socket polling on `127.0.0.1:8080` before fetching CA certificate.
  - Automated import into `/usr/local/share/ca-certificates/` and Chromium's NSS db (`certutil -d sql:/root/.pki/nssdb`).

---

## 3. Implementation Phasing

1. **Step 1: Baseline Evaluation (Current SONIC)**
   - Test current workstation provisioning, Chrome navigation, and terminal commands.
   - Observe baseline performance and record any failure points.
2. **Step 2: Workstation Bootstrap Engine**
   - Implement `sonic/computer/bootstrap.py` for automated dependency auditing and Burp CA handshake.
3. **Step 3: System 1 Motor Reflex Enhancements**
   - Implement GTK `Ctrl+L` file dialog handler, Two-Stage Click, and Deadlock Detector.
4. **Step 4: Micro-Target Visual Grounding**
   - Implement localized image cropping in `grounding.py` for Java Swing widgets.

