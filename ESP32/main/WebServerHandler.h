/**
 * @file WebServerHandler.h
 *
 * Encapsulates the ESP32 Wi‑Fi connectivity and HTTP server. The
 * WebServerHandler class manages connecting to the specified Wi‑Fi network,
 * exposes a handful of REST endpoints and relays cycle progress back to a remote Flask server. The
 * handler owns no hardware itself; instead it operates on references to a
 * SlideMechanism and Door instance supplied at construction.
 */

#pragma once

#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <Arduino.h>
#include "Config.h"
#include "credentials.h"
#include "SlideMechanism.h"
#include "Door.h"
#include "Debug.h"

class WebServerHandler {
public:
  WebServerHandler(SlideMechanism& slide, Door& door);
  void begin();
  void loop();

private:
  static void onSlideStarted(bool /*unused*/);
  static void onSlideFinished(bool success);

  void handlePush();
  void handleDoorOpen();
  void handleDoorClose();
  void handleDoorStatus();
  void sendFeedback(const char* status);
  void checkWiFi();

  SlideMechanism* m_slide;
  Door*          m_door;
  WebServer m_server;

  unsigned long m_lastReconnectAttempt;
  static WebServerHandler* s_instance;
};