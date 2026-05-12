"""
Orchestrator — tüm connector'ları sırayla çalıştırır, birleşik rapor üretir.
"""

import importlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

from core.base_connector import BaseConnector, ConnectorResult
from core.logger import get_logger
from core.report_builder import make_doc, add_ruling_to_doc, add_no_results_notice


def _load_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    def expand(val):
        if isinstance(val, str):
            return str(Path(val).expanduser()) if val.startswith("~") else val
        if isinstance(val, dict):
            return {k: expand(v) for k, v in val.items()}
        return val

    return expand(cfg)


def _load_connectors(
    config: dict,
    state_dir: Path,
    output_base: Path,
    logger,
) -> list[BaseConnector]:
    connectors = []
    for connector_id, connector_cfg in config.get("connectors", {}).items():
        if not connector_cfg.get("enabled", False):
            continue
        try:
            module = importlib.import_module(f"connectors.{connector_id}")
            class_name = "".join(p.capitalize() for p in connector_id.split("_")) + "Connector"
            cls = getattr(module, class_name)
            output_dir = output_base / connector_id.upper()
            # claude_batch_size'ı connector config'e aktar
            if "claude_batch_size" not in connector_cfg and "claude_batch_size" in config:
                connector_cfg = {**connector_cfg, "claude_batch_size": config["claude_batch_size"]}
            connector = cls(config=connector_cfg, state_dir=state_dir, output_dir=output_dir)
            connectors.append(connector)
            logger.info(f"  Connector yüklendi: {connector.display_name}")
        except Exception as e:
            logger.error(f"  Connector yüklenemedi ({connector_id}): {e}")
    return connectors


def _build_unified_report(
    results: list[ConnectorResult],
    connectors: list[BaseConnector],
    config: dict,
    target_date: datetime,
    output_base: Path,
    logger,
) -> Path | None:
    unified_cfg = config.get("unified_report", {})
    if not unified_cfg.get("enabled", False):
        return None

    date_str = target_date.strftime("%Y-%m-%d")
    output_name = unified_cfg.get("output_name", "BTI_Unified_{date}.docx").replace("{date}", date_str)
    docx_path = output_base / output_name

    # EU EBTI için ayrı Node.js yolu var; bu connector'dan raw records'u al
    # Diğerleri için python-docx yolu
    connector_map = {c.connector_id: c for c in connectors}

    doc = make_doc(
        "Günlük BTI Birleşik Raporu",
        f"AB EBTI  |  ABD CBP  |  Kanada CBSA  |  {date_str}",
    )

    # Özet tablosu
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    summary_p = doc.add_paragraph()
    summary_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sr = summary_p.add_run("Özet")
    sr.bold = True
    sr.font.size = Pt(13)
    sr.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)

    from core.report_builder import add_info_table
    summary_rows = []
    for result in results:
        conn = connector_map.get(result.connector_id)
        name = conn.display_name if conn else result.connector_id
        status = "✓" if result.success else "✗ HATA"
        summary_rows.append((name, f"{result.records_new} yeni karar  |  {status}"))

    add_info_table(doc, summary_rows)
    doc.add_paragraph()

    total_written = 0

    for result in results:
        if not result.success or result.records_new == 0:
            continue

        conn = connector_map.get(result.connector_id)
        if conn is None:
            continue

        # Bölüm başlığı
        sec_p = doc.add_paragraph()
        sec_r = sec_p.add_run(f"─── {conn.display_name} ───")
        sec_r.bold = True
        sec_r.font.size = Pt(15)
        sec_r.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)
        doc.add_paragraph()

        if result.connector_id == "eu_ebti":
            # AB EBTI: output_paths[0] .docx'i zaten üretmiş
            # Unified raporda "AB EBTI ayrı rapor üretildi" notu ekle
            if result.output_paths:
                note_p = doc.add_paragraph()
                note_r = note_p.add_run(
                    f"AB EBTI detaylı raporu ayrı olarak kaydedildi:\n{result.output_paths[0]}"
                )
                note_r.italic = True
                note_r.font.size = Pt(10)
                note_r.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
                doc.add_paragraph("─" * 80)
                doc.add_paragraph()
                total_written += result.records_new
        elif result.connector_id == "us_cbp":
            cbp_conn = conn
            if hasattr(cbp_conn, "get_processed_records"):
                # Mevcut records: build_report sırasında dedup sonrası işlenen kayıtlar
                # Basitleştirilmiş: output .docx'teki içeriği referans ver
                if result.output_paths:
                    note_p = doc.add_paragraph()
                    note_r = note_p.add_run(
                        f"ABD CBP detaylı raporu ayrı olarak kaydedildi:\n{result.output_paths[0]}"
                    )
                    note_r.italic = True
                    note_r.font.size = Pt(10)
                    note_r.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
                    doc.add_paragraph("─" * 80)
                    doc.add_paragraph()
                    total_written += result.records_new
        elif result.connector_id == "ca_cbsa":
            if result.output_paths:
                note_p = doc.add_paragraph()
                note_r = note_p.add_run(
                    f"Kanada CBSA detaylı raporu ayrı olarak kaydedildi:\n{result.output_paths[0]}"
                )
                note_r.italic = True
                note_r.font.size = Pt(10)
                note_r.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
                doc.add_paragraph("─" * 80)
                doc.add_paragraph()
                total_written += result.records_new

    if total_written == 0:
        add_no_results_notice(doc)

    doc.save(str(docx_path))
    logger.info(f"Birleşik rapor kaydedildi: {docx_path}")
    return docx_path


