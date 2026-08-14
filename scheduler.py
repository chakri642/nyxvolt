import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from config import SCHEDULE_HOURS

log = logging.getLogger(__name__)


def start(pipeline_fn):
    scheduler = BlockingScheduler(timezone="UTC")
    hours_str = ",".join(str(h) for h in SCHEDULE_HOURS)

    scheduler.add_job(
        lambda: pipeline_fn(post=True),
        trigger=CronTrigger(hour=hours_str, minute=0),
        id="nyxvolt_post",
        name="Nyxvolt auto-post",
        misfire_grace_time=600,
    )

    log.info(f"Scheduler started — posting at UTC hours: {SCHEDULE_HOURS}")
    print(f"Scheduler running. Posts at UTC {SCHEDULE_HOURS}. Press Ctrl+C to stop.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")
