#!/usr/bin/env python3
"""本机 → Slurm 集群投递 Rosetta 评价，结果同步回本地 work_dir。

用法（本机）::

    python scripts/rosetta_cluster_bridge.py \\
      --local-work-dir /path/to/round1/rescore/rosetta \\
      --job-name demo001 \\
      --wt .../inputs/WT.pdb \\
      --mutant .../inputs/H_*.pdb \\
      --antibody-chains H \\
      --antigen-chains A \\
      --n-jobs 64 --nstruct 1

依赖环境变量（或 .env）::

    ROSETTA_CLUSTER_HOST=cluster-cpu
    ROSETTA_CLUSTER_WORKDIR=/share/home/bj3212/boltz2_rosetta
    ROSETTA_CLUSTER_PARTITION=batch
    ROSETTA_CLUSTER_CPUS=64
    ROSETTA_CLUSTER_TIME=24:00:00
    ROSETTA_CLUSTER_CONDA_ENV=rosetta-eval
    ROSETTA_CLUSTER_POLL_SEC=30
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _run(cmd: list[str] | str, *, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    if isinstance(cmd, str):
        print(f"+ {cmd}", flush=True)
        return subprocess.run(cmd, shell=True, check=check, text=True, capture_output=capture)
    print("+ " + " ".join(shlex.quote(c) for c in cmd), flush=True)
    return subprocess.run(cmd, check=check, text=True, capture_output=capture)


def _ssh(host: str, remote_cmd: str, *, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    return _run(["ssh", "-o", "BatchMode=yes", host, remote_cmd], check=check, capture=capture)


def _rsync(src: str, dst: str) -> None:
    _run(["rsync", "-a", "--delete", src, dst], check=True)


def _write_sbatch(
    *,
    job_name: str,
    remote_job: Path,
    cpus: int,
    partition: str,
    time_limit: str,
    conda_env: str,
    antibody_chains: str,
    antigen_chains: str,
    n_jobs: int,
    nstruct: int,
    mutant_names: list[str],
) -> str:
    """生成在集群上执行的 sbatch 脚本内容。"""
    mut_args = " ".join(f'"$JOB_DIR/inputs/{name}"' for name in mutant_names)
    # 用官方 Rosetta CLI；集群一般没有 PyRosetta
    return f"""#!/bin/bash
#SBATCH -J ar_{job_name[:20]}
#SBATCH -p {partition}
#SBATCH -N 1
#SBATCH -c {cpus}
#SBATCH -t {time_limit}
#SBATCH -o {remote_job}/logs/%x-%j.out
#SBATCH -e {remote_job}/logs/%x-%j.err

set -euo pipefail
JOB_DIR="{remote_job}"
# jobs/<id> → boltz2_rosetta/；software 在同级 software/
ROOT="$(dirname "$(dirname "$JOB_DIR")")"
mkdir -p "$JOB_DIR/work" "$JOB_DIR/logs"
cd "$JOB_DIR"
rm -f DONE FAILED

