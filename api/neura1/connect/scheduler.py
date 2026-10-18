"""Sync from the ERP on a schedule (NEURA1_ERP_SYNC_MINUTES), in a background thread."""

import logging
import threading
import time

from neura1.config import settings

log = logging.getLogger("neura1.connect")


def start(get_graph) -> None:
    def loop():
        from neura1.connect import sync
        while True:
            time.sleep(max(settings.erp_sync_minutes, 1) * 60)
            try:
                report = sync.run(get_graph(), by="schedule")
                log.info("ERP sync: %s", report.get("message") or report.get("error"))
            except Exception:  # keep the schedule alive
                log.exception("ERP sync failed")

    threading.Thread(target=loop, name="erp-sync", daemon=True).start()
