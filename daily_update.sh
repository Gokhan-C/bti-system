#!/usr/bin/env bash
#
# BTI Günlük Güncelleme — tek giriş noktası
# -----------------------------------------
# 1) main.py ile tüm connector'ları çalıştırır (dünün kararlarını çeker)
# 2) site/build_site.py ile siteyi (data.js) tazeler
#
# LaunchAgent bu scripti her gün 06:00'da çağırır. Elle de çalıştırılabilir:
#     bash daily_update.sh
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# claude CLI, node ve python.org binaries PATH'te olsun (launchd minimal PATH ile gelir)
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Deps'in kurulu olduğu Python (Homebrew default'u değil)
PY="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"
[ -x "$PY" ] || PY="$(command -v python3)"

LOG_DIR="$HOME/BTI_Reports/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/daily_update.log"
TS() { date "+%Y-%m-%d %H:%M:%S"; }

{
  echo ""
  echo "════════════════════════════════════════════════════════"
  echo "[$(TS)] BTI günlük güncelleme başladı (PY=$PY)"

  # 1) Veri çekme + raporlar (tüm connector'lar, varsayılan tarih = dün)
  echo "[$(TS)] main.py çalışıyor..."
  "$PY" "$SCRIPT_DIR/main.py" --config "$SCRIPT_DIR/config.yaml"
  echo "[$(TS)] main.py bitti (exit=$?)"

  # 2) Siteyi tazele
  echo "[$(TS)] build_site.py çalışıyor..."
  "$PY" "$SCRIPT_DIR/site/build_site.py"
  echo "[$(TS)] build_site.py bitti (exit=$?)"

  echo "[$(TS)] Tamamlandı."
} >> "$LOG" 2>&1
