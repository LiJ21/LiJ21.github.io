#!/bin/bash
# Print the machine and software behind a run. From a GardenPipe checkout: bash record_environment.sh
echo "recorded $(date -Is)"
uname -sr
. /etc/os-release && echo "$PRETTY_NAME"
lscpu | grep -E "Model name|^CPU\(s\):|Thread\(s\) per core|Core\(s\) per socket"
grep -E "MemTotal|SwapTotal" /proc/meminfo
echo "cgroup filesystem: $(stat -fc %T /sys/fs/cgroup)"
echo "user cgroup controllers: $(cat "/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/cgroup.controllers")"
systemd --version | head -1
echo "vm.overcommit_memory=$(cat /proc/sys/vm/overcommit_memory) vm.swappiness=$(cat /proc/sys/vm/swappiness)"
echo "thread and allocator settings: $(env | grep -E '^(POLARS_|OMP_|MKL_|OPENBLAS_|MALLOC_|RAYON_)' | tr '\n' ' ')"
.venv/bin/python --version
uv --version
echo "GardenPipe $(git rev-parse HEAD)"
echo "changes against that commit: $(git status --short | tr '\n' ' ')"
uv pip freeze
