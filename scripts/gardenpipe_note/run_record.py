"""What every measured run records about itself, so that a contaminated run can be seen afterwards."""

import datetime
import os
import resource
import time


def _busy_seconds():
    """CPU seconds the whole machine has spent on anything but idling, from /proc/stat."""
    user, nice, system, idle, iowait, irq, softirq, steal = map(int, open("/proc/stat").readline().split()[1:9])
    return (user + nice + system + irq + softirq + steal) / os.sysconf("SC_CLK_TCK")


def _settings():
    """The environment that changes how Polars reads and allocates. Polars itself writes _RJEM_MALLOC_CONF on import."""
    return {k: v for k, v in sorted(os.environ.items()) if k.startswith(("POLARS_", "_RJEM_"))}


class Stopwatch:
    """Start after the imports. other_cpu_seconds is CPU used by every other process during the run."""

    def __init__(self):
        self.started_at = datetime.datetime.now().isoformat(timespec="seconds")
        self.wall = time.perf_counter()
        self.busy = _busy_seconds()
        self.own = sum(os.times()[:2])

    def record(self):
        own = sum(os.times()[:2]) - self.own
        return dict(
            started_at=self.started_at,
            seconds=time.perf_counter() - self.wall,
            other_cpu_seconds=round(_busy_seconds() - self.busy - own, 1),
            peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
            settings=_settings(),
        )
