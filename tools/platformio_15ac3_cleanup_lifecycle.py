Import("env")
from pathlib import Path

p = Path(env["PROJECT_DIR"]) / "src" / "powerstream_ble_lab.cpp"
s = p.read_text(encoding="utf-8")
marker = "// 15AC3 CLEANUP LIFECYCLE ATTRIBUTION"
if marker in s:
    print("[15AC3] cleanup lifecycle attribution already installed")
else:
    anchor = "static std::atomic<int32_t> sCleanupDeltaFree{0},sCleanupDeltaLargest{0};"
    if s.count(anchor) != 1:
        raise RuntimeError("15AC3 state anchor missing/non-unique")
    state = anchor + '''\n// 15AC3 CLEANUP LIFECYCLE ATTRIBUTION\nstatic std::atomic<uint32_t> sAc3PreCleanupFree{0},sAc3PreCleanupLargest{0};\nstatic std::atomic<uint32_t> sAc3PostClientFree{0},sAc3PostClientLargest{0};\nstatic std::atomic<uint32_t> sAc3PostReleaseFree{0},sAc3PostReleaseLargest{0};\nstatic std::atomic<uint32_t> sAc3FinishedFree{0},sAc3FinishedLargest{0};\nstatic std::atomic<uint32_t> sAc3CleanupGeneration{0};\n'''
    s = s.replace(anchor, state, 1)

    old = "psProbeTraceMark(PS_PROBE_CLEANUP);\n  cleanupClient();if(auxReserved)jkBleProxyReleaseAuxConnection();sLastOpMs=millis()-started;sWorkerStartedAt=0;"
    if s.count(old) != 1:
        raise RuntimeError("15AC3 cleanup anchor missing/non-unique")
    new = '''psProbeTraceMark(PS_PROBE_CLEANUP);\n  memSnap(sAc3PreCleanupFree,sAc3PreCleanupLargest);\n  cleanupClient();\n  memSnap(sAc3PostClientFree,sAc3PostClientLargest);\n  if(auxReserved)jkBleProxyReleaseAuxConnection();\n  memSnap(sAc3PostReleaseFree,sAc3PostReleaseLargest);\n  sAc3CleanupGeneration.fetch_add(1,std::memory_order_relaxed);\n  sLastOpMs=millis()-started;sWorkerStartedAt=0;'''
    s = s.replace(old, new, 1)

    old2 = "psProbeTraceMark(PS_PROBE_FINISHED);\n  heavyOpRelease(HeavyOpOwner::POWERSTREAM_BLE);sWorkerRunning=false;vTaskDelete(nullptr);"
    if s.count(old2) != 1:
        raise RuntimeError("15AC3 finish anchor missing/non-unique")
    new2 = '''psProbeTraceMark(PS_PROBE_FINISHED);\n  heavyOpRelease(HeavyOpOwner::POWERSTREAM_BLE);\n  memSnap(sAc3FinishedFree,sAc3FinishedLargest);\n  sWorkerRunning=false;vTaskDelete(nullptr);'''
    s = s.replace(old2, new2, 1)
    p.write_text(s, encoding="utf-8")
    print("[15AC3] cleanup lifecycle attribution installed")

# Fail fast if the intended checkpoints are not unique after patching.
out = p.read_text(encoding="utf-8")
for token in ["sAc3PreCleanupFree","sAc3PostClientFree","sAc3PostReleaseFree","sAc3FinishedFree","sAc3CleanupGeneration"]:
    if out.count(token) < 2:
        raise RuntimeError("15AC3 postcondition failed: " + token)
print("[15AC3] postconditions PASS")
