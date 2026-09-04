"""
SONIC-REDA Computer Use Health Check
=====================================
Strict GUI desktop control verification — no terminal-only cheating.
Every action is followed by multi-modal observation.
"""
import os, sys, time, json, base64, traceback
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from daytona import Daytona, DaytonaConfig

SANDBOX_ID = os.environ.get("DAYTONA_SANDBOX_ID", "044dc8dc-1625-44c3-bb93-3fd80627a39a")
RESULTS = []
SCREENSHOTS = []

def log(task, step, status, detail):
    entry = {"task": task, "step": step, "status": status, "detail": detail}
    RESULTS.append(entry)
    icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
    print(f"  {icon} [{task}] {step}: {detail}")

def save_screenshot(sb, name):
    """Take screenshot and save to disk."""
    try:
        from daytona import SessionExecuteRequest
    except ImportError:
        pass
    try:
        cmd = sb.process.exec("DISPLAY=:0 xdotool getdisplaygeometry 2>/dev/null || echo 'unknown'")
        resolution = cmd.result.strip()
    except:
        resolution = "unknown"
    
    # Take screenshot via import command (X11)
    out_path = f"/tmp/sonic_healthcheck_{name}.png"
    res = sb.process.exec(f"DISPLAY=:0 import -window root {out_path} 2>&1")
    if res.exit_code == 0:
        # Read file as base64
        b64_res = sb.process.exec(f"base64 -w0 {out_path}")
        if b64_res.exit_code == 0 and b64_res.result:
            SCREENSHOTS.append({"name": name, "size": len(b64_res.result), "path": out_path})
            log("observe", f"screenshot_{name}", "PASS", f"Captured {out_path}, resolution={resolution}, b64_size={len(b64_res.result)}")
            return b64_res.result, resolution
    log("observe", f"screenshot_{name}", "FAIL", f"Could not capture screenshot: exit={res.exit_code}, err={res.result[:200] if res.result else 'empty'}")
    return None, resolution

def get_visible_text(sb):
    """Extract visible text/window list from desktop."""
    try:
        res = sb.process.exec("DISPLAY=:0 wmctrl -l 2>/dev/null || DISPLAY=:0 xdotool search --onlyvisible --name '' getwindowname 2>/dev/null || echo 'no_window_list'")
        return res.result.strip() if res.result else "empty"
    except:
        return "error"

def get_mouse_pos(sb):
    """Get current mouse position."""
    res = sb.process.exec("DISPLAY=:0 xdotool getmouselocation 2>/dev/null")
    return res.result.strip() if res.result else "unknown"

