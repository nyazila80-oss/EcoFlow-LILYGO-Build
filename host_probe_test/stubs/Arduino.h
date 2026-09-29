#pragma once
#include <cstdint>
struct EspStub { uint32_t getFreeHeap() const { return 41000; } };
extern EspStub ESP;
uint32_t millis();
using portMUX_TYPE = int;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(mux) ((void)(mux))
#define portEXIT_CRITICAL(mux) ((void)(mux))
