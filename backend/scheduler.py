from __future__ import annotations

import os
from typing import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger


class AutomationScheduler:
    def __init__(
        self,
        scrape_job: Callable[[], Awaitable[None]],
        backup_job: Callable[[], Awaitable[None]],
        rss_job: Callable[[], Awaitable[None]] | None = None,
        weekly_report_job: Callable[[], Awaitable[None]] | None = None,
        security_job: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.scrape_job = scrape_job
        self.backup_job = backup_job
        self.rss_job = rss_job
        self.weekly_report_job = weekly_report_job
        self.security_job = security_job
        self.scheduler = AsyncIOScheduler(timezone=os.getenv("SCHEDULER_TIMEZONE", "UTC"))

    def start(self) -> None:
        if os.getenv("AUTOMATION_ENABLED", "true").lower() != "true":
            return
        scrape_minutes = int(os.getenv("SCRAPE_INTERVAL_MINUTES", "60"))
        backup_hours = int(os.getenv("BACKUP_INTERVAL_HOURS", "24"))
        rss_minutes = int(os.getenv("RSS_INTERVAL_MINUTES", "30"))
        security_minutes = int(os.getenv("SECURITY_INTERVAL_MINUTES", "5"))

        if scrape_minutes > 0:
            self.scheduler.add_job(self.scrape_job, IntervalTrigger(minutes=scrape_minutes), id="scheduled_scrape", replace_existing=True, max_instances=1, coalesce=True, misfire_grace_time=300)
        if backup_hours > 0:
            self.scheduler.add_job(self.backup_job, IntervalTrigger(hours=backup_hours), id="scheduled_backup", replace_existing=True, max_instances=1, coalesce=True, misfire_grace_time=900)
        if self.rss_job and rss_minutes > 0:
            self.scheduler.add_job(self.rss_job, IntervalTrigger(minutes=rss_minutes), id="rss_sync", replace_existing=True, max_instances=1, coalesce=True, misfire_grace_time=300)
        if self.security_job and security_minutes > 0:
            self.scheduler.add_job(self.security_job, IntervalTrigger(minutes=security_minutes), id="security_monitor", replace_existing=True, max_instances=1, coalesce=True, misfire_grace_time=300)
        if self.weekly_report_job:
            self.scheduler.add_job(
                self.weekly_report_job,
                CronTrigger(day_of_week=os.getenv("WEEKLY_REPORT_DAY", "mon"), hour=int(os.getenv("WEEKLY_REPORT_HOUR", "9")), minute=0),
                id="weekly_report",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=3600,
            )
        self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def status(self) -> dict:
        return {
            "enabled": self.scheduler.running,
            "timezone": os.getenv("SCHEDULER_TIMEZONE", "UTC"),
            "jobs": [
                {"id": job.id, "next_run": job.next_run_time.isoformat() if job.next_run_time else None}
                for job in self.scheduler.get_jobs()
            ] if self.scheduler.running else [],
        }
