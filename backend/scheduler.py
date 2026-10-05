from __future__ import annotations

import asyncio
import os
from typing import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger


class AutomationScheduler:
    def __init__(
        self,
        scrape_job: Callable[[], Awaitable[None]],
        backup_job: Callable[[], Awaitable[None]],
    ) -> None:
        self.scrape_job = scrape_job
        self.backup_job = backup_job
        self.scheduler = AsyncIOScheduler(timezone=os.getenv("SCHEDULER_TIMEZONE", "UTC"))

    def start(self) -> None:
        if os.getenv("AUTOMATION_ENABLED", "true").lower() != "true":
            return

        scrape_minutes = int(os.getenv("SCRAPE_INTERVAL_MINUTES", "60"))
        backup_hours = int(os.getenv("BACKUP_INTERVAL_HOURS", "24"))

        if scrape_minutes > 0:
            self.scheduler.add_job(
                self.scrape_job,
                IntervalTrigger(minutes=scrape_minutes),
                id="scheduled_scrape",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=300,
            )

        if backup_hours > 0:
            self.scheduler.add_job(
                self.backup_job,
                IntervalTrigger(hours=backup_hours),
                id="scheduled_backup",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=900,
            )

        self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def status(self) -> dict:
        jobs = []
        if self.scheduler.running:
            for job in self.scheduler.get_jobs():
                jobs.append({
                    "id": job.id,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                })
        return {
            "enabled": self.scheduler.running,
            "jobs": jobs,
        }
