#!/usr/bin/env bash
# BTI Sistemi Kurulum Scripti
# Çalıştırma: bash setup.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_PATH="$HOME/Library/LaunchAgents/com.user.bti-system-daily.plist"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  BTI Günlük Sistem — Kurulum"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# [1/5] Python bağımlılıkları
echo ""
echo "[1/5] Python bağımlılıkları yükleniyor..."
python3 -m pip install --quiet playwright requests python-docx pyyaml deep-translator
echo "  ✓ playwright, requests, python-docx, pyyaml, deep-translator"

# [2/5] Playwright Chromium
echo ""
echo "[2/5] Playwright Chromium tarayıcısı yükleniyor..."
python3 -m playwright install chromium
echo "  ✓ Chromium hazır"

# [3/5] Node.js bağımlılıkları (AB EBTI .docx üretici için)
echo ""
echo "[3/5] Node.js bağımlılıkları yükleniyor (assets/)..."
npm install --prefix "$SCRIPT_DIR/assets" --silent
echo "  ✓ docx paketi hazır"

# [4/5] State migrasyonu
echo ""
echo "[4/5] State dosyaları kontrol ediliyor..."
CBSA_OLD="$HOME/Desktop/claude/code/Gumruk_Kararlar/cbsa_seen_ids.json"
CBSA_NEW="$SCRIPT_DIR/state/ca_cbsa_seen.json"
mkdir -p "$SCRIPT_DIR/state"
if [ -f "$CBSA_OLD" ] && [ ! -f "$CBSA_NEW" ]; then
    cp "$CBSA_OLD" "$CBSA_NEW"
    echo "  ✓ CBSA state taşındı: $CBSA_NEW"
elif [ -f "$CBSA_NEW" ]; then
    echo "  ✓ CBSA state zaten mevcut: $CBSA_NEW"
else
    echo "  ⚠ CBSA eski state bulunamadı, boş başlatılacak"
    echo "[]" > "$CBSA_NEW"
fi

# [5/5] macOS LaunchAgent (06:00 günlük çalışma)
echo ""
echo "[5/5] macOS LaunchAgent kuruluyor (06:00)..."
mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "$HOME/BTI_Reports/logs"
mkdir -p "$SCRIPT_DIR/logs"

# Çalışan path'i bul (Homebrew + sistem)
PYTHON_PATH="$(command -v python3 || echo '/usr/bin/python3')"

cat > "$PLIST_PATH" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.bti-system-daily</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>${SCRIPT_DIR}/main.py</string>
        <string>--config</string>
        <string>${SCRIPT_DIR}/config.yaml</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>6</integer>
        <key>Minute</key><integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>${HOME}/BTI_Reports/logs/launchd_stdout.log</string>

    <key>StandardErrorPath</key>
    <string>${HOME}/BTI_Reports/logs/launchd_stderr.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin:/opt/homebrew/sbin</string>
        <key>HOME</key>
        <string>${HOME}</string>
    </dict>

    <key>WorkingDirectory</key>
    <string>${SCRIPT_DIR}</string>

    <key>RunAtLoad</key>
    <false/>

    <key>StandardErrorPath</key>
    <string>${HOME}/BTI_Reports/logs/launchd_stderr.log</string>
</dict>
</plist>
PLIST

# Varsa önce kaldır, sonra yükle
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"
echo "  ✓ LaunchAgent yüklendi: com.user.bti-system-daily"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Kurulum tamamlandı!"
echo ""
echo "  Otomatik çalışma: Her gün 06:00"
echo "  Raporlar: ~/BTI_Reports/"
echo "  Loglar:   ~/BTI_Reports/logs/launchd_stdout.log"
echo ""
echo "  Manuel test için:"
echo "    cd $SCRIPT_DIR && python3 main.py"
echo ""
echo "  Tek connector testi:"
echo "    python3 main.py --connector us_cbp"
echo "    python3 main.py --connector ca_cbsa"
echo "    python3 main.py --connector eu_ebti"
echo ""
echo "  LaunchAgent'ı hemen tetikle:"
echo "    launchctl start com.user.bti-system-daily"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
