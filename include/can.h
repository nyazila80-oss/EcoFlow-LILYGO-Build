#pragma once

#include <Arduino.h>
#include "driver/twai.h"
#include "config.h"
#include <atomic>

// ---- Queue sizes ----
#ifndef TWAI_RXQ
  #define TWAI_RXQ 32
  #define TWAI_TXQ 16
#endif

// ---- CAN state ----
extern bool twai_ok;

extern QueueHandle_t canRxQ;

extern std::atomic<uint32_t> can_rx_count;
extern std::atomic<uint32_t> can_rx_dropped;
extern std::atomic<uint32_t> can_rx_queue_overflow;
extern std::atomic<uint32_t> can_rx_epoch_dropped;
extern std::atomic<uint32_t> can_decoded;
extern std::atomic<uint32_t> can_rx_filtered;
extern std::atomic<uint32_t> can_log_dropped;
extern std::atomic<uint32_t> can_bus_off_count;
extern std::atomic<uint32_t> can_bus_recovered_count;
extern std::atomic<uint32_t> can_bus_recovery_fail;

// ---- Driver initialiser ----
void canInitDriver();

// ---- Create RX queue + start tasks if driver ok ----
void canStartTasks();

// ---- /can_try_init Link ---- 
bool canTryInitAndStart();

// ---- CAN Frame EcoFlow sender ----
bool sendCANFrame(uint32_t can_id, const uint8_t* data, uint8_t len);

// AUDIT19.15.19: task stack diagnostics; raw FreeRTOS high-water values.
UBaseType_t canRxStackHighWater();
UBaseType_t canDecodeStackHighWater();

// Monotonic fault boundary; increments whenever BUS-OFF is observed.
uint32_t canCurrentBusEpoch();
