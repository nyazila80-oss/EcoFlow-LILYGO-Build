#pragma once
#include <cstdint>
#define MALLOC_CAP_8BIT 1
inline uint32_t heap_caps_get_largest_free_block(int) { return 23000; }
