#!/usr/bin/env bash
#
# surum.sh — BTİ sistemi için basit sürüm yönetimi
#
# Kullanım:
#   ./surum.sh liste                 -> Tüm sürümleri (tarih + açıklama) gösterir
#   ./surum.sh simdi                 -> Şu an hangi sürümde olduğunu gösterir
#   ./surum.sh kaydet "açıklama"     -> Mevcut hali yeni bir sürüm olarak dondurur (v8, v9, ...)
#   ./surum.sh don <sürüm>           -> Belirtilen sürüme geri döner (ör: ./surum.sh don v6)
#
# Her sürüm bir git "tag"i olarak saklanır. Geri dönmek geçmişi SİLMEZ;
# istediğin an yeni sürüm kaydedip ileri de gidebilirsin.

set -euo pipefail
cd "$(dirname "$0")"

komut="${1:-liste}"

# En yüksek vN etiketini bulup bir sonrakini üretir (v3.1 gibi ara sürümleri atlar)
sonraki_surum() {
  local max=0 n
  for t in $(git tag -l 'v[0-9]*'); do
    n="${t#v}"; n="${n%%.*}"          # v3.1 -> 3
    [[ "$n" =~ ^[0-9]+$ ]] || continue
    (( n > max )) && max=$n
  done
  echo "v$(( max + 1 ))"
}

case "$komut" in
  liste)
    echo "=== Sürümler ==="
    for t in $(git tag -l 'v*' | sort -V); do
      printf "%-8s %s  %s\n" "$t" \
        "$(git log -1 --format='%ci' "$t" | cut -d' ' -f1)" \
        "$(git tag -l --format='%(contents:subject)' "$t")"
    done
    echo
    echo "Şu anki sürüm: $(cat VERSION 2>/dev/null || echo '?')"
    ;;

  simdi)
    echo "Kayıtlı sürüm: $(cat VERSION 2>/dev/null || echo '?')"
    echo "HEAD üzerindeki en yakın etiket: $(git describe --tags 2>/dev/null || echo 'yok')"
    ;;

  kaydet)
    aciklama="${2:-}"
    if [[ -z "$aciklama" ]]; then
      echo "HATA: Açıklama gerekli.  Örnek: ./surum.sh kaydet \"site yeni tasarım\"" >&2
      exit 1
    fi
    yeni="$(sonraki_surum)"
    # Bekleyen değişiklik varsa önce commit'le
    if [[ -n "$(git status --porcelain)" ]]; then
      git add -A
      git commit -m "${yeni}: ${aciklama}"
    fi
    echo "$yeni" > VERSION
    git add VERSION
    git commit -m "surum: ${yeni} olarak işaretlendi" >/dev/null 2>&1 || true
    git tag -a "$yeni" -m "${yeni}: ${aciklama}"
    echo "✓ Yeni sürüm kaydedildi: $yeni — $aciklama"
    echo "  (Uzağa göndermek için:  git push && git push --tags)"
    ;;

  don)
    hedef="${2:-}"
    if [[ -z "$hedef" ]]; then
      echo "HATA: Hangi sürüme dönüleceğini yaz.  Örnek: ./surum.sh don v6" >&2
      echo "Mevcut sürümler:"; git tag -l 'v*' | sort -V | sed 's/^/  /'
      exit 1
    fi
    if ! git rev-parse -q --verify "refs/tags/${hedef}" >/dev/null; then
      echo "HATA: '${hedef}' diye bir sürüm yok." >&2
      echo "Mevcut sürümler:"; git tag -l 'v*' | sort -V | sed 's/^/  /'
      exit 1
    fi
    echo "→ '${hedef}' sürümüne dönülüyor..."
    # Çalışma ağacını + index'i tam olarak hedef sürüme eşitle (eklenen dosyalar silinir,
    # silinenler geri gelir). Geçmiş korunur; bu bir "geri alma commit'i" olarak işlenir.
    git read-tree --reset -u "$hedef"
    echo "$hedef" > VERSION
    git add -A
    if git commit -m "surum: ${hedef} sürümüne dönüldü ($(date +%F))" >/dev/null 2>&1; then
      echo "✓ Artık ${hedef} sürümündesin."
    else
      echo "✓ Zaten ${hedef} sürümündeydin (değişiklik yok)."
    fi
    echo "  (Uzağa göndermek için:  git push)"
    ;;

  *)
    echo "Bilinmeyen komut: $komut" >&2
    echo "Kullanım: ./surum.sh [liste | simdi | kaydet \"açıklama\" | don <sürüm>]" >&2
    exit 1
    ;;
esac
