#!/usr/bin/env bash
#
# BTI Nöbetçi (health check)
# --------------------------
# Amaç: kullanıcı siteyi her gün elle kontrol etmek zorunda kalmasın.
# Günlük ajanın HİÇ çalışmadığı durum (Mac kapalıydı, LaunchAgent düştü, script
# baştan patladı) hiçbir bildirim üretmez — bu sessiz başarısızlığı burada yakalarız.
#
# İki şeyi kontrol eder:
#   1) Yerel: daily_update.log'daki son "Tamamlandı" ne kadar eski?
#   2) Canlı: gokhan-c.github.io'daki data/index.json'ın generated_at'i ne kadar eski?
# İkisinden biri eşikten eskiyse masaüstü bildirimi + ALERTS.log kaydı.
#
# LaunchAgent bunu her gün 12:00'da çağırır. Elle: bash check_health.sh
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
PY="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"
[ -x "$PY" ] || PY="$(command -v python3)"

LOG_DIR="$HOME/BTI_Reports/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/health.log"
DAILY_LOG="$LOG_DIR/daily_update.log"
MAX_AGE_H="${MAX_AGE_H:-26}"     # 26 saat: günlük çalışma + gecikme payı
TS() { date "+%Y-%m-%d %H:%M:%S"; }

notify() {
  osascript -e "display notification \"$1\" with title \"BTI Nöbetçi\" sound name \"Basso\"" 2>/dev/null || true
  echo "[$(TS)] $1" >> "$LOG_DIR/ALERTS.log"
}

{
  echo "[$(TS)] nöbetçi kontrolü başladı (eşik: ${MAX_AGE_H} saat)"
  PROBLEMS=""

  # --- 1) Yerel çalışma ne kadar eski? ---
  LAST_RUN=$(grep -a "Tamamlandı" "$DAILY_LOG" 2>/dev/null | tail -1 | sed -E 's/^\[([0-9-]+ [0-9:]+)\].*/\1/')
  if [ -z "$LAST_RUN" ]; then
    PROBLEMS="$PROBLEMS · günlük ajan hiç tamamlanmamış"
  else
    AGE_H=$("$PY" -c "
import sys,datetime
try:
    d=datetime.datetime.strptime('$LAST_RUN','%Y-%m-%d %H:%M:%S')
    print(int((datetime.datetime.now()-d).total_seconds()//3600))
except Exception: print(999)
")
    echo "[$(TS)] son yerel çalışma: $LAST_RUN (${AGE_H} saat önce)"
    [ "$AGE_H" -gt "$MAX_AGE_H" ] && PROBLEMS="$PROBLEMS · günlük ajan ${AGE_H} saattir çalışmadı"
  fi

  # --- 2) Canlı site ne kadar eski? ---
  LIVE_GEN=$(curl -s -m 25 "https://gokhan-c.github.io/bti-system/data/index.json?cb=$(date +%s)" \
    | "$PY" -c "import json,sys;print(json.load(sys.stdin).get('generated_at',''))" 2>/dev/null)
  if [ -z "$LIVE_GEN" ]; then
    PROBLEMS="$PROBLEMS · canlı site okunamadı"
  else
    LIVE_AGE_H=$("$PY" -c "
import datetime
try:
    d=datetime.datetime.strptime('$LIVE_GEN'[:16],'%Y-%m-%d %H:%M')
    print(int((datetime.datetime.now()-d).total_seconds()//3600))
except Exception: print(999)
")
    echo "[$(TS)] canlı site: $LIVE_GEN (${LIVE_AGE_H} saat önce)"
    [ "$LIVE_AGE_H" -gt "$MAX_AGE_H" ] && PROBLEMS="$PROBLEMS · canlı site ${LIVE_AGE_H} saattir güncellenmedi"
  fi

  if [ -n "$PROBLEMS" ]; then
    echo "[$(TS)] SORUN:$PROBLEMS"
    notify "Site güncellenmiyor olabilir:${PROBLEMS}"
  else
    echo "[$(TS)] ✓ her şey yolunda"
  fi
} >> "$LOG" 2>&1
