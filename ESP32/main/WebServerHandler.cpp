#include "WebServerHandler.h"

WebServerHandler* WebServerHandler::s_instance = nullptr;

WebServerHandler::WebServerHandler(SlideMechanism& slide, Door& door)
  : m_slide(&slide),
    m_door(&door),
    m_server(80),
    m_lastReconnectAttempt(0)
{
}

void WebServerHandler::begin() {
  // Store instance pointer for static callback wrappers.
  s_instance = this;

  DEBUG_PRINTLN(F("Initialising WiFi connection…"));
  WiFi.mode(WIFI_STA);
  WiFi.begin(Credentials::WIFI_SSID, Credentials::WIFI_PASSWORD);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 10000UL) {
    delay(500);
    DEBUG_PRINT(F("."));
  }
  if (WiFi.status() == WL_CONNECTED) {
    DEBUG_PRINTLN(F("\nWiFi connected"));
    DEBUG_PRINT(F("IP address: "));
    DEBUG_PRINTLN(WiFi.localIP());
  } else {
    DEBUG_PRINTLN(F("\nFailed to connect to WiFi; will retry in background"));
  }

  m_server.on("/push", []() { if (WebServerHandler::s_instance) WebServerHandler::s_instance->handlePush(); });
  m_server.on("/door/open", []() { if (WebServerHandler::s_instance) WebServerHandler::s_instance->handleDoorOpen(); });
  m_server.on("/door/close", []() { if (WebServerHandler::s_instance) WebServerHandler::s_instance->handleDoorClose(); });
  m_server.on("/door/status", []() { if (WebServerHandler::s_instance) WebServerHandler::s_instance->handleDoorStatus(); });
  m_server.begin();
  DEBUG_PRINTLN(F("HTTP server started"));
}

void WebServerHandler::loop() {
  m_server.handleClient();
  checkWiFi();
}

// Callback invoked by SlideMechanism when a cycle starts.
void WebServerHandler::onSlideStarted(bool /*unused*/) {
  if (s_instance) {
    s_instance->sendFeedback("gestart");
  }
}

// Callback invoked by SlideMechanism when a cycle ends.
void WebServerHandler::onSlideFinished(bool success) {
  if (s_instance) {
    s_instance->sendFeedback(success ? "klaar" : "vast");
    // Close the door when finished.
    s_instance->m_door->close();
  }
}

void WebServerHandler::handlePush() {
  DEBUG_PRINTLN(F("HTTP request: /push"));
  if (!m_slide->isBusy()) {
    m_door->open();
    m_slide->start(WebServerHandler::onSlideStarted, WebServerHandler::onSlideFinished);
    m_server.send(200, "text/plain", "Schuif geactiveerd via WiFi");
  } else {
    m_server.send(409, "text/plain", "Schuif is momenteel bezig");
  }
}

void WebServerHandler::handleDoorOpen() {
  DEBUG_PRINTLN(F("HTTP request: /door/open"));
  m_door->open();
  m_server.send(200, "text/plain", "Deur geopend");
}

void WebServerHandler::handleDoorClose() {
  DEBUG_PRINTLN(F("HTTP request: /door/close"));
  m_door->close();
  m_server.send(200, "text/plain", "Deur dicht");
}

void WebServerHandler::handleDoorStatus() {
  DEBUG_PRINTLN(F("HTTP request: /door/status"));
  String json = String("{\"deur_status\":\"") + (m_door->isOpen() ? "open" : "dicht") + "\"}";
  m_server.send(200, "application/json", json);
}

void WebServerHandler::sendFeedback(const char* status) {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    String url = String("http://") + Config::WEB_SERVER_HOST + ":" + String(Config::WEB_SERVER_PORT) + "/schuif_feedback";
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    // Compose JSON payload.
    String payload = String("{\"status\":\"") + status + "\"}";
    int responseCode = http.POST(payload);
    if (responseCode > 0) {
      DEBUG_PRINTF("Feedback '%s' sent: %d\n", status, responseCode);
    } else {
      DEBUG_PRINTF("Feedback '%s' failed: %s\n", status, http.errorToString(responseCode).c_str());
    }
    http.end();
  } else {
    DEBUG_PRINTF("Cannot send feedback '%s': not connected to WiFi\n", status);
  }
}

void WebServerHandler::checkWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }
  if (millis() - m_lastReconnectAttempt < Config::WIFI_RECONNECT_INTERVAL_MS) {
    return;
  }
  m_lastReconnectAttempt = millis();
  DEBUG_PRINTLN(F("WiFi disconnected. Attempting reconnection…"));
  WiFi.disconnect();
  WiFi.begin(Credentials::WIFI_SSID, Credentials::WIFI_PASSWORD);
  unsigned long attemptStart = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - attemptStart < 10000UL) {
    delay(500);
    DEBUG_PRINT(F("."));
  }
  if (WiFi.status() == WL_CONNECTED) {
    DEBUG_PRINTLN(F("\nReconnected to WiFi"));
  } else {
    DEBUG_PRINTLN(F("\nFailed to reconnect to WiFi"));
  }
}