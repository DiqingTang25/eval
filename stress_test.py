#!/usr/bin/env python3
"""Agent Eval — Concurrent stress test (stdlib only)"""
import urllib.request
import urllib.error
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

TIMEOUT = 30
LEVELS = [50, 100, 200]
MULT = 5  # total = concurrency * MULT


def req(url):
    start = time.perf_counter()
    try:
        r = urllib.request.Request(url)
        with urllib.request.urlopen(r, timeout=TIMEOUT) as resp:
            return True, (time.perf_counter() - start) * 1000, resp.status
    except urllib.error.HTTPError as e:
        return True, (time.perf_counter() - start) * 1000, e.code
    except Exception as e:
        return False, (time.perf_counter() - start) * 1000, str(e)[:80]


def bench(label, url, conc, total):
    print(f"\n===== {label} | conc={conc} total={total} =====")
    results = {"ok": 0, "fail": 0, "lats": [], "codes": {}}
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=conc) as ex:
        fs = [ex.submit(req, url) for _ in range(total)]
        for f in as_completed(fs):
            ok, ms, st = f.result()
            results["lats"].append(ms)
            if ok:
                results["ok"] += 1
            else:
                results["fail"] += 1
            k = str(st)
            results["codes"][k] = results["codes"].get(k, 0) + 1
    wall = time.perf_counter() - t0
    lats = sorted(results["lats"])
    n = len(lats)
    avg = sum(lats) / n if n else 0
    p50 = lats[n // 2] if n else 0
    p95 = lats[int(n * 0.95)] if n else 0
    p99 = lats[int(n * 0.99)] if n else 0
    qps = results["ok"] / wall if wall > 0 else 0
    print(f"  OK={results['ok']} FAIL={results['fail']} wall={wall:.2f}s QPS={qps:.1f}")
    print(f"  Latency(ms): avg={avg:.1f} p50={p50:.1f} p95={p95:.1f} p99={p99:.1f} min={lats[0]:.1f} max={lats[-1]:.1f}")
    print(f"  Status codes: {results['codes']}")
    return {
        "label": label, "conc": conc, "total": total,
        "ok": results["ok"], "fail": results["fail"],
        "qps": round(qps, 1), "avg_ms": round(avg, 1),
        "p50_ms": round(p50, 1), "p95_ms": round(p95, 1),
        "p99_ms": round(p99, 1),
        "min_ms": round(lats[0], 1) if lats else 0,
        "max_ms": round(lats[-1], 1) if lats else 0,
        "wall_s": round(wall, 2),
    }


def main():
    # probe proxy
    try:
        urllib.request.urlopen("http://127.0.0.1/test/", timeout=5)
        px = "http://127.0.0.1/test/"
        print(f"Proxy reachable: {px}")
    except Exception as e:
        px = "http://127.0.0.1/test/"
        print(f"Proxy probe failed ({e}), fallback: {px}")

    targets = [("Direct-8000", "http://127.0.0.1:8000/"), ("Nginx-/test", px)]
    all_res = []
    for label, url in targets:
        for c in LEVELS:
            all_res.append(bench(label, url, c, c * MULT))
            time.sleep(2)

    print("\n\n" + "=" * 72)
    hdr = f"{'Target':<16s} {'Conc':>5s} {'Total':>6s} {'OK':>5s} {'Fail':>5s} {'QPS':>7s} {'avg_ms':>8s} {'p99_ms':>8s}"
    print(hdr)
    print("-" * 72)
    for r in all_res:
        print(f"{r['label']:<16s} {r['conc']:>5d} {r['total']:>6d} {r['ok']:>5d} {r['fail']:>5d} {r['qps']:>7.1f} {r['avg_ms']:>8.1f} {r['p99_ms']:>8.1f}")
    print("=" * 72)
    print("JSON_RESULT:", json.dumps(all_res, ensure_ascii=False))


if __name__ == "__main__":
    main()
