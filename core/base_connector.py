"""
Tüm ülke connector'larının türediği abstract sınıf.

Yaşam döngüsü (orchestrator tarafından çağrılır):
    run(target_date)
        → fetch()          – ham kayıtları çek
        → deduplicate()    – state dosyasıyla karşılaştır, sadece yenileri döndür
        → build_report()   – .docx üret, path listesi döndür
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ConnectorResult:
    connector_id: str
    run_date: datetime
    records_fetched: int
    records_new: int
    output_paths: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    success: bool = True
    data: dict = field(default_factory=dict)   # birleşik rapor için işlenmiş veri


class BaseConnector(ABC):

    def __init__(self, config: dict, state_dir: Path, output_dir: Path):
        self.config = config
        self.state_dir = Path(state_dir)
        self.output_dir = Path(output_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._seen_ids: set[str] = self._load_seen_ids()

    # ── Alt sınıfların uygulaması zorunlu ──────────────────────────────────

    @property
    @abstractmethod
    def connector_id(self) -> str:
        """Benzersiz slug: 'eu_ebti', 'us_cbp', 'ca_cbsa'"""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """İnsan tarafından okunabilir isim: 'AB EBTI', 'ABD CBP'"""

    @abstractmethod
    def fetch(self, target_date: datetime) -> list[dict[str, Any]]:
        """
        target_date için ham kayıtları döndürür.
        Her kayıt en az bir benzersiz anahtar içermelidir (extract_id tarafından okunur).
        """

    @abstractmethod
    def build_report(
        self,
        records: list[dict[str, Any]],
        target_date: datetime,
    ) -> list[Path]:
        """
        Çevrilmiş/işlenmiş kayıtlardan .docx raporu üretir.
        Oluşturulan dosyaların path listesini döndürür.
        """

    # ── Base class tarafından sağlananlar (override edilebilir) ───────────

    def extract_id(self, record: dict[str, Any]) -> str:
        return str(record.get("id", ""))

    def deduplicate(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        new_records = [r for r in records if self.extract_id(r) not in self._seen_ids]
        for r in new_records:
            self._seen_ids.add(self.extract_id(r))
        if new_records:
            self._save_seen_ids()
        return new_records

    def run(self, target_date: datetime) -> ConnectorResult:
        errors: list[str] = []
        output_paths: list[Path] = []
        records_fetched = 0
        records_new = 0

        try:
            raw = self.fetch(target_date)
            records_fetched = len(raw)
            new = self.deduplicate(raw)
            records_new = len(new)
            if new:
                output_paths = self.build_report(new, target_date)
        except Exception as e:
            import traceback
            errors.append(traceback.format_exc())

        return ConnectorResult(
            connector_id=self.connector_id,
            run_date=target_date,
            records_fetched=records_fetched,
            records_new=records_new,
            output_paths=output_paths,
            errors=errors,
            success=len(errors) == 0,
            data=getattr(self, "_report_data", {}),   # build_report() tarafından doldurulur
        )

    # ── State dosyası yönetimi ─────────────────────────────────────────────

    def _seen_ids_path(self) -> Path:
        return self.state_dir / f"{self.connector_id}_seen.json"

    def _load_seen_ids(self) -> set[str]:
        p = self._seen_ids_path()
        if p.exists():
            try:
                return set(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                return set()
        return set()

    def _save_seen_ids(self) -> None:
        self._seen_ids_path().write_text(
            json.dumps(sorted(self._seen_ids), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
