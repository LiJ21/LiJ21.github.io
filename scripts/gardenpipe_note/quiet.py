"""Keep other work on the machine out of the measurements.

python3 quiet.py wait                        returns once the machine has been idle for 30 seconds
python3 quiet.py keep LAST OUT REJECTED      files the record in LAST under OUT if the machine stayed idle
                                             during that run, or under REJECTED if not, and exits 1 then

QUIET_FREE_MIB and QUIET_CPUS change what counts as idle, for when another program holds memory or ticks over.
"""

import json
import os
import sys
import time
from pathlib import Path

IDLE_CPUS = float(os.environ.get("QUIET_CPUS", 1.0))
FREE_MIB = int(os.environ.get("QUIET_FREE_MIB", 12_000))
TICKS = 100


def busy_ticks():
    user, nice, system, idle, iowait, irq, softirq, steal = map(int, open("/proc/stat").readline().split()[1:9])
    return user + nice + system + irq + softirq + steal


def available_mib():
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 1024


def wait():
    began, quiet, told = time.time(), 0, False
    while quiet < 6:
        before = busy_ticks()
        time.sleep(5)
        cpus = (busy_ticks() - before) / TICKS / 5
        quiet = quiet + 1 if cpus < IDLE_CPUS and available_mib() > FREE_MIB else 0
        if not quiet and not told:
            print(f"waiting for an idle machine: {cpus:.1f} CPUs busy, {available_mib():,.0f} MiB available", flush=True)
            told = True
    if told:
        print(f"idle after {time.time() - began:,.0f} s", flush=True)


def keep(last, out, rejected):
    if not last.exists():
        print(f"no record in {last}")
        return 1
    line = last.read_text().strip()
    record = json.loads(line)
    cpus = record["other_cpu_seconds"] / record["seconds"]
    clean = cpus <= IDLE_CPUS
    with (out if clean else rejected).open("a") as f:
        f.write(line + "\n")
    if not clean:
        print(f"rejected: {cpus:.1f} other CPUs busy during the run", flush=True)
    return 0 if clean else 1


if sys.argv[1] == "wait":
    wait()
else:
    sys.exit(keep(*map(Path, sys.argv[2:5])))
