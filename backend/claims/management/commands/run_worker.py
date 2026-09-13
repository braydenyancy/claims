"""The registration worker process. Same image as the API, different
command. Run more than one for throughput; SKIP LOCKED keeps them from
taking the same row."""

import signal
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.module_loading import import_string

from claims.clearinghouse import worker


class Command(BaseCommand):
    help = "Drain the clearinghouse registration outbox"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="process at most one row, then exit")

    def handle(self, *args, once=False, **options):
        gateway = import_string(settings.CLEARINGHOUSE["GATEWAY"])()
        stop = {"now": False}

        def _stop(signum, frame):
            stop["now"] = True

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

        self.stdout.write(f"worker: gateway={type(gateway).__name__} poll={settings.CLEARINGHOUSE['POLL_SECONDS']}s")
        while not stop["now"]:
            worked = worker.run_once(gateway)
            if once:
                return
            if not worked:
                time.sleep(settings.CLEARINGHOUSE["POLL_SECONDS"])
        self.stdout.write("worker: stopped")
