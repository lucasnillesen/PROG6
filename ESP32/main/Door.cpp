#include "Door.h"
#include "Debug.h"

Door::Door(uint8_t servoPin, int openPos, int closePos)
  : m_pin(servoPin), m_openPos(openPos), m_closePos(closePos), m_isOpen(false) {}

void Door::begin() {
  m_servo.attach(m_pin);
  close();
}

void Door::open() {
  m_servo.write(m_openPos);
  delay(300);
  m_isOpen = true;
  DEBUG_PRINTLN(F("Door opened"));
}

void Door::close() {
  m_servo.write(m_closePos);
  delay(300);
  m_isOpen = false;
  DEBUG_PRINTLN(F("Door closed"));
}

bool Door::isOpen() const {
  return m_isOpen;
}