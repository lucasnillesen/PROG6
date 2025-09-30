#include "SlideMechanism.h"

SlideMechanism::SlideMechanism()
  : m_onStarted(nullptr),
    m_onFinished(nullptr),
    m_serialPort(1),
    m_driverY(&m_serialPort, Config::R_SENSE, Config::DRIVER_ADDRESS_Y),
    m_driverX(&m_serialPort, Config::R_SENSE, Config::DRIVER_ADDRESS_X),
    m_stepperY(AccelStepper::DRIVER, Config::STEP_PIN_Y, Config::DIR_PIN_Y),
    m_stepperX(AccelStepper::DRIVER, Config::STEP_PIN_X, Config::DIR_PIN_X),
    m_sgYIndex(0),
    m_sgXIndex(0),
    m_baselineUpSet(false),
    m_baselineUp(0),
    m_confirmUp(0),
    m_baselineDownSet(false),
    m_baselineDown(0),
    m_confirmDown(0),
    m_phase(Phase::Idle),
    m_motionStart(0),
    m_impactMonitoringY(false),
    m_impactMonitoringX(false),
    m_busy(false),
    m_reportedStuck(false),
    m_manualPwm(false)
{
  // Initialise buffers with zeros
  for (int i = 0; i < Config::SG_BUFFER_SIZE; ++i) {
    m_sgYBuffer[i] = 0;
    m_sgXBuffer[i] = 0;
  }
}

void SlideMechanism::begin() {
  // Initialise serial port for the drivers
  m_serialPort.begin(115200, SERIAL_8N1, Config::UART_RX_PIN, Config::UART_TX_PIN);
  delay(1000);

  // Initialise limit switch pins
  pinMode(Config::LIMIT_SWITCH_X_PIN, INPUT_PULLUP);
  pinMode(Config::LIMIT_SWITCH_Y_PIN, INPUT_PULLUP);

  // Initialise TMC drivers
  m_driverY.begin(); delay(100);
  m_driverY.pdn_disable(true);
  m_driverY.mstep_reg_select(true);
  m_driverY.I_scale_analog(false);
  m_driverY.GCONF(m_driverY.GCONF() & ~(1 << 2));
  m_driverY.en_spreadCycle(true);

  m_driverX.begin(); delay(100);
  m_driverX.pdn_disable(true);
  m_driverX.mstep_reg_select(true);
  m_driverX.I_scale_analog(false);
  m_driverX.GCONF(m_driverX.GCONF() & ~(1 << 2));
  m_driverX.en_spreadCycle(true);

  // Set current and microstepping configuration
  m_driverY.rms_current(800);
  m_driverY.microsteps(16);
  m_driverY.toff(5);
  m_driverY.tbl(1);
  m_driverY.hstrt(3);
  m_driverY.hend(0);
  m_driverY.pwm_autoscale(false);
  m_driverY.TCOOLTHRS(0xFFFF);
  m_driverY.SGTHRS(1);

  m_driverX.rms_current(800);
  m_driverX.microsteps(16);
  m_driverX.toff(5);
  m_driverX.tbl(1);
  m_driverX.hstrt(3);
  m_driverX.hend(0);
  m_driverX.pwm_autoscale(false);
  m_driverX.TCOOLTHRS(0xFFFF);
  m_driverX.SGTHRS(1);

  // Give drivers some time to settle
  delay(2000);
  m_driverY.begin();
  m_driverX.begin();
  m_driverY.en_spreadCycle(true);
  m_driverX.en_spreadCycle(true);
  m_driverY.GCONF(m_driverY.GCONF() & ~(1 << 2));
  m_driverX.GCONF(m_driverX.GCONF() & ~(1 << 2));

  // Configure steppers
  m_stepperY.setMaxSpeed(1000);
  m_stepperX.setMaxSpeed(1000);
  m_stepperY.setAcceleration(2000);
  m_stepperX.setAcceleration(2000);

  // Ensure internal state is reset
  resetBuffers();
  m_baselineUpSet   = false;
  m_baselineDownSet = false;
  m_confirmUp       = 0;
  m_confirmDown     = 0;
  m_phase           = Phase::Idle;
  m_busy            = false;
  m_reportedStuck   = false;
  m_manualPwm       = false;
}

void SlideMechanism::start(Callback onStarted, Callback onFinished) {
  if (m_busy) {
    // Already running; ignore repeated start requests.
    return;
  }
  m_onStarted  = onStarted;
  m_onFinished = onFinished;
  m_busy       = true;
  m_phase      = Phase::Begin;
  m_motionStart = millis();
  m_reportedStuck = false;
  m_manualPwm  = false;

  // Reset StallGuard buffers and detection state.
  resetBuffers();
  m_baselineUpSet   = false;
  m_baselineDownSet = false;
  m_confirmUp       = 0;
  m_confirmDown     = 0;

  if (m_onStarted) {
    m_onStarted(true);
  }
}

