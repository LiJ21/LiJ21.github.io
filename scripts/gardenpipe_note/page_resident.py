"""python3 resident.py DIR N: MiB of the first N Parquet files in the page cache. Reads no data."""
import ctypes, mmap, os, sys
from pathlib import Path
PAGE = os.sysconf("SC_PAGE_SIZE")
libc = ctypes.CDLL("libc.so.6", use_errno=True)
libc.mmap.restype = ctypes.c_void_p
libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_long]
libc.mincore.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
held = 0
for path in sorted(Path(sys.argv[1]).glob("*.parquet"))[: int(sys.argv[2])]:
    fd = os.open(path, os.O_RDONLY)
    size = os.fstat(fd).st_size
    pages = (size + PAGE - 1) // PAGE
    present = (ctypes.c_ubyte * pages)()
    where = libc.mmap(None, size, mmap.PROT_READ, mmap.MAP_SHARED, fd, 0)
    libc.mincore(where, size, present)
    libc.munmap(where, size)
    held += min(size, sum(f & 1 for f in present) * PAGE)
    os.close(fd)
print(f"{held / 2**20:.0f}")
