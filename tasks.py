"""SentinelLake task runner: works the same on Windows, macOS and Linux (no `make` needed).

Laptop mode (no Docker):
  python tasks.py doctor      check Python, Java and (on Windows) winutils
  python tasks.py test        run the test suite
  python tasks.py demo        replay -> stream -> evaluate, then start the dashboard
  python tasks.py replay      simulate 6 hours of API traffic into data/landing
  python tasks.py stream      Spark streaming job over data/landing
  python tasks.py evaluate    score the detector against the injected failures
  python tasks.py serve       dashboard on http://localhost:8000
  python tasks.py mapreduce   the 3 MapReduce jobs with the local runner
  python tasks.py hive        the HiveQL reports, run on Spark SQL
  python tasks.py bench       storage / query / partition / combiner benchmarks
  python tasks.py charts      redraw docs/img from results/

Cluster mode (Docker Desktop must be running):
  python tasks.py up | batch-up | logs | down
  python tasks.py cluster-mapreduce [YYYY-MM-DD]
  python tasks.py cluster-hive
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
WINDOWS = platform.system() == "Windows"


def tool_env() -> dict:
    """Environment for child processes: JAVA_HOME's java (and Hadoop helpers) first on PATH,
    so Spark uses Java 17 even if a newer Java is also installed."""
    env = dict(os.environ)
    # Spark writes start-up files to TEMP; keep them on the project's drive (C may be full)
    tmp = ROOT / "data" / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    env["TEMP"] = env["TMP"] = env["TMPDIR"] = str(tmp)
    # Spark's Windows launcher otherwise looks for "python3", which is a Microsoft Store stub
    env["PYSPARK_PYTHON"] = env["PYSPARK_DRIVER_PYTHON"] = PY
    # local mode only needs loopback; skips a hostname lookup that can stall on Windows Wi-Fi/VPN
    env.setdefault("SPARK_LOCAL_IP", "127.0.0.1")
    env.setdefault("SPARK_LOCAL_HOSTNAME", "localhost")
    front = []
    if env.get("JAVA_HOME"):
        front.append(str(Path(env["JAVA_HOME"], "bin")))
    if WINDOWS and env.get("HADOOP_HOME"):
        front.append(str(Path(env["HADOOP_HOME"], "bin")))
    if front:
        env["PATH"] = os.pathsep.join(front + [env.get("PATH", "")])
    return env


def java_exe() -> str | None:
    home = os.environ.get("JAVA_HOME")
    if home:
        exe = Path(home, "bin", "java.exe" if WINDOWS else "java")
        if exe.exists():
            return str(exe)
    return shutil.which("java")


def run(*cmd: str, env: dict | None = None) -> None:
    print("\n>", " ".join(cmd), flush=True)
    code = subprocess.run(list(cmd), cwd=ROOT, env={**tool_env(), **(env or {})}).returncode
    if code:
        sys.exit(code)


def py(*args: str, env: dict | None = None) -> None:
    run(PY, *args, env=env)


# ---------------------------------------------------------------- checks
def doctor() -> None:
    ok = True

    def line(good: bool, text: str, fix: str = "") -> None:
        nonlocal ok
        ok &= good
        print(f"  [{'ok' if good else '!!'}] {text}" + ("" if good else f"\n       fix: {fix}"))

    print("SentinelLake environment check\n")
    v = sys.version_info
    line((3, 10) <= (v.major, v.minor) <= (3, 12), f"Python {v.major}.{v.minor} ({PY})",
         "use Python 3.10, 3.11 or 3.12 (Spark 3.5 does not support newer versions)")
    line(sys.prefix != sys.base_prefix, "running inside a virtual environment",
         "create one: py -3.12 -m venv .venv   then activate it")

    java = java_exe()
    jver = ""
    if java:
        out = subprocess.run([java, "-version"], capture_output=True, text=True)
        lines = (out.stderr or out.stdout or "").splitlines()
        jver = next((ln for ln in lines if " version " in ln), lines[0] if lines else "")
    print(f"       JAVA_HOME = {os.environ.get('JAVA_HOME') or 'not set'}")
    line(bool(java) and any(f'"{n}' in jver for n in ("17", "21", "11")),
         f"Java used by Spark: {jver or 'not found'} ({java})",
         "install Java 17 (Eclipse Temurin), set JAVA_HOME to its folder, then restart VS Code")

    if WINDOWS:
        home = os.environ.get("HADOOP_HOME", "")
        wu = Path(home, "bin", "winutils.exe") if home else None
        dll = Path(home, "bin", "hadoop.dll") if home else None
        line(bool(home), f"HADOOP_HOME = {home or 'not set'}", "set HADOOP_HOME to D:\\hadoop (see README)")
        line(bool(wu and wu.exists()), "winutils.exe present", "download it into %HADOOP_HOME%\\bin (see README)")
        line(bool(dll and dll.exists()), "hadoop.dll present", "download it into %HADOOP_HOME%\\bin (see README)")
        on_path = home and any(Path(p).resolve() == Path(home, "bin").resolve()
                               for p in os.environ.get("PATH", "").split(os.pathsep) if p)
        line(bool(on_path), "%HADOOP_HOME%\\bin is on PATH", "add D:\\hadoop\\bin to your user Path and reopen the terminal")
        line(" " not in str(ROOT), f"project path has no spaces ({ROOT})", "move the project, e.g. to D:\\Projects\\sentinellake")

    for mod in ("pyspark", "pyarrow", "pandas", "fastapi", "uvicorn", "pytest", "mongomock"):
        try:
            __import__(mod)
            line(True, f"python package: {mod}")
        except ImportError:
            line(False, f"python package: {mod}", "pip install -r requirements.txt")

    free_gb = shutil.disk_usage(ROOT).free / 2**30
    line(free_gb > 3, f"{free_gb:.1f} GB free on the project drive", "free up space: Spark and the demo data need about 3 GB")

    if ok:
        ok &= spark_check(line)

    print("\nAll good. Next: python tasks.py test" if ok else "\nFix the items marked !! and run this again.")
    if not ok:
        sys.exit(1)


def _run_live(cmd: list[str], env: dict, timeout: int) -> int | None:
    """Run with output shown live; return the exit code, or None on timeout (process tree killed)."""
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env)
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if WINDOWS:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.kill()
        proc.wait()
        return None


def spark_check(line) -> bool:
    """Two steps, so a failure points at the right layer: Java + launcher first, then Python <-> JVM."""
    import pyspark
    spark_home = Path(pyspark.__file__).parent
    env = {**tool_env(), "SPARK_HOME": str(spark_home)}
    submit = spark_home / "bin" / ("spark-submit.cmd" if WINDOWS else "spark-submit")

    print("\n  Step 1/2: Spark launcher + Java (spark-submit --version), up to 2 minutes", flush=True)
    t0 = time.time()
    code = _run_live([str(submit), "--version"], env, 120)
    good = code == 0
    line(good, f"Spark launcher runs ({time.time() - t0:.0f} s)",
         "timed out: an antivirus may be blocking java.exe or cmd.exe - see the output above"
         if code is None else "see the error printed above")
    if not good:
        return False

    print("\n  Step 2/2: start Spark from Python and run a tiny job, up to 4 minutes", flush=True)
    script = ("from pyspark.sql import SparkSession; "
              "s = SparkSession.builder.master('local[1]').config('spark.ui.enabled', 'false')"
              ".config('spark.driver.host', '127.0.0.1').config('spark.driver.bindAddress', '127.0.0.1')"
              ".getOrCreate(); n = s.range(5).count(); s.stop(); print('rows counted by Spark:', n)")
    t0 = time.time()
    code = _run_live([PY, "-c", script], {**env, "SPARK_PRINT_LAUNCH_COMMAND": "1"}, 240)
    good = code == 0
    line(good, f"Spark starts from Python and runs a job ({time.time() - t0:.0f} s)",
         "timed out: allow Java in any firewall/antivirus popup, then retry" if code is None
         else "see the error printed above")
    return good


# ---------------------------------------------------------------- laptop mode
def replay() -> None:
    py("-m", "sentinellake.generator", "replay", "--hours", "6", "--out", "data/landing", "--corrupt")


def stream() -> None:
    shutil.rmtree(ROOT / "data" / "lake", ignore_errors=True)
    py("-m", "sentinellake.streaming.job", "--source", "files", "--input", "data/landing",
       "--lake", "data/lake", "--serving", "local", "--once", "--files-per-trigger", "6")


def evaluate() -> None:
    py("-m", "benchmarks.evaluate_detection")
    py("-m", "benchmarks.detection_robustness")


def serve() -> None:
    print("\nDashboard: http://localhost:8000   (Ctrl+C to stop)")
    py("-m", "uvicorn", "api.main:app", "--port", "8000",
       env={"SENTINEL_BACKEND": "local", "SENTINEL_LOCAL_DIR": "data/lake/serving"})


def demo() -> None:
    replay()
    stream()
    evaluate()
    serve()


def test() -> None:
    py("-m", "pytest", "-v")


def mapreduce() -> None:
    py("-m", "mapreduce.local_runner", "all", "--input", "data/landing", "--out", "results/mapreduce")


def hive() -> None:
    py("-m", "hive.run_local", "--lake", "data/lake")


def bench() -> None:
    py("-m", "benchmarks.run_benchmarks")


def charts() -> None:
    py("-m", "benchmarks.make_charts")


# ---------------------------------------------------------------- cluster mode
def compose(*args: str) -> None:
    run("docker", "compose", *args)


def up() -> None:
    compose("up", "-d", "--build")
    print("\nDashboard: http://localhost:8000  (first incident about 15 minutes after start)")


def batch_up() -> None:
    compose("--profile", "batch", "up", "-d", "--build")


def logs() -> None:
    compose("logs", "-f", "stream")


def down() -> None:
    compose("--profile", "batch", "down")


def cluster_mapreduce(day: str | None = None) -> None:
    day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    compose("exec", "namenode", "bash", "/opt/sentinellake/mapreduce/run_hadoop.sh", day)


def cluster_hive() -> None:
    for f in ("01_tables.hql", "02_analytics.hql"):
        compose("exec", "hive", "beeline", "-u", "jdbc:hive2://localhost:10000", "-f", f"/opt/sentinellake/hive/{f}")


TASKS = {
    "doctor": doctor, "test": test, "demo": demo, "replay": replay, "stream": stream,
    "evaluate": evaluate, "serve": serve, "mapreduce": mapreduce, "hive": hive, "bench": bench,
    "charts": charts, "up": up, "batch-up": batch_up, "logs": logs, "down": down,
    "cluster-mapreduce": cluster_mapreduce, "cluster-hive": cluster_hive,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in TASKS:
        print(__doc__)
        sys.exit(0 if len(sys.argv) < 2 else 1)
    TASKS[sys.argv[1]](*sys.argv[2:])