void SlideMechanism::update() {
  // If not running, nothing to do.
  if (!m_busy) {
    return;
  }

  // Always run steppers to keep motors moving.
  m_stepperY.run();
  m_stepperX.run();

  // Throttle StallGuard updates to ~20 Hz.
  static unsigned long lastTick = 0;
  if (millis() - lastTick < 50) {
    return;
  }
  lastTick = millis();

  // Read StallGuard values and maintain rolling averages.
  uint16_t sgY = m_driverY.SG_RESULT();
  uint16_t sgX = m_driverX.SG_RESULT();
  m_sgYBuffer[m_sgYIndex] = sgY;
  m_sgYIndex = (m_sgYIndex + 1) % Config::SG_BUFFER_SIZE;
  m_sgXBuffer[m_sgXIndex] = sgX;
  m_sgXIndex = (m_sgXIndex + 1) % Config::SG_BUFFER_SIZE;
  uint16_t avgY = averageY();
  uint16_t avgX = averageX();

  switch (m_phase) {
    case Phase::Begin:
      handleBegin();
      break;
    case Phase::MovingUp:
      handleMovingUp();
      break;
    case Phase::MovingIn:
      handleMovingIn();
      break;
    case Phase::MovingDown:
      handleMovingDown();
      break;
    case Phase::MovingOut:
      handleMovingOut();
      break;
    case Phase::Returning:
      handleReturning();
      break;
    default:
      // Idle or unknown state; do nothing
      break;
  }
}


uint16_t SlideMechanism::averageY() const {
  uint32_t sum = 0;
  for (int i = 0; i < Config::SG_BUFFER_SIZE; i++) {
    sum += m_sgYBuffer[i];
  }
  return static_cast<uint16_t>(sum / Config::SG_BUFFER_SIZE);
}

uint16_t SlideMechanism::averageX() const {
  uint32_t sum = 0;
  for (int i = 0; i < Config::SG_BUFFER_SIZE; i++) {
    sum += m_sgXBuffer[i];
  }
  return static_cast<uint16_t>(sum / Config::SG_BUFFER_SIZE);
}

void SlideMechanism::resetBuffers() {
  for (int i = 0; i < Config::SG_BUFFER_SIZE; ++i) {
    m_sgYBuffer[i] = 0;
    m_sgXBuffer[i] = 0;
  }
  m_sgYIndex = 0;
  m_sgXIndex = 0;
}

void SlideMechanism::maybeSetBaselineUp(uint16_t avg) {
  if (!m_baselineUpSet && avg > 0) {
    m_baselineUp = avg;
    m_baselineUpSet = true;
  }
}

void SlideMechanism::maybeSetBaselineDown(uint16_t avg) {
  if (!m_baselineDownSet && avg > 0) {
    m_baselineDown = avg;
    m_baselineDownSet = true;
  }
}

bool SlideMechanism::dropConfirmedUp(uint16_t avg) {
  if (!m_baselineUpSet || m_baselineUp == 0) {
    return false;
  }
  if (avg < static_cast<uint16_t>(m_baselineUp * (1.0f - Config::DROP_PCT_TOP))) {
    if (++m_confirmUp >= Config::SGY_TOP_SAMPLES) {
      return true;
    }
  } else {
    if (m_confirmUp > 0) {
      m_confirmUp--;
    }
  }
  return false;
}

bool SlideMechanism::dropConfirmedDown(uint16_t avg) {
  if (!m_baselineDownSet || m_baselineDown == 0) {
    return false;
  }
  if (avg < static_cast<uint16_t>(m_baselineDown * (1.0f - Config::DROP_PCT_IMPACT))) {
    if (++m_confirmDown >= Config::SGY_CONFIRM_SAMPLES) {
      return true;
    }
  } else {
    if (m_confirmDown > 0) {
      m_confirmDown--;
    }
  }
  return false;
}

// ----------------- State handlers ------------------------------------------

void SlideMechanism::handleBegin() {
  m_stepperY.setMaxSpeed(10000);
  m_stepperX.setMaxSpeed(10000);
  m_stepperY.setAcceleration(2000);
  m_stepperX.setAcceleration(2000);
  m_driverY.pwm_autoscale(true);
  m_driverY.rms_current(1200);
  m_stepperY.moveTo(-1000000L);
  m_motionStart = millis();
  resetBuffers();
  m_baselineUpSet   = false;
  m_baselineDownSet = false;
  m_confirmUp       = 0;
  m_confirmDown     = 0;
  m_impactMonitoringY = false;
  m_phase = Phase::MovingUp;
  DEBUG_PRINTLN(F("Phase: MovingUp"));
}

