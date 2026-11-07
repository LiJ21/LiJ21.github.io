"""Put dataset files in a known page-cache state: python3 page_cache.py cold|warm DIR

cold asks the kernel to drop the files' cached pages, which needs no root for files you can open.
warm reads them. Prints how much of the data is resident afterwards, measured with mincore.
"""

import ctypes
import mmap
import os
import sys
from pathlib import Path

PAGE = os.sysconf("SC_PAGE_SIZE")
libc = ctypes.CDLL("libc.so.6", use_errno=True)
libc.mmap.restype = ctypes.c_void_p
libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_long]
libc.mincore.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]


def resident_bytes(fd, size):
    pages = (size + PAGE - 1) // PAGE
    present = (ctypes.c_ubyte * pages)()
    where = libc.mmap(None, size, mmap.PROT_READ, mmap.MAP_SHARED, fd, 0)
    libc.mincore(where, size, present)
    libc.munmap(where, size)
    return min(size, sum(flag & 1 for flag in present) * PAGE)


state, directory = sys.argv[1], Path(sys.argv[2])
assert state in ("cold", "warm"), state
paths = sorted(directory.glob("*.parquet"))
for path in paths:
    fd = os.open(path, os.O_RDONLY)
    if state == "cold":
        os.fsync(fd)
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
    else:
        while os.read(fd, 1 << 24):
            pass
    os.close(fd)

total = held = 0
for path in paths:
    fd = os.open(path, os.O_RDONLY)
    size = os.fstat(fd).st_size
    total += size
    held += resident_bytes(fd, size)
    os.close(fd)
print(f"{directory.name}: {state}, {held / 2**20:,.0f} of {total / 2**20:,.0f} MiB resident")
