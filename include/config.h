#pragma once
#include <Arduino.h>
#include <Preferences.h>
#include <atomic>

#define FW_VERSION "2.4.5.9.36.7.15AO-WEB-QUIESCE-TLS-FIX"

// RS485
#define RS485_TX 22
#define RS485_RX 21
#define RS485_CALLBACK 17
#define RS485_EN 19
#define BOOST_ENABLE_PIN 16

// WS2812B
#define WS2812B_DATA 4

// CAN
#define CAN_TX 27
#define CAN_RX 26

// Keep the remainder of this header supplied by the canonical branch below.
#include "config_rest.inc"