source /usr/share/Modules/init/bash 2>/dev/null || true
module load rosetta/v3.14
export LD_LIBRARY_PATH=/share/app/rosetta/rosetta-3.14/source/build/external/release/linux/5.14/64/x86/gcc/11/default:${{LD_LIBRARY_PATH:-}}
export ROSETTA_BIN=/share/app/rosetta/rosetta-3.14/source/bin
export ROSETTA3_DB=/share/app/rosetta/rosetta-3.14/database

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/miniconda3/etc/profile.d/conda.sh"
elif [[ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/anaconda3/etc/profile.d/conda.sh"
fi
conda activate {conda_env}

python "$ROOT/software/rosetta_eval_runner.py" \\
  --work-dir "$JOB_DIR/work" \\
  --wt "$JOB_DIR/inputs/WT.pdb" \\
  --nstruct {nstruct} \\
  --n-jobs {n_jobs} \\
  --antibody-chains {shlex.quote(antibody_chains)} \\
  --antigen-chains {shlex.quote(antigen_chains)} \\
  --rosetta-bin "$ROSETTA_BIN" \\
  --mutant {mut_args}

if [[ -f "$JOB_DIR/work/scores.csv" ]]; then
  touch "$JOB_DIR/DONE"
else
  echo "scores.csv missing" > "$JOB_DIR/FAILED"
  exit 1
fi
"""


def submit_and_wait(
    *,
    local_work_dir: Path,
    job_name: str,
    wt: Path,
    mutants: list[Path],
    antibody_chains: str,
    antigen_chains: str,
    n_jobs: int,
    nstruct: int,
) -> Path:
    host = _env("ROSETTA_CLUSTER_HOST", "cluster-cpu")
    remote_root = Path(_env("ROSETTA_CLUSTER_WORKDIR", "/share/home/bj3212/boltz2_rosetta"))
    partition = _env("ROSETTA_CLUSTER_PARTITION", "batch")
    cpus = int(_env("ROSETTA_CLUSTER_CPUS", str(max(n_jobs, 1))) or n_jobs or 64)
    time_limit = _env("ROSETTA_CLUSTER_TIME", "24:00:00")
    conda_env = _env("ROSETTA_CLUSTER_CONDA_ENV", "rosetta-eval")
    poll_sec = int(_env("ROSETTA_CLUSTER_POLL_SEC", "30") or 30)
    timeout_sec = int(_env("ROSETTA_CLUSTER_TIMEOUT_SEC", str(36 * 3600)) or 36 * 3600)

    local_work_dir = local_work_dir.resolve()
    local_work_dir.mkdir(parents=True, exist_ok=True)
    local_inputs = local_work_dir / "inputs"
    local_inputs.mkdir(parents=True, exist_ok=True)

    # 保证 WT / mutant 都在 inputs/ 下（与本地 _run_rosetta 一致）
    wt_dest = local_inputs / "WT.pdb"
    if Path(wt).resolve() != wt_dest.resolve():
        import shutil

        shutil.copy2(wt, wt_dest)
    mut_dests: list[Path] = []
    for m in mutants:
        dest = local_inputs / f"{Path(m).stem}.pdb"
        if Path(m).resolve() != dest.resolve():
            import shutil

            shutil.copy2(m, dest)
        mut_dests.append(dest)

    remote_job = remote_root / "jobs" / job_name
    remote_software = remote_root / "software"
    runner_local = Path(__file__).resolve().parent / "rosetta_eval_runner.py"

    print(f"[cluster] host={host} remote_job={remote_job}", flush=True)
    _ssh(host, f"mkdir -p {shlex.quote(str(remote_job / 'inputs'))} {shlex.quote(str(remote_job / 'logs'))} {shlex.quote(str(remote_software))}")
    _rsync(str(runner_local), f"{host}:{remote_software}/rosetta_eval_runner.py")
    _rsync(str(local_inputs) + "/", f"{host}:{remote_job}/inputs/")

    sbatch_body = _write_sbatch(
        job_name=job_name,
        remote_job=remote_job,
        cpus=cpus,
        partition=partition,
        time_limit=time_limit,
        conda_env=conda_env,
        antibody_chains=antibody_chains,
        antigen_chains=antigen_chains,
        n_jobs=n_jobs if n_jobs > 0 else cpus,
        nstruct=nstruct,
        mutant_names=[p.name for p in mut_dests],
    )
    local_sbatch = local_work_dir / "cluster_run.sbatch"
    local_sbatch.write_text(sbatch_body, encoding="utf-8")
    _rsync(str(local_sbatch), f"{host}:{remote_job}/run.sbatch")

    # 清掉上次 DONE/FAILED
    _ssh(host, f"rm -f {shlex.quote(str(remote_job / 'DONE'))} {shlex.quote(str(remote_job / 'FAILED'))}")

    sub = _ssh(
        host,
        f"cd {shlex.quote(str(remote_job))} && sbatch run.sbatch",
        capture=True,
    )
    out = (sub.stdout or "").strip()
    print(out, flush=True)
    # Submitted batch job 12345
    slurm_id = out.split()[-1] if out else ""
    (local_work_dir / "cluster_job_id.txt").write_text(slurm_id + "\n", encoding="utf-8")

    t0 = time.time()
    while True:
        if time.time() - t0 > timeout_sec:
            raise TimeoutError(f"集群 Rosetta 超时 ({timeout_sec}s)，slurm_id={slurm_id}")
        st = _ssh(
            host,
            f"if [[ -f {shlex.quote(str(remote_job / 'DONE'))} ]]; then echo DONE; "
            f"elif [[ -f {shlex.quote(str(remote_job / 'FAILED'))} ]]; then echo FAILED; "
            f"elif squeue -j {shlex.quote(slurm_id)} -h 2>/dev/null | grep -q .; then echo RUNNING; "
            f"else echo UNKNOWN; fi",
            capture=True,
        )
        state = (st.stdout or "").strip().splitlines()[-1] if st.stdout else "UNKNOWN"
        print(f"[cluster] slurm={slurm_id} state={state} elapsed={int(time.time() - t0)}s", flush=True)
        if state == "DONE":
            break
        if state == "FAILED":
            log_tail = _ssh(
                host,
                f"ls -t {shlex.quote(str(remote_job / 'logs'))}/* 2>/dev/null | head -1 | xargs -r tail -n 80",
                check=False,
                capture=True,
            )
            raise RuntimeError(
                "集群 Rosetta 失败:\n" + ((log_tail.stdout or "") + (log_tail.stderr or ""))[-4000:]
            )
        if state == "UNKNOWN" and slurm_id:
            # 作业已从队列消失但无 DONE：再等一轮或判失败
            time.sleep(poll_sec)
            st2 = _ssh(
                host,
                f"if [[ -f {shlex.quote(str(remote_job / 'DONE'))} ]]; then echo DONE; "
                f"elif [[ -f {shlex.quote(str(remote_job / 'FAILED'))} ]]; then echo FAILED; "
                f"else echo GONE; fi",
                capture=True,
            )
            state2 = (st2.stdout or "").strip().splitlines()[-1]
            if state2 == "DONE":
                break
            if state2 == "FAILED":
                raise RuntimeError("集群 Rosetta 失败（FAILED）")
            raise RuntimeError(f"集群作业 {slurm_id} 已结束但未找到 DONE（state={state2}）")
        time.sleep(poll_sec)

    # 同步结果回本地 work_dir（覆盖 scores.csv 等）
    _rsync(f"{host}:{remote_job}/work/", str(local_work_dir) + "/")
    scores = local_work_dir / "scores.csv"
    if not scores.is_file():
        raise RuntimeError(f"同步后缺少 scores.csv: {scores}")
    print(f"[cluster] synced scores → {scores}", flush=True)
    return scores


def main() -> int:
    # 加载仓库 .env（若存在）
    root = Path(__file__).resolve().parents[1]
    env_file = root / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    p = argparse.ArgumentParser(description="Submit Rosetta eval to Slurm cluster")
    p.add_argument("--local-work-dir", required=True)
    p.add_argument("--job-name", required=True, help="集群 jobs/ 下的子目录名，建议用任务短 id")
    p.add_argument("--wt", required=True)
    p.add_argument("--mutant", nargs="*", default=[])
    p.add_argument("--antibody-chains", default="H")
    p.add_argument("--antigen-chains", default="A")
    p.add_argument("--n-jobs", type=int, default=64)
    p.add_argument("--nstruct", type=int, default=1)
    args = p.parse_args()

    mutants = [Path(m) for m in args.mutant]
    if not mutants:
        # 自动收集 local work_dir/inputs 下非 WT 的 pdb
        inp = Path(args.local_work_dir) / "inputs"
        mutants = sorted(x for x in inp.glob("*.pdb") if x.stem != "WT")

    submit_and_wait(
        local_work_dir=Path(args.local_work_dir),
        job_name=args.job_name,
        wt=Path(args.wt),
        mutants=mutants,
        antibody_chains=args.antibody_chains,
        antigen_chains=args.antigen_chains,
        n_jobs=args.n_jobs,
        nstruct=args.nstruct,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
