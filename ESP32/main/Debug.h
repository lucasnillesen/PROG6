// SPDX-License-Identifier: MIT

// Simple debug logging infrastructure. Define DEBUG_MODE before including this
// header to enable logging. When DEBUG_MODE is not defined, all debug
// statements are compiled out, allowing the firmware to run without serial
// overhead.

#pragma once

#include <Arduino.h>

#ifdef DEBUG_MODE
  #define DEBUG_BEGIN(baud)    Serial.begin(baud)
  #define DEBUG_PRINT(x)       Serial.print(x)
  #define DEBUG_PRINTLN(x)     Serial.println(x)
  #define DEBUG_PRINTF(...)    Serial.printf(__VA_ARGS__)
#else
  #define DEBUG_BEGIN(baud)    (void)0
  #define DEBUG_PRINT(x)       (void)0
  #define DEBUG_PRINTLN(x)     (void)0
  #define DEBUG_PRINTF(...)    (void)0
#endif