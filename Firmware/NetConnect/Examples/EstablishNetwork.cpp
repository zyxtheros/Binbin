#include "NetConnect.h"
 
// ===========================
// HTML PAGE
// ===========================
 
const char* landingPageHTML = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
    <title>ESP32 WiFi Setup</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial;
            margin: 40px;
            background: #f2f2f2;
        }
        .container {
            background: white;
            padding: 20px;
            border-radius: 10px;
            max-width: 400px;
            margin: auto;
        }
        input {
            width: 100%;
            padding: 10px;
            margin-top: 10px;
        }
        button {
            margin-top: 20px;
            padding: 10px;
            width: 100%;
        }
    </style>
</head>
<body>
<div class="container">
    <h2>ESP32 WiFi Setup</h2>
    <form action="/save" method="POST">
        <label>SSID</label>
        <input type="text" name="ssid">
        <label>Password</label>
        <input type="password" name="password">
        <button type="submit">Save & Connect</button>
    </form>
</div>
</body>
</html>
)rawliteral";
 
// ===========================
// CONSTRUCTOR
// ===========================
 
NetworkInstance::NetworkInstance(int ledPin, int serverPort)
    : isConnected(false), apMode(false), connectedSSID(""),
      server(serverPort), statusLED(ledPin), lastBlink(0), ledState(false) {
    if (statusLED != -1) {
        pinMode(statusLED, OUTPUT);
        digitalWrite(statusLED, LOW);
    }
}
 
// ===========================
// BEGIN (call once in setup)
// ===========================
 
void NetworkInstance::begin() {
    isConnected = connectToWiFi();
 
    if (!isConnected) {
        startAccessPoint();
    }
}
 
// ===========================
// LOOP (call every loop)
// ===========================
 
void NetworkInstance::loop() {
    if (WiFi.status() == WL_CONNECTED) {
        isConnected = true;
        connectedSSID = WiFi.SSID();
 
        if (statusLED != -1) {
            digitalWrite(statusLED, HIGH);
        }
    } else {
        isConnected = false;
 
        // Blink LED while disconnected
        if (statusLED != -1 && millis() - lastBlink > 500) {
            lastBlink = millis();
            ledState = !ledState;
            digitalWrite(statusLED, ledState);
        }
 
        // Start AP if not already in AP mode
        if (!apMode) {
            Serial.println("WiFi lost, starting AP mode...");
            startAccessPoint();
        }
    }
 
    // Handle web server requests when in AP mode
    if (apMode) {
        server.handleClient();
    }
}
 
// ===========================
// CONNECT TO WIFI
// ===========================
 
bool NetworkInstance::connectToWiFi() {
    preferences.begin("wifi", true);
    String ssid = preferences.getString("ssid", "");
    String password = preferences.getString("password", "");
    preferences.end();
 
    if (ssid == "") {
        Serial.println("No saved WiFi credentials");
        return false;
    }
 
    Serial.println("Connecting to WiFi: " + ssid);
 
    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid.c_str(), password.c_str());
 
    unsigned long startAttempt = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - startAttempt < 10000) {
        delay(500);
        Serial.print(".");
    }
 
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi connected!");
        Serial.print("IP Address: ");
        Serial.println(WiFi.localIP());
        connectedSSID = ssid;
        return true;
    }
 
    Serial.println("\nFailed to connect");
    return false;
}
 
// ===========================
// ACCESS POINT MODE
// ===========================
 
void NetworkInstance::startAccessPoint() {
    apMode = true;
 
    WiFi.mode(WIFI_AP);
    WiFi.softAP("ESP32-Setup");
 
    IPAddress IP = WiFi.softAPIP();
    Serial.println("Access Point started");
    Serial.print("AP IP Address: ");
    Serial.println(IP);
 
    setupRoutes();
    server.begin();
    Serial.println("Web server started");
}
 
// ===========================
// WEB SERVER ROUTES
// ===========================
 
void NetworkInstance::setupRoutes() {
    server.on("/", HTTP_GET, [this]() {
        handleRoot();
    });
 
    server.on("/save", HTTP_POST, [this]() {
        handleSave();
    });
}
 
void NetworkInstance::handleRoot() {
    server.send(200, "text/html", landingPageHTML);
}
 
void NetworkInstance::handleSave() {
    String ssid = server.arg("ssid");
    String password = server.arg("password");
 
    if (ssid.isEmpty() || password.isEmpty()) {
        server.send(400, "text/html",
            "<h2>Error: SSID and password cannot be empty.</h2>");
        return;
    }
 
    preferences.begin("wifi", false);
    preferences.putString("ssid", ssid);
    preferences.putString("password", password);
    preferences.end();
 
    Serial.println("Credentials saved. Rebooting...");
 
    server.send(200, "text/html",
        "<h2>Credentials Saved</h2>"
        "<p>Rebooting and attempting connection...</p>");
 
    delay(2000);
    ESP.restart();
}
 
// ===========================
// GETTERS / MISC
// ===========================
 
bool NetworkInstance::getConnectionStatus() const {
    return isConnected;
}
 
String NetworkInstance::getConnectedSSID() const {
    return connectedSSID;
}
 
void NetworkInstance::handleWebServer() {
    server.handleClient();
}