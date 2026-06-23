"""
Orchestrator — tüm connector'ları sırayla çalıştırır, birleşik rapor üretir.
"""

import importlib
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from core.base_connector import BaseConnector, ConnectorResult
from core.logger import get_logger


# Ülke renk paleti (birleşik rapor kapak kartları)
COUNTRY_COLORS = {
    "eu_ebti":  {"color": "003399", "label_color": "2E75B6"},
    "us_cbp":   {"color": "B22234", "label_color": "C0392B"},
    "ca_cbsa":  {"color": "FF0000", "label_color": "C0392B"},
}


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


def _load_connectors(config, state_dir, output_base, logger) -> list[BaseConnector]:
    connectors = []
    for connector_id, connector_cfg in config.get("connectors", {}).items():
        if not connector_cfg.get("enabled", False):
            continue
        try:
            module     = importlib.import_module(f"connectors.{connector_id}")
            class_name = "".join(p.capitalize() for p in connector_id.split("_")) + "Connector"
            cls        = getattr(module, class_name)
            output_dir = output_base / connector_id.upper()
            if "claude_batch_size" not in connector_cfg and "claude_batch_size" in config:
                connector_cfg = {**connector_cfg, "claude_batch_size": config["claude_batch_size"]}
            connectors.append(cls(config=connector_cfg, state_dir=state_dir, output_dir=output_dir))
            logger.info(f"  Connector yüklendi: {connectors[-1].display_name}")
        except Exception as e:
            logger.error(f"  Connector yüklenemedi ({connector_id}): {e}")
    return connectors


# ── Cached report data yükleyici ─────────────────────────────────────────────

def _load_cached_report_data(connector, target_date: datetime, output_base: Path) -> dict:
    """
    result.data boş olduğunda (records_new=0 → build_report çağrılmadı),
    connector'ın output dizininde kayıtlı _report_data.json'ı bulup döndürür.
    """
    date_str = target_date.strftime("%Y-%m-%d")
    base_dir = output_base / connector.connector_id.upper()

    # 1. Hedef tarih dizini
    candidate = base_dir / date_str / "_report_data.json"
    if candidate.exists():
        try:
            return json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            pass

    # 2. En son tarih dizini (fallback)
    try:
        date_dirs = sorted(
            [d for d in base_dir.iterdir() if d.is_dir() and (d / "_report_data.json").exists()],
            reverse=True,
        )
        if date_dirs:
            return json.loads((date_dirs[0] / "_report_data.json").read_text(encoding="utf-8"))
    except Exception:
        pass

    return {}


# ── Birleşik rapor ────────────────────────────────────────────────────────────

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

    date_str    = target_date.strftime("%Y-%m-%d")
    output_name = unified_cfg.get("output_name", "BTI_Unified_{date}.docx").replace("{date}", date_str)
    docx_path   = output_base / output_name

    connector_map = {c.connector_id: c for c in connectors}
    result_map    = {r.connector_id: r for r in results}

    # ── Tüm connector'lar için data yükle (cache fallback ile) ─────────────
    data_map:  dict[str, dict] = {}
    count_map: dict[str, int]  = {}
    for cid, conn in connector_map.items():
        res = result_map.get(cid)
        d = res.data if (res and res.data) else {}
        if not d:
            d = _load_cached_report_data(conn, target_date, output_base)
            if d:
                logger.info(f"  {conn.display_name}: cached _report_data.json yüklendi")
        data_map[cid]  = d
        count_map[cid] = len(d.get("records", []))

    # ── Kapak için ülke kartı listesi ────────────────────────────────────────
    country_cards = []
    for cid, conn in connector_map.items():
        colors = COUNTRY_COLORS.get(cid, {"color": "444444", "label_color": "666666"})
        country_cards.append({
            "name":        conn.display_name,
            "count":       count_map.get(cid, 0),
            "color":       colors["color"],
            "label_color": colors["label_color"],
        })

    # ── Node.js'e gönderilecek birleşik JSON ─────────────────────────────────
    unified_data: dict = {
        "date":      date_str,
        "countries": country_cards,
    }
    if "eu_ebti" in data_map and data_map["eu_ebti"]:
        unified_data["eu_ebti"] = data_map["eu_ebti"]
    if "us_cbp" in data_map and data_map["us_cbp"]:
        cbp = dict(data_map["us_cbp"])
        cbp.setdefault("date_str", date_str)
        unified_data["us_cbp"] = cbp
    if "ca_cbsa" in data_map and data_map["ca_cbsa"]:
        cbsa = dict(data_map["ca_cbsa"])
        cbsa.setdefault("date_str", date_str)
        unified_data["ca_cbsa"] = cbsa

    # ── Geçici JSON dosyasına yaz, Node.js'i çalıştır ───────────────────────
    tmp_json = output_base / f"_unified_tmp_{date_str}.json"
    tmp_json.write_text(
        json.dumps(unified_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    unified_script = Path(
        config.get("connectors", {})
             .get("eu_ebti", {})
             .get("docx_script", "~/bti_system/assets/build_docx.js")
    ).expanduser().parent / "build_unified_docx.js"

    try:
        result = subprocess.run(
            ["node", str(unified_script), str(tmp_json), str(docx_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            logger.error(f"Birleşik rapor Node.js hatası:\n{result.stderr[:800]}")
            return None
    finally:
        tmp_json.unlink(missing_ok=True)

    logger.info(f"Birleşik rapor kaydedildi: {docx_path}")
    return docx_path


# ── Ana Orchestrator ──────────────────────────────────────────────────────────

class Orchestrator:

    def __init__(self, config_path: Path):
        self.config_path = Path(config_path)
        self.config      = _load_config(self.config_path)

        log_file    = self.config.get("log_file")
        self.logger = get_logger("bti_system", log_file=Path(log_file) if log_file else None)

        self.output_base = Path(self.config["output_base"])
        self.state_dir   = Path(self.config["state_dir"])
        self.output_base.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        bti_root = str(self.config_path.parent)
        if bti_root not in sys.path:
            sys.path.insert(0, bti_root)

        self.connectors = _load_connectors(
            self.config, self.state_dir, self.output_base, self.logger
        )

    def run(self, target_date: datetime | None = None) -> list[ConnectorResult]:
        if target_date is None:
            target_date = datetime.now() - timedelta(days=1)

        self.logger.info("=" * 60)
        self.logger.info(f"BTI Sistemi | {target_date.strftime('%Y-%m-%d')}")
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
                        f"{result.records_new} yeni → {[p.name for p in result.output_paths]}"
                    )
                else:
                    self.logger.error(f"  {connector.display_name} HATA:\n{''.join(result.errors)}")
            except Exception as e:
                import traceback
                self.logger.critical(f"  {connector.display_name} beklenmedik hata: {traceback.format_exc()}")
                results.append(ConnectorResult(
                    connector_id=connector.connector_id,
                    run_date=target_date,
                    records_fetched=0, records_new=0,
                    errors=[str(e)], success=False,
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
