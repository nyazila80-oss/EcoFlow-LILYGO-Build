from pathlib import Path


dashboard = Path("data/bms_dashboard.html").read_text(encoding="utf-8")

required = (
    "if(activeTab==='powerstream'||psCloudJobActive)",
    "activeTab==='powerstream'?5000:1000",
    "new URLSearchParams(location.search).get('tab')",
    "if(requestedTab==='powerstream')",
    "tab('powerstream',psButton)",
    "if(psMinimalMode)return",
    "if(psMinimalMode||document.hidden",
    "if(!psMinimalMode)loadBleIsolation()",
)
missing = [token for token in required if dashboard.count(token) != 1]
if missing:
    raise SystemExit(f"15AG PowerStream poll isolation missing/duplicated: {missing!r}")

poll_start = dashboard.index("async function poll()")
poll_end = dashboard.index("async function writeSetting()", poll_start)
poll_body = dashboard[poll_start:poll_end]
guard_pos = poll_body.index("if(activeTab==='powerstream'||psCloudJobActive)")
fetch_pos = poll_body.index("fetchBounded('/api/bms'")
if guard_pos > fetch_pos:
    raise SystemExit("15AG PowerStream poll guard executes after /api/bms fetch")

minimal_start = dashboard.index("if(requestedTab==='powerstream')")
minimal_end = dashboard.index("if(!psMinimalMode)loadBleIsolation()", minimal_start)
minimal_body = dashboard[minimal_start:minimal_end]
for token in ("psMinimalMode=true", "psInitialLoaded=true", "loadPsCloud()"):
    if minimal_body.count(token) != 1:
        raise SystemExit(f"15AG minimal PowerStream startup missing/duplicated: {token}")
for forbidden in ("loadPs()", "loadPsBleStatus", "loadAuthDiag", "loadNetHealth", "readLimits"):
    if forbidden in minimal_body:
        raise SystemExit(f"15AG minimal PowerStream startup calls diagnostic endpoint: {forbidden}")

print("15AG PowerStream/BMS poll isolation audit PASS")
