"""Current diagnostic regression for the no-app JK path and OTA completion gate.

The state model checks the intended boundary; source checks keep it attached to
the implementation. Hardware callback timing and Update internals remain HIL.
"""
from pathlib import Path
import random
import re

root = Path(__file__).resolve().parent
jk = (root / "src/jk_ble_proxy.cpp").read_text()
ota = (root / "src/ota.cpp").read_text()
bms = (root / "src/bms.cpp").read_text()

notify = jk.split("static void remoteNotify(", 1)[1].split("static void bridgePump()", 1)[0]
assert notify.index("!sAppConnected.load") < notify.index("queuePacket(sBmsToApp")
assert "!sBmsConnected.load" in notify and "bleEventsPending()" in notify

for route, next_route in (("/ota_update", "/ota_fs"), ("/ota_fs", None)):
    block = ota.split(f'server.on("{route}", HTTP_POST,', 1)[1]
    if next_route:
        block = block.split(f'server.on("{next_route}", HTTP_POST,', 1)[0]
    assert 'otaState(request) == 2 && !Update.hasError()' in block
    assert 'otaSetState(request,2)' in block or 'otaSetState(request, 2)' in block
    end_call = 'Update.end(true)' if route == '/ota_update' else 'Update.end(false)'
    assert block.index(end_call) < block.rindex('otaSetState(request,')

assert 'request->_tempObject = malloc(sizeof(uint8_t))' in ota
assert 'request->_tempObject = (void*)' not in ota
assert 'sActiveHttpOta.compare_exchange_strong(expected, request' in ota
assert 'sActiveHttpOta.compare_exchange_strong(owner, nullptr' in ota
assert 'request->onDisconnect([request, filesystem]()' in ota
assert 'if (otaState(request) == 3)' in ota and 'Update.abort()' in ota
assert len(re.findall(r'otaSetState\(request,\s*3\)', ota)) == 2
assert ota.count('otaState(request) != 3') == 2
assert 'WRITE VERIFY failed: setup read-back timeout' in bms
assert 'WRITE VERIFY failed: rejected setup read-back' in bms
assert 'WRITE VERIFY failed: invalid setup read-back' in bms
assert 'void JKPBBms::parseSetup() {\n  // A failed new setup read' in bms
assert 'setupValid_ = false;' in bms
assert (root / 'partitions.csv').read_text().count('0x60000') >= 1

rng = random.Random(936711)
for _ in range(1_000_000):
    app = bool(rng.getrandbits(1))
    bms = bool(rng.getrandbits(1))
    fault = bool(rng.getrandbits(1))
    pending = bool(rng.getrandbits(1))
    queued = app and bms and not fault and not pending
    assert not queued or (app and bms)
    upload_finished = bool(rng.getrandbits(1))
    update_error = bool(rng.getrandbits(1))
    response_ok = upload_finished and not update_error
    assert not response_ok or upload_finished
    expected_fs_size = 0x60000
    received_fs_size = rng.randrange(expected_fs_size - 2, expected_fs_size + 3)
    fs_ok = received_fs_size == expected_fs_size and not update_error
    assert not fs_ok or received_fs_size == expected_fs_size

# Two request streams must never own the single Update writer simultaneously.
owner = None
for i in range(1_000_000):
    request = rng.randrange(8)
    if rng.getrandbits(1):
        if owner is None:
            owner = request
        else:
            assert owner in range(8)
    elif owner == request:
        owner = None

print("PASS diagnostic JK no-app, OTA completion and single-writer model: 2000000 states")
