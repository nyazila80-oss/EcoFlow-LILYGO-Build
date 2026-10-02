#include "powerstream_ble_lab.h"
#include "resource_gate.h"
#include <Preferences.h>
#include <NimBLEDevice.h>

// 15AC3 linker/lifecycle repair.
//
// Cloud TLS is allowed to reclaim only the cached PowerStream client that matches
// the persisted PowerStream peer identity, and only while the global heavy-op gate
// is owned by POWERSTREAM_CLOUD.  An active/connecting client is never deleted.
// The NimBLE host, JK proxy, advertising state, and unrelated clients are untouched.
bool powerStreamBleLabReclaimIdleClientForCloud(bool& released) {
  released = false;

  // Fail closed unless the caller already owns the cloud heavy-operation slot.
  // This excludes the PowerStream BLE worker because both operations share the
  // same resource gate.
  if (heavyOpOwner() != HeavyOpOwner::POWERSTREAM_CLOUD) return false;

  Preferences p;
  if (!p.begin("psblelab", true)) return false;
  const String mac = p.getString("mac", "");
  const int addrType = p.getInt("atype", -1);
  p.end();

  // No configured PowerStream peer means there is no peer-specific cache to
  // reclaim.  This is a safe no-op, not an error.
  if (mac.length() != 17 || (addrType != 0 && addrType != 1)) return true;

  const NimBLEAddress peer(mac.c_str(), addrType == 1 ? BLE_ADDR_RANDOM : BLE_ADDR_PUBLIC);
  NimBLEClient* client = NimBLEDevice::getClientByPeerAddress(peer);
  if (!client) return true;

  // Never tear down a live link for TLS memory.  The cloud operation must abort
  // instead and may be retried after the BLE transaction has become idle.
  if (client->isConnected()) return false;

  // deleteClient is the NimBLE-supported destruction path and removes only this
  // peer-specific cached client from the global client list.
  if (!NimBLEDevice::deleteClient(client)) return false;
  released = true;
  return true;
}
