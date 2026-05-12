"""
Çeviri motoru sarmalayıcıları.
  - call_claude / translate_batch_claude / translate_all_claude  → Claude CLI
  - translate_google                                             → Google Translate
  - summarize_cbp_ruling_claude                                  → CBP kararı 3 madde özet
"""

import re
import subprocess
import time
from typing import Any


CHUNK_SIZE = 4500  # Google Translate karakter limiti


# ── Claude CLI ────────────────────────────────────────────────────────────────

def call_claude(prompt: str, timeout: int = 180) -> str:
    result = subprocess.run(
        ["claude", "-p", prompt, "--allowedTools", ""],
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[:300])
    return result.stdout.strip()


def translate_batch_claude(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    EBTI BTI kayıtlarını Claude CLI ile Türkçeye çevirir.
    Her kayıtta 'LANGUAGE', 'DESCRIPTION_OF_GOODS', 'CLASSIFICATION_JUSTIFICATION' beklenir.
    Sonuç: her kayda 'desc_tr' ve 'just_tr' eklenir.
    """
    lines = []
    for idx, row in enumerate(batch):
        lines.append(f"### KAYIT_{idx + 1}")
        lines.append(f"DİL: {row.get('LANGUAGE', 'fr')}")
        lines.append(f"TANIM: {(row.get('DESCRIPTION_OF_GOODS') or '').strip()}")
        lines.append(f"GEREKÇE: {(row.get('CLASSIFICATION_JUSTIFICATION') or '').strip()}")
        lines.append("")

    prompt = (
        "Aşağıdaki EBTI BTI kayıtlarını Türkçeye çevir. "
        "Her kayıt için tam ve eksiksiz çeviri yap; boyutlar, ağırlıklar, "
        "malzeme bileşimleri, sınıflandırma kural numaraları dahil. "
        "Kısaltma yapma. Sadece çeviriyi yaz, açıklama ekleme.\n\n"
        + "\n".join(lines)
        + "\n\nHer kayıt için şu formatta yanıt ver (başka hiçbir şey yazma):\n"
          "### KAYIT_1\nTANIM_TR: ...\nGEREKÇE_TR: ...\n\n"
          "### KAYIT_2\nTANIM_TR: ...\nGEREKÇE_TR: ..."
    )

    response = call_claude(prompt)

    parsed_desc: dict[int, str] = {}
    parsed_just: dict[int, str] = {}
    current = None
    desc_lines: list[str] = []
    just_lines: list[str] = []
    mode = None

    for line in response.splitlines():
        m = re.match(r"### KAYIT_(\d+)", line)
        if m:
            if current is not None:
                parsed_desc[current] = " ".join(desc_lines).strip()
                parsed_just[current] = " ".join(just_lines).strip()
            current = int(m.group(1)) - 1
            desc_lines, just_lines = [], []
            mode = None
        elif line.startswith("TANIM_TR:"):
            mode = "desc"
            desc_lines = [line[9:].strip()]
        elif line.startswith("GEREKÇE_TR:"):
            mode = "just"
            just_lines = [line[11:].strip()]
        elif mode == "desc" and line.strip():
            desc_lines.append(line)
        elif mode == "just" and line.strip():
            just_lines.append(line)

    if current is not None:
        parsed_desc[current] = " ".join(desc_lines).strip()
        parsed_just[current] = " ".join(just_lines).strip()

    results = []
    for idx, row in enumerate(batch):
        results.append({
            **row,
            "desc_tr": parsed_desc.get(idx) or row.get("DESCRIPTION_OF_GOODS", ""),
            "just_tr": parsed_just.get(idx) or row.get("CLASSIFICATION_JUSTIFICATION", ""),
        })
    return results


def translate_all_claude(
    rows: list[dict[str, Any]],
    batch_size: int = 8,
    logger=None,
) -> list[dict[str, Any]]:
    translated: list[dict[str, Any]] = []
    total = len(rows)
    for start in range(0, total, batch_size):
        batch = rows[start : start + batch_size]
        if logger:
            logger.info(f"  Claude çevirisi: {start + 1}-{min(start + batch_size, total)}/{total}")
        try:
            translated.extend(translate_batch_claude(batch))
        except Exception as e:
            if logger:
                logger.warning(f"  Çeviri hatası ({e}), orijinal metin kullanılıyor")
            for row in batch:
                translated.append({
                    **row,
                    "desc_tr": row.get("DESCRIPTION_OF_GOODS", ""),
                    "just_tr": row.get("CLASSIFICATION_JUSTIFICATION", ""),
                })
    return translated


# ── CBP Karar Özeti (Claude) ─────────────────────────────────────────────────

def summarize_cbp_ruling_claude(
    subject: str,
    text: str,
    tariffs: str,
    ruling_number: str,
    logger=None,
) -> dict[str, str]:
    """
    Bir ABD CBP gümrük kararını Claude CLI ile 3 maddeye özetler.

    Dönüş:
        {
          "esya_tanimi":     str,   # Eşyanın ticari tanımı
          "gtip_karar":      str,   # Verilen GTİP + talep edilen GTİP (varsa)
          "teknik_gerekce":  str,   # Sınıflandırmanın teknik gerekçesi
        }
    """
    # Metni makul uzunlukta tut (Claude token limitini zorlamasın)
    text_excerpt = (text or "")[:4000]

    prompt = (
        f"Aşağıdaki ABD CBP gümrük tarife sınıflandırma kararını analiz et.\n\n"
        f"KARAR NO: {ruling_number}\n"
        f"KONU: {subject}\n"
        f"GTİP KODLARI: {tariffs}\n\n"
        f"TAM METİN:\n{text_excerpt}\n\n"
        f"Sadece aşağıdaki 3 satırı Türkçe olarak yaz, başka hiçbir şey ekleme:\n\n"
        f"EŞYA_TANIMI: [Eşyanın kısa ve net ticari tanımı]\n"
        f"GTİP_KARAR: [Verilen GTİP kodu ve fasıl açıklaması. "
        f"Başvurucunun talep ettiği farklı bir GTİP varsa 'Talep edilen: XXXX.XX' şeklinde de belirt]\n"
        f"TEKNİK_GEREKÇE: [Sınıflandırma kararının teknik gerekçesi, 2-3 cümle]"
    )

    try:
        response = call_claude(prompt)
    except Exception as e:
        if logger:
            logger.warning(f"CBP özet hatası ({ruling_number}): {e}")
        return {
            "esya_tanimi":    subject,
            "gtip_karar":     tariffs,
            "teknik_gerekce": "(Özet üretilemedi)",
        }

    result = {"esya_tanimi": "", "gtip_karar": "", "teknik_gerekce": ""}
    for line in response.splitlines():
        if line.startswith("EŞYA_TANIMI:"):
            result["esya_tanimi"] = line[12:].strip()
        elif line.startswith("GTİP_KARAR:"):
            result["gtip_karar"] = line[11:].strip()
        elif line.startswith("TEKNİK_GEREKÇE:"):
            result["teknik_gerekce"] = line[15:].strip()

    # Herhangi bir alan boş kaldıysa ham değerle doldur
    if not result["esya_tanimi"]:
        result["esya_tanimi"] = subject
    if not result["gtip_karar"]:
        result["gtip_karar"] = tariffs

    return result


# ── Google Translate ──────────────────────────────────────────────────────────

def translate_google(text: str, logger=None) -> str:
    if not text or not text.strip():
        return ""
    try:
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source="en", target="tr")
        chunks = [text[i : i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]
        parts = []
        for chunk in chunks:
            parts.append(translator.translate(chunk))
            time.sleep(0.3)
        return " ".join(parts)
    except Exception as e:
        if logger:
            logger.warning(f"Google Translate hatası: {e}")
        return text
