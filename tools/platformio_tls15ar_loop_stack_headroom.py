from pathlib import Path
Import("env")

root = Path(env["PROJECT_DIR"])
main = (root / "src/main.cpp").read_text()
api_path = root / "src/powerstream_api.cpp"
api = api_path.read_text()

required = [
    "TLS15AR_LOOP_STACK_BYTES = 7168",
    "SET_LOOP_TASK_STACK_SIZE(TLS15AR_LOOP_STACK_BYTES)",
    "TLS15AR_MIN_STACK_MARGIN_BYTES = 2048",
]
missing = [token for token in required if token not in main]
if missing:
    raise RuntimeError("15AR main.cpp gate missing: " + ", ".join(missing))

marker = r',"http_quiet_window_ms":750,'
addition = (
    r',"http_quiet_window_ms":750,'
    r'"15ar_version":"9.36.7.15AR-LOOP-STACK-HEADROOM",'
    r'"15ar_loop_stack_bytes":7168,'
    r'"15ar_min_stack_margin_bytes":2048,'
)

if '15ar_version' not in api:
    if marker not in api:
        raise RuntimeError("15AR could not find post-15AO JSON insertion marker")
    api = api.replace(marker, addition, 1)
    api_path.write_text(api)

api = api_path.read_text()
for token in (
    '15ar_version',
    '9.36.7.15AR-LOOP-STACK-HEADROOM',
    '15ar_loop_stack_bytes',
    '15ar_min_stack_margin_bytes',
):
    if api.count(token) != 1:
        raise RuntimeError(f"15AR fixed-point gate failed for {token}: count={api.count(token)}")

print("[15AR] fixed point PASS: loop stack=7168, required hardware margin=2048; TLS verification unchanged")
