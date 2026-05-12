#!/usr/bin/env python3
"""
BTI Günlük Sistem — Giriş Noktası

Kullanım:
  python main.py                           # dünün verisi, tüm connectorlar
  python main.py --date 07-05-2026        # belirli tarih
  python main.py --connector us_cbp       # sadece bir connector
  python main.py --list                   # aktif connectorları listele
  python main.py --config ./config.yaml  # özel config dosyası
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="BTI Günlük Veri Çekme ve Raporlama Sistemi",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--config",
        default=str(Path(__file__).parent / "config.yaml"),
        help="Konfigürasyon dosyası yolu (varsayılan: config.yaml)",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Hedef tarih DD-MM-YYYY formatında (varsayılan: dün)",
    )
    parser.add_argument(
        "--connector",
        default=None,
        help="Sadece belirtilen connector'ı çalıştır (örn: us_cbp)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Aktif connector'ları listele ve çık",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"HATA: Config dosyası bulunamadı: {config_path}", file=sys.stderr)
        sys.exit(1)

    # sys.path'e bti_system kök dizinini ekle
    bti_root = str(Path(__file__).parent)
    if bti_root not in sys.path:
        sys.path.insert(0, bti_root)

    from core.orchestrator import Orchestrator, _load_config

    if args.list:
        cfg = _load_config(config_path)
        print("Aktif connector'lar:")
        for cid, ccfg in cfg.get("connectors", {}).items():
            if ccfg.get("enabled", False):
                print(f"  [{cid}] {ccfg.get('display_name', cid)}")
        sys.exit(0)

    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%d-%m-%Y")
        except ValueError:
            print(f"HATA: Geçersiz tarih formatı: {args.date} (beklenen: DD-MM-YYYY)", file=sys.stderr)
            sys.exit(1)

    if args.connector:
        # Tek connector modunu aktifleştir: config'de diğerlerini devre dışı bırak
        import yaml
        from core.orchestrator import _load_config
        cfg = _load_config(config_path)
        for cid in cfg.get("connectors", {}):
            cfg["connectors"][cid]["enabled"] = (cid == args.connector)
        if args.connector not in cfg.get("connectors", {}):
            print(f"HATA: Bilinmeyen connector: {args.connector}", file=sys.stderr)
            print(f"Mevcut connector'lar: {list(cfg.get('connectors', {}).keys())}")
            sys.exit(1)
        # Geçici config dosyası yaz
        import tempfile, os
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        )
        yaml.dump(cfg, tmp, allow_unicode=True)
        tmp.close()
        config_path = Path(tmp.name)
        try:
            orch = Orchestrator(config_path)
            results = orch.run(target_date)
        finally:
            os.unlink(config_path)
    else:
        orch = Orchestrator(config_path)
        results = orch.run(target_date)

    # Çıkış kodu: herhangi bir connector başarısızsa 1
    if any(not r.success for r in results):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
