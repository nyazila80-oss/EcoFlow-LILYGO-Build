#pragma once
#include <stdint.h>

enum class HeavyOpOwner : uint8_t { NONE=0, POWERSTREAM_BLE=1, POWERSTREAM_CLOUD=2 };
bool heavyOpTryAcquire(HeavyOpOwner owner);
void heavyOpRelease(HeavyOpOwner owner);
HeavyOpOwner heavyOpOwner();
const char* heavyOpOwnerName();
uint32_t heavyOpAgeMs();
uint32_t heavyOpAcquireCount();
uint32_t heavyOpReleaseMismatchCount();