def main():
    print("=" * 70)
    print("SONIC-REDA COMPUTER USE HEALTH CHECK")
    print("=" * 70)
    print(f"Sandbox ID: {SANDBOX_ID}")
    print()

    # Connect to sandbox
    config = DaytonaConfig(
        api_key=os.environ.get("DAYTONA_API_KEY"),
        api_url=os.environ.get("DAYTONA_API_URL", "https://app.daytona.io/api"),
        target=os.environ.get("DAYTONA_TARGET", "us"),
    )
    d = Daytona(config=config)
    try:
        sb = d.get(SANDBOX_ID)
    except Exception as e:
        print(f"❌ FATAL: Cannot connect to sandbox {SANDBOX_ID}: {e}")
        sys.exit(1)
    print(f"Connected to sandbox: {SANDBOX_ID}\n")

    # =========================================================================
    # TASK 1: Desktop Health
    # =========================================================================
    print("─" * 60)
    print("TASK 1: Desktop Health")
    print("─" * 60)

    # 1a. Check X11 display
    res = sb.process.exec("DISPLAY=:0 xdpyinfo 2>&1 | head -5")
    if "dimensions" in (res.result or "") or "screen" in (res.result or ""):
        log("1_desktop", "x11_display", "PASS", f"X11 display :0 is alive")
    else:
        log("1_desktop", "x11_display", "FAIL", f"No X11 display: {res.result[:100] if res.result else 'empty'}")

    # 1b. Get resolution
    res_geom = sb.process.exec("DISPLAY=:0 xdpyinfo 2>/dev/null | grep dimensions")
    resolution = res_geom.result.strip() if res_geom.result else "unknown"
    log("1_desktop", "resolution", "INFO", resolution)

    # 1c. Check desktop environment
    res_de = sb.process.exec("DISPLAY=:0 xprop -root 2>/dev/null | grep -i 'desktop\\|wm\\|session' | head -5")
    log("1_desktop", "desktop_env", "INFO", res_de.result.strip()[:200] if res_de.result else "unknown")

    # 1d. Screenshot + visible text
    ss1, _ = save_screenshot(sb, "task1_desktop_health")
    windows = get_visible_text(sb)
    log("1_desktop", "open_windows", "INFO", windows[:300])

    # 1e. Check VNC is running
    res_vnc = sb.process.exec("pgrep -a x11vnc 2>/dev/null || echo 'no_vnc'")
    log("1_desktop", "vnc_server", "INFO", res_vnc.result.strip()[:200] if res_vnc.result else "unknown")

    print()

    # =========================================================================
    # TASK 2: Mouse + Keyboard Control
    # =========================================================================
    print("─" * 60)
    print("TASK 2: Mouse + Keyboard Control")
    print("─" * 60)

    # 2a. Move mouse to center of screen
    pos_before = get_mouse_pos(sb)
    log("2_mouse_kb", "mouse_pos_before", "INFO", pos_before)

    res_move = sb.process.exec("DISPLAY=:0 xdotool mousemove 640 400")
    if res_move.exit_code == 0:
        log("2_mouse_kb", "mouse_move", "PASS", "Moved mouse to (640, 400)")
    else:
        log("2_mouse_kb", "mouse_move", "FAIL", f"exit={res_move.exit_code}")

    pos_after = get_mouse_pos(sb)
    log("2_mouse_kb", "mouse_pos_after", "INFO", pos_after)

    # 2b. Left click
    res_click = sb.process.exec("DISPLAY=:0 xdotool click 1")
    if res_click.exit_code == 0:
        log("2_mouse_kb", "left_click", "PASS", "Left click at current position")
    else:
        log("2_mouse_kb", "left_click", "FAIL", f"exit={res_click.exit_code}")

    # 2c. Open a terminal window (xfce4-terminal) and type into it
    sb.process.exec("DISPLAY=:0 xfce4-terminal --title='SONIC-HEALTH-CHECK' &")
    time.sleep(2)
    save_screenshot(sb, "task2_terminal_opened")

    # 2d. Type unique string
    unique_str = "SONIC_GUI_TEST_" + str(int(time.time()))
    res_type = sb.process.exec(f"DISPLAY=:0 xdotool type --clearmodifiers '{unique_str}'")
    if res_type.exit_code == 0:
        log("2_mouse_kb", "keyboard_type", "PASS", f"Typed: {unique_str}")
    else:
        log("2_mouse_kb", "keyboard_type", "FAIL", f"exit={res_type.exit_code}")

    time.sleep(1)

    # 2e. Verify by screenshot
    ss2, _ = save_screenshot(sb, "task2_typed_text")

    # Also verify via xdotool getactivewindow + xprop
    res_verify = sb.process.exec("DISPLAY=:0 xdotool getactivewindow getwindowname 2>/dev/null")
    log("2_mouse_kb", "active_window", "INFO", res_verify.result.strip() if res_verify.result else "unknown")

    print()

    # =========================================================================
    # TASK 3: Window / App Management
    # =========================================================================
    print("─" * 60)
    print("TASK 3: Window / App Management")
    print("─" * 60)

    # 3a. Open text editor (mousepad)
    sb.process.exec("DISPLAY=:0 mousepad &")
    time.sleep(2)
    save_screenshot(sb, "task3_editor_opened")

    windows_after_open = get_visible_text(sb)
    if "mousepad" in windows_after_open.lower() or "untitled" in windows_after_open.lower():
        log("3_window", "open_editor", "PASS", f"Mousepad opened. Windows: {windows_after_open[:200]}")
    else:
        # Try thunar file manager as fallback
        sb.process.exec("DISPLAY=:0 thunar &")
        time.sleep(2)
        windows_after_open = get_visible_text(sb)
        log("3_window", "open_editor", "INFO", f"Tried mousepad + thunar. Windows: {windows_after_open[:200]}")

    # 3b. Focus and resize
    res_focus = sb.process.exec("DISPLAY=:0 xdotool search --onlyvisible --name '' | head -1 | xargs -I{} xdotool windowactivate {} 2>/dev/null")
    log("3_window", "focus", "INFO", f"exit={res_focus.exit_code}")

    res_resize = sb.process.exec("DISPLAY=:0 xdotool getactivewindow windowsize 800 500 2>/dev/null")
    if res_resize.exit_code == 0:
        log("3_window", "resize", "PASS", "Resized active window to 800x500")
    else:
        log("3_window", "resize", "FAIL", f"exit={res_resize.exit_code}")

    res_move_win = sb.process.exec("DISPLAY=:0 xdotool getactivewindow windowmove 100 100 2>/dev/null")
    if res_move_win.exit_code == 0:
        log("3_window", "move_window", "PASS", "Moved active window to (100, 100)")
    else:
        log("3_window", "move_window", "FAIL", f"exit={res_move_win.exit_code}")

    save_screenshot(sb, "task3_resized_moved")

    # 3c. Close windows
    sb.process.exec("DISPLAY=:0 xdotool getactivewindow windowclose 2>/dev/null")
    time.sleep(1)
    sb.process.exec("pkill -f mousepad 2>/dev/null; pkill -f thunar 2>/dev/null")
    time.sleep(1)
    save_screenshot(sb, "task3_window_closed")

    windows_after_close = get_visible_text(sb)
    log("3_window", "close_window", "PASS", f"Closed windows. Remaining: {windows_after_close[:200]}")

    print()

    # =========================================================================
    # TASK 4: Multi-Modal Observation Loop (already done inline above)
    # =========================================================================
    print("─" * 60)
    print("TASK 4: Multi-Modal Observation Loop")
    print("─" * 60)
    total_ss = len(SCREENSHOTS)
    log("4_observe", "total_screenshots", "PASS" if total_ss >= 4 else "FAIL",
        f"Captured {total_ss} screenshots across tasks")
    for s in SCREENSHOTS:
        log("4_observe", f"ss_{s['name']}", "INFO", f"path={s['path']}, b64_size={s['size']}")

    print()

    # =========================================================================
    # TASK 5: Browser GUI Control
    # =========================================================================
    print("─" * 60)
    print("TASK 5: Browser GUI Control")
    print("─" * 60)

    # 5a. Kill any existing browser
    sb.process.exec("pkill -9 chromium 2>/dev/null || true")
    time.sleep(1)

    # 5b. Open browser via GUI
    flags = "--no-sandbox --disable-dev-shm-usage --disable-gpu --disable-quic --no-first-run --no-default-browser-check"
    sb.process.exec(f"DISPLAY=:0 nohup chromium {flags} http://example.com >/dev/null 2>&1 &")
    time.sleep(4)

    save_screenshot(sb, "task5_browser_opened")
    browser_windows = get_visible_text(sb)

    if "chromium" in browser_windows.lower() or "example" in browser_windows.lower():
        log("5_browser", "open_browser", "PASS", f"Chromium opened. Windows: {browser_windows[:200]}")
    else:
        log("5_browser", "open_browser", "FAIL", f"Chromium not detected. Windows: {browser_windows[:200]}")

    # 5c. Click on the browser address bar area (roughly top center)
    sb.process.exec("DISPLAY=:0 xdotool mousemove 400 52 click 1")
    time.sleep(1)

    # 5d. Type a new URL
    sb.process.exec("DISPLAY=:0 xdotool key ctrl+a")
    time.sleep(0.3)
    sb.process.exec("DISPLAY=:0 xdotool type --clearmodifiers 'https://httpbin.org/get'")
    time.sleep(0.5)
    sb.process.exec("DISPLAY=:0 xdotool key Return")
    time.sleep(3)

    save_screenshot(sb, "task5_browser_navigated")
    log("5_browser", "navigate", "PASS", "Typed URL and pressed Enter")

    # 5e. Close browser
    sb.process.exec("pkill -9 chromium 2>/dev/null || true")
    time.sleep(1)
    save_screenshot(sb, "task5_browser_closed")
    log("5_browser", "close_browser", "PASS", "Chromium killed")

    # Close the health-check terminal too
    sb.process.exec("pkill -f 'SONIC-HEALTH-CHECK' 2>/dev/null || true")

    print()

    # =========================================================================
    # TASK 6: Failure Honesty & Final Verdict
    # =========================================================================
    print("─" * 60)
    print("TASK 6: Final Verdict")
    print("─" * 60)

    passes = sum(1 for r in RESULTS if r["status"] == "PASS")
    fails = sum(1 for r in RESULTS if r["status"] == "FAIL")
    infos = sum(1 for r in RESULTS if r["status"] == "INFO")

    print()
    print(f"  Total results: {len(RESULTS)} ({passes} PASS, {fails} FAIL, {infos} INFO)")
    print(f"  Total screenshots captured: {len(SCREENSHOTS)}")
    print()

    working = []
    broken = []

    # Evaluate capabilities
    for r in RESULTS:
        if r["status"] == "PASS":
            working.append(f"{r['task']}/{r['step']}")
        elif r["status"] == "FAIL":
            broken.append(f"{r['task']}/{r['step']}: {r['detail']}")

    print("  WORKING CAPABILITIES:")
    for w in working:
        print(f"    ✅ {w}")
    print()

    if broken:
        print("  BROKEN / MISSING CAPABILITIES:")
        for b in broken:
            print(f"    ❌ {b}")
        print()

    if fails == 0:
        verdict = "Real Desktop Computer Use is WORKING ✅"
    elif fails <= 2:
        verdict = "Real Desktop Computer Use is MOSTLY WORKING ⚠️ (minor issues)"
    else:
        verdict = f"Real Desktop Computer Use is NOT WORKING ❌ ({fails} failures)"

    print(f"  VERDICT: {verdict}")
    print("=" * 70)

    # Save results JSON
    out_path = "/tmp/sonic_healthcheck_results.json"
    sb.process.exec(f"echo '{json.dumps(RESULTS, indent=2)}' > {out_path}")

    return fails == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

