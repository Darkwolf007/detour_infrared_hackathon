"""
Memory + stage-timing monitor for the backend process.
Run: python monitor_mem.py <pid>
Samples memory every 1 s, prints a report when stdin receives 'q' or Ctrl-C.
"""
import sys
import time
import signal
import threading
import psutil
from datetime import datetime

PID = int(sys.argv[1]) if len(sys.argv) > 1 else None

samples: list[tuple[float, float]] = []   # (elapsed_s, rss_mb)
stop_event = threading.Event()

def _sample(proc: psutil.Process):
    start = time.monotonic()
    print(f"[monitor] Sampling PID {proc.pid} ({proc.name()}) — hit the API now, then press Ctrl-C to print report\n", flush=True)
    while not stop_event.is_set():
        try:
            rss = proc.memory_info().rss / 1024 / 1024
            elapsed = time.monotonic() - start
            samples.append((elapsed, rss))
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"  {ts}  +{elapsed:6.1f}s  RSS {rss:7.1f} MB", flush=True)
        except psutil.NoSuchProcess:
            print("[monitor] Process gone.", flush=True)
            break
        time.sleep(1.0)

def _report():
    if not samples:
        print("\n[monitor] No samples collected.")
        return
    rss_vals = [r for _, r in samples]
    baseline = rss_vals[0]
    peak = max(rss_vals)
    peak_t = samples[rss_vals.index(peak)][0]
    final = rss_vals[-1]
    print("\n" + "="*55)
    print("MEMORY REPORT")
    print("="*55)
    print(f"  Baseline  : {baseline:.1f} MB")
    print(f"  Peak      : {peak:.1f} MB  (+{peak - baseline:.1f} MB spike)  at +{peak_t:.1f}s")
    print(f"  Final     : {final:.1f} MB  (+{final - baseline:.1f} MB retained)")
    print(f"  Duration  : {samples[-1][0]:.1f}s  ({len(samples)} samples)")

    # Detect significant jumps (>50 MB in a single second)
    print("\n  Jumps > 50 MB:")
    found = False
    for i in range(1, len(samples)):
        delta = samples[i][1] - samples[i-1][1]
        if abs(delta) > 50:
            t = samples[i][0]
            print(f"    +{t:.1f}s  {samples[i-1][1]:.1f} → {samples[i][1]:.1f} MB  ({delta:+.1f} MB)")
            found = True
    if not found:
        print("    none")
    print("="*55)

def _on_signal(sig, frame):
    stop_event.set()

signal.signal(signal.SIGINT, _on_signal)
signal.signal(signal.SIGTERM, _on_signal)

try:
    proc = psutil.Process(PID)
except Exception as e:
    print(f"[monitor] Cannot attach to PID {PID}: {e}")
    sys.exit(1)

t = threading.Thread(target=_sample, args=(proc,), daemon=True)
t.start()
t.join()
_report()
