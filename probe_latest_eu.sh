#!/usr/bin/env bash
# EBTI'nin elindeki EN YENİ veri gününü bulur ve çeker.
# 18 Haziran'dan geriye doğru dener; boş günler ~5 sn'de geçer,
# ilk veri bulunan günde durur. Sonra siteyi tazeler.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
PY="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"
OUT="$HOME/BTI_Reports/EU_EBTI"
LOG="$HOME/BTI_Reports/logs/probe_eu.log"
TS(){ date "+%Y-%m-%d %H:%M:%S"; }

reccount(){ # $1 = YYYY-MM-DD
  local f="$OUT/$1/_report_data.json"
  [ -f "$f" ] || { echo 0; return; }
  "$PY" -c "import json,sys;print(len(json.load(open(sys.argv[1])).get('records',[])))" "$f" 2>/dev/null || echo 0
}

{
echo "════════════════════════════════════════"
echo "[$(TS)] EBTI en güncel gün taraması başladı"
FOUND=""
# 18 Haz → 1 Haz arası geriye doğru (en fazla 18 gün)
for d in 18 17 16 15 12 11 10 09 08 05 04 03 02 01; do
  DATE="${d}-06-2026"
  ISO="2026-06-$(printf %02d $((10#$d)))"
  echo "[$(TS)] EU deneniyor: $ISO"
  "$PY" "$SCRIPT_DIR/main.py" --connector eu_ebti --date "$DATE" >/dev/null 2>&1
  N=$(reccount "$ISO")
  echo "[$(TS)]   → $ISO: $N kayıt"
  if [ "$N" -gt 0 ] 2>/dev/null; then FOUND="$ISO"; break; fi
done

if [ -n "$FOUND" ]; then
  echo "[$(TS)] ✓ En güncel veri günü: $FOUND"
else
  echo "[$(TS)] ⚠ Haziran'da EU verisi bulunamadı (yayın gecikmesi olabilir)"
fi

echo "[$(TS)] build_site.py çalışıyor..."
"$PY" "$SCRIPT_DIR/site/build_site.py"
echo "[$(TS)] Tamamlandı. (FOUND=$FOUND)"
} >> "$LOG" 2>&1
echo "PROBE_DONE FOUND=$FOUND"
