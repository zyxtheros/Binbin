#include <Arduino.h>
#include "NetConnect.h"

// Create an instance of NetworkInstance
// Pass the pin number for the status LED (e.g., pin 2), or leave it as default (-1) if no LED is used
NetworkInstance net(23); // pass your LED pin

void setup() {
    Serial.begin(115200);
    net.begin();
}

void loop() {
    net.loop();
}