void SlideMechanism::handleMovingUp() {
  if (!m_impactMonitoringY && millis() - m_motionStart > Config::WARMUP_MS) {
    m_impactMonitoringY = true;
  }
  if (m_impactMonitoringY) {
    uint16_t avg = averageY();
    maybeSetBaselineUp(avg);
    if (dropConfirmedUp(avg)) {
      m_stepperY.stop();
      m_stepperY.setCurrentPosition(m_stepperY.currentPosition());
      resetBuffers();
      m_baselineDownSet = false;
      m_confirmDown     = 0;
      m_impactMonitoringY = false;

      m_stepperX.setMaxSpeed(10000);
      m_stepperX.moveTo(-1000000L);
      m_motionStart = millis();
      m_impactMonitoringX = false;
      m_phase = Phase::MovingIn;
      DEBUG_PRINTLN(F("Phase: MovingIn"));
    }
  }
}

void SlideMechanism::handleMovingIn() {
  if (!m_impactMonitoringX && millis() - m_motionStart > 3000UL) {
    m_impactMonitoringX = true;
  }
  if (m_impactMonitoringX && averageX() < 90) {
    m_stepperX.stop();
    m_stepperX.setCurrentPosition(m_stepperX.currentPosition());
    delay(100);
    m_driverY.pwm_autoscale(true);
    m_driverY.rms_current(1200);
    m_stepperY.setMaxSpeed(10000);
    m_stepperY.moveTo(100000L);
    resetBuffers();
    m_baselineDownSet = false;
    m_confirmDown     = 0;
    m_motionStart = millis();
    m_impactMonitoringY = false;
    m_phase = Phase::MovingDown;
    DEBUG_PRINTLN(F("Phase: MovingDown"));
  }
}

void SlideMechanism::handleMovingDown() {
  if (!m_manualPwm && (millis() - m_motionStart > 15000UL)) {
    m_manualPwm = true;
    m_driverY.rms_current(500);
    m_driverY.pwm_autoscale(false);
    m_driverY.pwm_autograd(false);
    m_driverY.pwm_ofs(52);
    m_driverY.pwm_grad(10);
    m_driverY.en_spreadCycle(false);
    resetBuffers();
    m_baselineDownSet = false;
    m_confirmDown     = 0;
  }
  if (!m_impactMonitoringY && millis() - m_motionStart > 20000UL) {
    m_impactMonitoringY = true;
  }
  if (m_impactMonitoringY) {
    uint16_t avg = averageY();
    maybeSetBaselineDown(avg);
    if (dropConfirmedDown(avg)) {
      m_stepperY.stop();
      m_stepperY.setCurrentPosition(m_stepperY.currentPosition());
      // Move back up half a rotation to relieve pressure.
      const long halfRotation = 8000L;
      m_stepperY.moveTo(m_stepperY.currentPosition() - halfRotation);
      while (m_stepperY.distanceToGo() != 0) {
        m_stepperY.run();
      }
      m_manualPwm = false;
      m_driverX.rms_current(1800);
      m_driverX.microsteps(8);
      m_stepperX.moveTo(100000L);
      resetBuffers();
      m_motionStart = millis();
      m_impactMonitoringY = false;
      m_phase = Phase::MovingOut;
      DEBUG_PRINTLN(F("Phase: MovingOut"));
    }
  }
}

void SlideMechanism::handleMovingOut() {
  static int lowValueCount = 0;
  bool switchXActive = digitalRead(Config::LIMIT_SWITCH_X_PIN) == HIGH;
  if (!switchXActive && millis() - m_motionStart > 3000UL) {
    if (m_stepperX.distanceToGo() == 0) {
      m_stepperX.moveTo(m_stepperX.currentPosition() - 10000L);
    }
    if (averageX() < 80) {
      lowValueCount++;
      if (lowValueCount >= 150 && !m_reportedStuck) {
        if (m_onFinished) {
          m_onFinished(false);
        }
        m_reportedStuck = true;
      }
    } else {
      lowValueCount = 0;
    }
  }
  if (switchXActive) {
    m_stepperX.stop();
    m_stepperX.setCurrentPosition(m_stepperX.currentPosition());
    m_driverY.rms_current(500);
    m_stepperY.setMaxSpeed(1200);
    m_stepperY.moveTo(100000L);
    resetBuffers();
    m_motionStart = millis();
    m_impactMonitoringY = false;
    m_phase = Phase::Returning;
    DEBUG_PRINTLN(F("Phase: Returning"));
  }
}

void SlideMechanism::handleReturning() {
  bool switchYActive = digitalRead(Config::LIMIT_SWITCH_Y_PIN) == HIGH;
  if (switchYActive) {
    m_stepperY.stop();
    m_stepperY.setCurrentPosition(m_stepperY.currentPosition());
    delay(100);
    if (m_onFinished) {
      m_onFinished(!m_reportedStuck);
    }
    // Reset internal state for next cycle.
    m_busy = false;
    m_phase = Phase::Idle;
    m_impactMonitoringY = false;
    m_impactMonitoringX = false;
    m_manualPwm = false;
    m_reportedStuck = false;
    resetBuffers();
    m_baselineUpSet   = false;
    m_baselineDownSet = false;
    m_confirmUp       = 0;
    m_confirmDown     = 0;
    m_motionStart     = millis();
    DEBUG_PRINTLN(F("Cycle complete; returning to Idle"));
  }
}