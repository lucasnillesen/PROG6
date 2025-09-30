// Define DEBUG_MODE before including Debug.h to enable serial logging. Remove
// or comment out this line in production to silence debug output.
#define DEBUG_MODE

/**
 * @file main.ino
 *
 * Entry point for the printer‑schuif firmware. This sketch wires together
 * the Door, SlideMechanism and WebServerHandler classes into a cohesive
 * application. The loop simply delegates to the web server and slide
 * mechanism; all the complex logic lives in the respective classes.
 */

#include "Debug.h"
#include "Door.h"
#include "SlideMechanism.h"
#include "WebServerHandler.h"

Door             g_door;
SlideMechanism   g_slide;
WebServerHandler g_server(g_slide, g_door);

void setup() {
  // Start serial port for debugging, only active when DEBUG_MODE is defined.
  DEBUG_BEGIN(115200);
  DEBUG_PRINTLN(F("Firmware starting…"));

  g_door.begin();
  g_slide.begin();
  g_server.begin();

  DEBUG_PRINTLN(F("Initialisation complete"));
}

void loop() {
  g_server.loop();
  g_slide.update();
}