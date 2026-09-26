import logging
import os
from pathlib import Path

log = logging.getLogger("nvd-guard")


class Blocklist:
    """อ่านคำต้องห้ามจากไฟล์ข้อความ (หนึ่งบรรทัดต่อหนึ่งคำ/วลี, # = คอมเมนต์)

    รีโหลดอัตโนมัติเมื่อไฟล์ถูกแก้ ไม่ต้องรีสตาร์ต server
    จับแบบ "ข้อความมีคำนั้นอยู่" และไม่แยกตัวพิมพ์เล็กใหญ่
    """

    def __init__(self, path: str):
        self.path = Path(path)
        self._mtime: float | None = None
        self._terms: list[str] = []

    def _reload_if_changed(self) -> None:
        try:
            mtime = os.stat(self.path).st_mtime
        except OSError:
            if self._mtime is not None or not self._terms:
                log.warning("อ่าน blocklist ไม่ได้: %s (ถือว่าว่าง)", self.path)
            self._mtime, self._terms = None, []
            return
        if mtime == self._mtime:
            return
        lines = self.path.read_text(encoding="utf-8-sig").splitlines()
        self._terms = [
            ln.strip().casefold()
            for ln in lines
            if ln.strip() and not ln.strip().startswith("#")
        ]
        self._mtime = mtime
        log.info("โหลด blocklist %d คำ", len(self._terms))

    def matches(self, message: str) -> bool:
        self._reload_if_changed()
        text = message.casefold()
        return any(term in text for term in self._terms)
