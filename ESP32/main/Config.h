// This header centralises all constants and configuration values used by the
// project.

#pragma once

namespace Config {
  // ---------------------------------------------------------------------------
  // Hardware pin assignments
  // ---------------------------------------------------------------------------
  constexpr uint8_t DOOR_SERVO_PIN     = 5;
  constexpr int     DOOR_POSITION_OPEN  = 140;
  constexpr int     DOOR_POSITION_CLOSE = 10;

  // Stepper motor pins for the Y axis (vertical lift).
  constexpr uint8_t STEP_PIN_Y = 10;
  constexpr uint8_t DIR_PIN_Y  = 2;

  // Stepper motor pins for the X axis (horizontal slide).
  constexpr uint8_t STEP_PIN_X = 4;
  constexpr uint8_t DIR_PIN_X  = 3;

  // UART pins used by the TMC2209 drivers.
  constexpr uint8_t UART_RX_PIN = 6;
  constexpr uint8_t UART_TX_PIN = 7;

  // Limit switches used to detect end‑stops.
  constexpr uint8_t LIMIT_SWITCH_X_PIN = 0;
  constexpr uint8_t LIMIT_SWITCH_Y_PIN = 1;

  // StallGuard sense resistor
  constexpr float R_SENSE = 0.11f;

  // Driver addresses on the shared UART
  constexpr uint8_t DRIVER_ADDRESS_Y = 0b00;
  constexpr uint8_t DRIVER_ADDRESS_X = 0b01;

  // ---------------------------------------------------------------------------
  // Motion parameters
  // ---------------------------------------------------------------------------

  // Size of the moving average buffer used to smooth StallGuard readings.
  constexpr int SG_BUFFER_SIZE = 10;

  // Warm‑up time in milliseconds before StallGuard baseline detection begins.
  constexpr unsigned long WARMUP_MS = 8000UL;

  // Percentage drop from the baseline used to detect the top of the Y travel.
  constexpr float DROP_PCT_TOP    = 0.35f;
  // Number of samples below the drop threshold required to confirm the drop.
  constexpr int   SGY_TOP_SAMPLES = 30;

  // Percentage drop used to detect an impact on the way down.
  constexpr float DROP_PCT_IMPACT    = 0.30f;
  // Number of samples below the impact threshold required to confirm the drop.
  constexpr int   SGY_CONFIRM_SAMPLES = 20;

  // ---------------------------------------------------------------------------
  // Wi‑Fi and networking
  // ---------------------------------------------------------------------------

  constexpr const char WEB_SERVER_HOST[] = "192.168.178.34"; // Host of the Flask web interface that receives progress feedback from the ESP32.
  constexpr uint16_t WEB_SERVER_PORT = 5000; // HTTP port used by the remote Flask server. Use 5000 unless the backend is configured differently.

  constexpr unsigned long WIFI_RECONNECT_INTERVAL_MS = 10000UL; // Retry interval in milliseconds for Wi‑Fi reconnection attempts.

}