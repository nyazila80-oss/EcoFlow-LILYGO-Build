#pragma once
#include <stdint.h>

// ESP-IDF returns the task's minimum lifetime free stack in bytes.
uint32_t diagHeartbeatStackMinBytes();