class Orchestrator:

    def __init__(self, config_path: Path):
        self.config_path = Path(config_path)
        self.config = _load_config(self.config_path)

        log_file = self.config.get("log_file")
        self.logger = get_logger("bti_system", log_file=Path(log_file) if log_file else None)

        self.output_base = Path(self.config["output_base"])
        self.state_dir = Path(self.config["state_dir"])
        self.output_base.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # sys.path'e bti_system kök dizinini ekle (connector importları için)
        bti_root = str(self.config_path.parent)
        if bti_root not in sys.path:
            sys.path.insert(0, bti_root)

        self.connectors = _load_connectors(
            self.config, self.state_dir, self.output_base, self.logger
        )

    def run(self, target_date: datetime | None = None) -> list[ConnectorResult]:
        from datetime import timedelta
        if target_date is None:
            target_date = datetime.now() - timedelta(days=1)

        self.logger.info("=" * 60)
        self.logger.info(f"BTI Sistemi başlatıldı | Hedef tarih: {target_date.strftime('%Y-%m-%d')}")
        self.logger.info("=" * 60)

        results: list[ConnectorResult] = []

        for connector in self.connectors:
            self.logger.info(f"── {connector.display_name} ──────────────")
            try:
                result = connector.run(target_date)
                results.append(result)
                if result.success:
                    self.logger.info(
                        f"  {connector.display_name}: {result.records_fetched} çekildi, "
                        f"{result.records_new} yeni, "
                        f"dosyalar: {[p.name for p in result.output_paths]}"
                    )
                else:
                    self.logger.error(
                        f"  {connector.display_name} HATA:\n{''.join(result.errors)}"
                    )
            except Exception as e:
                import traceback
                self.logger.critical(
                    f"  {connector.display_name} beklenmedik hata: {traceback.format_exc()}"
                )
                results.append(ConnectorResult(
                    connector_id=connector.connector_id,
                    run_date=target_date,
                    records_fetched=0,
                    records_new=0,
                    errors=[str(e)],
                    success=False,
                ))

        self._print_summary(results)

        unified_path = _build_unified_report(
            results, self.connectors, self.config, target_date, self.output_base, self.logger
        )
        if unified_path:
            self.logger.info(f"Birleşik rapor: {unified_path}")

        self.logger.info("=" * 60)
        return results

    def _print_summary(self, results: list[ConnectorResult]) -> None:
        self.logger.info("")
        self.logger.info("┌─── ÖZET ───────────────────────────────────────┐")
        for r in results:
            status = "✓ BAŞARILI" if r.success else "✗ HATA"
            self.logger.info(
                f"│  {r.connector_id:<12} {status:<12} "
                f"çekilen:{r.records_fetched:>4}  yeni:{r.records_new:>4}  │"
            )
        self.logger.info("└────────────────────────────────────────────────┘")
        self.logger.info("")
