"""Run a command and sample its memory at 5 Hz. usage: sample_rss.py out.csv cmd...

RSS is split into anonymous pages, which must stay in RAM, and file-backed pages, which the
kernel can drop under pressure. The split matters for anything that memory-maps a cache.
"""

import subprocess, sys, time

FIELDS = ("VmRSS", "RssAnon", "RssFile")
out, cmd = sys.argv[1], sys.argv[2:]
p = subprocess.Popen(cmd)
t0 = time.time()
with open(out, "w") as f:
    f.write("t,rss_mib,anon_mib,file_mib\n")
    while p.poll() is None:
        try:
            now = {}
            for line in open(f"/proc/{p.pid}/status"):
                key = line.split(":")[0]
                if key in FIELDS:
                    now[key] = int(line.split()[1]) / 1024
            if len(now) == len(FIELDS):
                row = ",".join(f"{now[k]:.1f}" for k in FIELDS)
                f.write(f"{time.time()-t0:.2f},{row}\n")
                f.flush()
        except OSError:
            pass
        time.sleep(0.2)
sys.exit(p.returncode)
