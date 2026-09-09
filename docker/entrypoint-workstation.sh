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

# Configure Chrome wrapper to always run with --no-sandbox inside docker
cat << 'EOF' > /usr/local/bin/chrome
#!/bin/bash
exec /usr/bin/google-chrome-stable --no-sandbox --disable-dev-shm-usage "$@"
EOF
chmod +x /usr/local/bin/chrome
ln -sf /usr/local/bin/chrome /usr/local/bin/chromium 2>/dev/null || true
ln -sf /usr/local/bin/chrome /usr/local/bin/chromium-browser 2>/dev/null || true

# Ensure python symlink & NSS DB exist
ln -sf /usr/bin/python3 /usr/local/bin/python 2>/dev/null || true
if [ ! -f /root/.pki/nssdb/cert9.db ]; then
    mkdir -p /root/.pki/nssdb
    timeout 5 certutil -d sql:/root/.pki/nssdb -N --empty-password < /dev/null 2>/dev/null || true
fi

# Patch Google Chrome system launcher if not already patched
if [ -f /opt/google/chrome/google-chrome ] && ! grep -q -- '--no-sandbox' /opt/google/chrome/google-chrome; then
    sed -i 's|exec -a "\$0" "\$HERE/chrome" "\$@"|exec -a "\$0" "\$HERE/chrome" --no-sandbox --disable-dev-shm-usage "\$@"|' /opt/google/chrome/google-chrome
fi

# Set up Desktop directory and shortcuts for user
mkdir -p /root/Desktop

# Google Chrome shortcut
cat << 'EOF' > /root/Desktop/google-chrome.desktop
[Desktop Entry]
Version=1.0
Type=Application
Name=Google Chrome
Comment=Access the Internet
Exec=/usr/local/bin/chrome %U
Icon=google-chrome
Path=/root
Terminal=false
StartupNotify=true
Categories=Network;WebBrowser;
EOF
chmod +x /root/Desktop/google-chrome.desktop

# Terminal shortcut
cat << 'EOF' > /root/Desktop/xfce4-terminal.desktop
[Desktop Entry]
Version=1.0
Type=Application
Name=Terminal
Comment=Use the command line
Exec=xfce4-terminal
Icon=utilities-terminal
Path=/root
Terminal=false
StartupNotify=true
Categories=System;TerminalEmulator;
EOF
chmod +x /root/Desktop/xfce4-terminal.desktop

# Thunar File Manager shortcut
cat << 'EOF' > /root/Desktop/thunar.desktop
[Desktop Entry]
Version=1.0
Type=Application
Name=File Manager
Comment=Browse the file system
Exec=thunar
Icon=system-file-manager
Path=/root
Terminal=false
StartupNotify=true
Categories=System;FileManager;
EOF
chmod +x /root/Desktop/thunar.desktop

# Start full XFCE4 desktop session
echo "[*] Starting XFCE4 desktop session..."
startxfce4 &
sleep 2

# Start x11vnc server on port 5900
echo "[*] Starting x11vnc on port 5900..."
x11vnc -display :99 -forever -nopw -shared -rfbport 5900 -bg

# Start noVNC websockify bridge on port 6080
echo "[*] Starting noVNC websockify bridge on port 6080..."
/usr/bin/python3 /usr/bin/websockify --web=/usr/share/novnc/ 6080 localhost:5900 &

echo "[+] SONIC Docker Workstation desktop ready on http://localhost:6080/vnc.html"

# Auto-launch terminal with welcome message
sleep 2
DISPLAY=:99 xfce4-terminal --geometry=80x24+50+50 --title="SONIC Workstation Terminal" --command="bash -c 'echo \"============================================\"; echo \"  SONIC-REDA Cyber Workstation (Docker)\"; echo \"  Full Unrestricted Internet Access Active\"; echo \"  Google Chrome, Nmap, Tools Ready\"; echo \"============================================\"; exec bash'" &

# Keep container alive
exec tail -f /dev/null

