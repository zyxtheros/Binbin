#ifndef NET_CONNECT_H
#define NET_CONNECT_H

#ifndef WIFI_H
    #include <WiFi.h>
#endif
#ifndef WEB_SERVER_H
    #include <WebServer.h>
#endif
#include <Preferences.h>
#include <vector>

class NetworkInstance {
public:
    NetworkInstance(int ledPin = -1, int serverPort = 80);

    // Public variables
    WebServer server;
    bool isConnected;       // Whether a valid WiFi connection is active
    bool apMode;            // Whether the device is in Access Point mode
    String connectedSSID;   // SSID of the connected network

    // Public functions
    void begin();                   // Call once in setup()
    void loop();                    // Call every loop()
    void startAccessPoint();        // Start AP mode with setup page
    bool connectToWiFi();           // Load saved credentials and attempt connection
    void handleWebServer();         // Manually call server.handleClient()
    bool getConnectionStatus() const;
    String getConnectedSSID() const;

private:
    int statusLED;
    Preferences preferences;

    unsigned long lastBlink;
    bool ledState;
    bool manualOverride;    // When true, loop() won't touch the LED state (used when LED is turned on/off via web)

    String buildSetupPage(int networkCount, std::vector<String>& ssids);
    void setupAPRoutes();           // Register AP mode routes
    void setupControlRoutes();      // Register control page routes
    void handleRoot();              // Serve appropriate page based on state
    void handleSave();              // Save credentials and reboot
    void handleLEDOn();             // Turn LED on
    void handleLEDOff();            // Turn LED off
    void handleReset();             // Clear credentials and reboot
};

extern const char* controlPageHTML;

#endif