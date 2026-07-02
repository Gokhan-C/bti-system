#!/usr/bin/env bash
#
# BTI Günlük Güncelleme — tek giriş noktası
# -----------------------------------------
# 1) main.py ile tüm connector'ları çalıştırır (dünün kararlarını çeker)
# 2) site/build_site.py ile siteyi (data.js) tazeler
# 3) Güncel site/klasörünü GitHub Pages'e push eder (otomatik yayın)
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
  MAIN_OUT="$LOG_DIR/last_main_run.log"
  "$PY" "$SCRIPT_DIR/main.py" --config "$SCRIPT_DIR/config.yaml" 2>&1 | tee "$MAIN_OUT"
  echo "[$(TS)] main.py bitti (exit=$?)"

  # 1b) Hata veren connector'ları tek tek yeniden dene (2 Tem 2026: eu_ebti
  # launch timeout ile düşünce günün EU verisi tamamen kaçmıştı).
  FAILED=$(grep '✗ HATA' "$MAIN_OUT" | sed -E 's/.*│ *([a-z_]+) .*/\1/' | sort -u)
  STILL_FAILED=""
  for C in $FAILED; do
    echo "[$(TS)] $C hata verdi, 120 sn sonra yeniden deneniyor..."
    sleep 120
    RETRY_OUT="$LOG_DIR/last_retry_$C.log"
    "$PY" "$SCRIPT_DIR/main.py" --config "$SCRIPT_DIR/config.yaml" --connector "$C" 2>&1 | tee "$RETRY_OUT"
    if grep -q '✗ HATA' "$RETRY_OUT"; then
      STILL_FAILED="$STILL_FAILED $C"
      echo "[$(TS)] $C yeniden denemede de BAŞARISIZ."
    else
      echo "[$(TS)] $C yeniden denemede başarılı."
    fi
  done
  # 1c) Bugün de çekilemeyenleri telafi kuyruğuna yaz: ertesi sabahki çalışma
  # bu günleri --date ile otomatik yeniden dener (format: connector|DD-MM-YYYY|deneme).
  QUEUE="$LOG_DIR/missed_days.txt"
  YDATE=$(date -v-1d "+%d-%m-%Y")
  if [ -n "$STILL_FAILED" ]; then
    for C in $STILL_FAILED; do
      echo "$C|$YDATE|0" >> "$QUEUE"
    done
    echo "[$(TS)] HATA: şu connector'lar bugün veri çekemedi:$STILL_FAILED — yarın otomatik telafi edilecek."
    osascript -e "display notification \"Veri çekilemedi:$STILL_FAILED — yarın otomatik telafi edilecek\" with title \"BTI Günlük Güncelleme\"" 2>/dev/null || true
  fi

  # 1d) Önceki günlerden kalan telafi kuyruğunu işle (bugün eklenenler atlanır;
  # onlar zaten az önce 2 kez denendi). Başarılı olan kuyruktan düşer, başarısız
  # olan deneme sayısı artarak kalır; 7 denemeden sonra vazgeçilir ve bildirilir.
  if [ -s "$QUEUE" ]; then
    echo "[$(TS)] Telafi kuyruğu işleniyor..."
    NEW_QUEUE="$QUEUE.tmp"
    : > "$NEW_QUEUE"
    while IFS='|' read -r C D N; do
      [ -z "$C" ] && continue
      if [ "$D" = "$YDATE" ]; then
        echo "$C|$D|$N" >> "$NEW_QUEUE"
        continue
      fi
      echo "[$(TS)] Telafi: $C / $D (önceki deneme: $N) çekiliyor..."
      BACKFILL_OUT="$LOG_DIR/last_backfill_${C}.log"
      "$PY" "$SCRIPT_DIR/main.py" --config "$SCRIPT_DIR/config.yaml" --connector "$C" --date "$D" 2>&1 | tee "$BACKFILL_OUT"
      if grep -q '✗ HATA' "$BACKFILL_OUT"; then
        N=$((N + 1))
        if [ "$N" -ge 7 ]; then
          echo "[$(TS)] Telafi: $C / $D 7 denemede de başarısız — VAZGEÇİLDİ, veri elle çekilmeli."
          osascript -e "display notification \"$C / $D telafisi 7 denemede başarısız — elle çekilmeli\" with title \"BTI Günlük Güncelleme\"" 2>/dev/null || true
        else
          echo "$C|$D|$N" >> "$NEW_QUEUE"
          echo "[$(TS)] Telafi: $C / $D yine başarısız, kuyrukta kalıyor (deneme: $N)."
        fi
      else
        echo "[$(TS)] Telafi: $C / $D BAŞARILI, kuyruktan düşürüldü."
      fi
    done < "$QUEUE"
    mv "$NEW_QUEUE" "$QUEUE"
    [ -s "$QUEUE" ] || rm -f "$QUEUE"
  fi

  # 2) Siteyi tazele
  echo "[$(TS)] build_site.py çalışıyor..."
  "$PY" "$SCRIPT_DIR/site/build_site.py"
  echo "[$(TS)] build_site.py bitti (exit=$?)"

  # 3) GitHub Pages'e push (site/ → gh-pages branch)
  echo "[$(TS)] GitHub Pages push başlıyor..."
  TODAY=$(date "+%Y-%m-%d")
  git add site/
  if git diff --cached --quiet; then
    echo "[$(TS)] site/ değişmedi, yeni commit yok."
  else
    git commit -q -m "chore(site): otomatik güncelleme $TODAY"
  fi

  # Push her zaman denenir: önceki gün ağ hatasıyla lokalde kalmış
  # commit'ler varsa burada kendiliğinden gider (self-healing).
  PUSH_OK=0
  for ATTEMPT in 1 2 3; do
    if git push origin master && git subtree push --prefix site origin gh-pages; then
      PUSH_OK=1
      echo "[$(TS)] GitHub Pages push tamamlandı (deneme $ATTEMPT)."
      break
    fi
    echo "[$(TS)] Push başarısız (deneme $ATTEMPT/3), 60 sn sonra tekrar denenecek..."
    sleep 60
  done
  if [ "$PUSH_OK" -ne 1 ]; then
    echo "[$(TS)] HATA: GitHub push 3 denemede de başarısız — site GÜNCELLENMEDİ, commit'ler lokalde bekliyor."
    osascript -e 'display notification "GitHub push 3 denemede başarısız — site güncellenmedi" with title "BTI Günlük Güncelleme"' 2>/dev/null || true
  fi

  echo "[$(TS)] Tamamlandı."
} >> "$LOG" 2>&1
