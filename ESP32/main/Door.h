/**
 * @file Door.h
 *
 * Encapsulation for the door servo mechanism. The Door class controls a
 * servo attached to a latch that secures the printer's enclosure. 
 */

#pragma once

#include <ESP32Servo.h>
#include <Arduino.h>
#include "Config.h"

class Door {
public:
  Door(uint8_t servoPin = Config::DOOR_SERVO_PIN,
       int openPos = Config::DOOR_POSITION_OPEN,
       int closePos = Config::DOOR_POSITION_CLOSE);

  void begin();
  void open();
  void close();

  bool isOpen() const;

private:
  Servo       m_servo;
  uint8_t     m_pin;
  int         m_openPos;
  int         m_closePos;
  bool        m_isOpen;
};