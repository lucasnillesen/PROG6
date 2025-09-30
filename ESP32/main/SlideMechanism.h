/**
 * @file SlideMechanism.h
 *
 * Encapsulation of the sliding and lifting mechanism. This class manages two
 * stepper motors controlled by TMC2209 drivers. Its public API exposes a
 * simple life‑cycle: call begin() once during setup, call start() when a
 * product removal cycle should begin and then call update() on every
 * iteration of the loop.
 */

#pragma once

#include <AccelStepper.h>
#include <TMCStepper.h>
#include <Arduino.h>
#include "Config.h"
#include "Debug.h"

class SlideMechanism {
public:
  enum class Phase {
    Idle,
    Begin,
    MovingUp,
    MovingIn,
    MovingDown,
    MovingOut,
    Returning
  };

  /**
   * Type alias for callback functions. The callback will be invoked when
   * the cycle starts and again when it ends. The bool parameter for the
   * finished callback indicates success (true) or failure (false).
   */
  using Callback = void(*)(bool success);

  SlideMechanism();

  void begin();
  void start(Callback onStarted = nullptr, Callback onFinished = nullptr);
  void update();

  bool isBusy() const { return m_busy; }

private:
  // Internal helpers for StallGuard smoothing.
  uint16_t averageY() const;
  uint16_t averageX() const;
  void     resetBuffers();
  void     maybeSetBaselineUp(uint16_t avg);
  void     maybeSetBaselineDown(uint16_t avg);
  bool     dropConfirmedUp(uint16_t avg);
  bool     dropConfirmedDown(uint16_t avg);

  // Callback pointers.
  Callback m_onStarted;
  Callback m_onFinished;

  // Hardware objects.
  HardwareSerial m_serialPort;
  TMC2209Stepper m_driverY;
  TMC2209Stepper m_driverX;
  AccelStepper   m_stepperY;
  AccelStepper   m_stepperX;

  // StallGuard buffers.
  uint16_t m_sgYBuffer[Config::SG_BUFFER_SIZE];
  uint16_t m_sgXBuffer[Config::SG_BUFFER_SIZE];
  int      m_sgYIndex;
  int      m_sgXIndex;

  // Baseline detection variables.
  bool     m_baselineUpSet;
  uint16_t m_baselineUp;
  int      m_confirmUp;
  bool     m_baselineDownSet;
  uint16_t m_baselineDown;
  int      m_confirmDown;

  // State machine.
  Phase    m_phase;
  unsigned long m_motionStart;
  bool     m_impactMonitoringY;
  bool     m_impactMonitoringX;
  bool     m_busy;
  bool     m_reportedStuck;
  bool     m_manualPwm;

  // Internal methods for state transitions.
  void handleBegin();
  void handleMovingUp();
  void handleMovingIn();
  void handleMovingDown();
  void handleMovingOut();
  void handleReturning();
};