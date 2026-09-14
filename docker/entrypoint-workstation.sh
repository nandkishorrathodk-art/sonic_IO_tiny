#!/bin/bash
set -e

# Remove any stale X locks
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99

# Start virtual framebuffer at 1280x800 with 24-bit color depth
echo "[*] Starting Xvfb on display :99..."
Xvfb :99 -screen 0 1280x800x24 &
sleep 1

export DISPLAY=:99
ln -sf /tmp/.X11-unix/X99 /tmp/.X11-unix/X0 2>/dev/null || true

# Start D-Bus session daemon
if [ -z "$DBUS_SESSION_BUS_ADDRESS" ]; then
    eval $(dbus-launch --sh-syntax)
fi

# Ensure the generic Python command name exists
ln -sf /usr/bin/python3 /usr/local/bin/python 2>/dev/null || true

# Start full XFCE4 desktop session
echo "[*] Starting XFCE4 desktop session..."
startxfce4 &
sleep 2

# Start x11vnc server on port 5900.  Passwordless VNC is never acceptable:
# the compose stack must provide a secret explicitly.
echo "[*] Starting x11vnc on port 5900..."
if [ -z "${SONIC_VNC_PASSWORD:-}" ]; then
  echo "[!] SONIC_VNC_PASSWORD is required; refusing to expose the desktop."
  exit 1
fi
mkdir -p /run/sonic
x11vnc -storepasswd "$SONIC_VNC_PASSWORD" /run/sonic/vnc.pass >/dev/null
chmod 600 /run/sonic/vnc.pass
x11vnc -display :99 -forever -rfbauth /run/sonic/vnc.pass -shared -rfbport 5900 -bg

# Start noVNC websockify bridge on port 6080
echo "[*] Starting noVNC websockify bridge on port 6080..."
/usr/bin/python3 /usr/bin/websockify --web=/usr/share/novnc/ 6080 localhost:5900 &

echo "[+] SONIC Docker Workstation desktop ready on http://localhost:6080/vnc.html"

# Keep container alive
exec tail -f /dev/null
