#pragma once
#include <Arduino.h>
#include <Preferences.h>
#include <atomic>

#define FW_VERSION "2.4.5.9.36.7.15Z-MEMORY-RELIEF-AB8"

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
#define CAN_SPEED_MODE 23

// RS485 and CAN Boost power supply
#define ME2107_EN 16 

// SD
#define SD_MISO 2
#define SD_MOSI 15
#define SD_SCLK 14
#define SD_CS 13

// ---- Global configuration structure ----
struct Config {
  uint8_t soc = 1;
  uint16_t volt = 0;
  uint16_t chgvolt = 57600;
  uint8_t temp = 20;
  uint32_t disruntime = 1;
  uint32_t chgruntime = 1;
  uint8_t bmsChgUp = 100;
  uint8_t bmsChgDn = 10;
  bool flagCB = false;
  char serialStr[17] = "M102Z3B4ZE5H1234";
  bool txlogging = true;
  bool rxlogging = true;
  bool canTxEnabled = true;
  bool canRxEnabled = true;
  bool message3C = true;
  bool message13 = true;
  bool messageCB = true;
