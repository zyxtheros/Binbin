#include "NetConnect.h"

// ===========================
// CONTROL PAGE HTML
// ===========================

const char* controlPageHTML = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
    <title>ESP32 Control</title>
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
            text-align: center;
        }
        .btn {
            display: inline-block;
            margin-top: 20px;
            padding: 15px;
            width: 80%;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            cursor: pointer;
            user-select: none;
            -webkit-user-select: none;
        }
        .btn-led {
            background-color: #28a745;
            color: white;
        }
        .btn-led:active {
            background-color: #1e7e34;
        }
        .btn-reset {
            background-color: #dc3545;
            color: white;
        }
        .btn-reset:hover {
            background-color: #bd2130;
        }
        p.hint {
            color: #888;
            font-size: 13px;
            margin-top: 8px;
        }
    </style>
</head>
<body>
<div class="container">
    <h2>ESP32 Control</h2>
    <p>Connected &#10003;</p>

    <button class="btn btn-led"
        onmousedown="fetch('/led/off')"  onmouseup="fetch('/led/on')"
        ontouchstart="fetch('/led/off')" ontouchend="fetch('/led/on')">
        Turn LED off
    </button>
    <p class="hint">Status LED turns off while button is held</p>

    <br>

    <button class="btn btn-reset" onclick="resetCredentials()">
        Reset Network Credentials
    </button>
    <p class="hint">Clears saved WiFi and restarts setup</p>
</div>
<script>
    function resetCredentials() {
        if (confirm("This will erase saved WiFi credentials and restart. Continue?")) {
            fetch('/reset').then(() => {
                document.body.innerHTML = "<div style='text-align:center;margin-top:80px'><h2>Resetting...</h2><p>Connect to <b>ESP32-Setup</b> to reconfigure.</p></div>";
            });
        }
    }
</script>
</body>
</html>
)rawliteral";

// ===========================
// CONSTRUCTOR
// ===========================

NetworkInstance::NetworkInstance(int ledPin, int serverPort)
    : isConnected(false), apMode(false), connectedSSID(""),
      server(serverPort), statusLED(ledPin), lastBlink(0), ledState(false),
      manualOverride(false) {
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

    if (isConnected) {
        // WiFi connected — serve control page
        setupControlRoutes();
        server.begin();
        Serial.println("Control server started");
    } else {
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

        // Only write HIGH if the button isn't being held
        if (!manualOverride && statusLED != -1) {
            digitalWrite(statusLED, HIGH);
        }
    } else {
        isConnected = false;
        manualOverride = false; // Clear override if WiFi drops

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

    server.handleClient();
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

    // Start AP first, then scan using AP_STA mode (avoids mode switching disrupting AP)
    WiFi.mode(WIFI_AP_STA);
    WiFi.softAP("ESP32-Setup");
    delay(500); // Allow AP to fully initialize before scanning

    IPAddress IP = WiFi.softAPIP();
    Serial.println("Access Point started");
    Serial.print("AP IP Address: ");
    Serial.println(IP);

    Serial.println("Scanning for networks...");
    int networkCount = WiFi.scanNetworks();
    Serial.println(String(networkCount) + " networks found");

    std::vector<String> ssids;
    for (int i = 0; i < networkCount; i++) {
        ssids.push_back(WiFi.SSID(i));
    }
    WiFi.scanDelete();

    // Build and register setup page with scan results
    String setupPageHTML = buildSetupPage(networkCount, ssids);

    server.on("/", HTTP_GET, [this, setupPageHTML]() {
        server.send(200, "text/html", setupPageHTML);
    });

    server.on("/save", HTTP_POST, [this]() {
        handleSave();
    });

    server.begin();
    Serial.println("Web server started");
}

// ===========================
// BUILD SETUP PAGE
// ===========================

String NetworkInstance::buildSetupPage(int networkCount, std::vector<String>& ssids) {
    String dropdown = "";

    if (networkCount > 0) {
        dropdown += "<label>SSID</label>";
        dropdown += "<select id='ssidSelect' onchange='onDropdownChange(this)'>";
        for (int i = 0; i < networkCount; i++) {
            dropdown += "<option value='" + ssids[i] + "'>" + ssids[i] + "</option>";
        }
        dropdown += "<option value='__manual__'>Enter manually...</option>";
        dropdown += "</select>";
        dropdown += "<input type='text' id='ssidManual' name='ssid' placeholder='Enter SSID' style='display:none;margin-top:8px'>";
    } else {
        // No networks found — just show a text input
        dropdown += "<label>SSID</label>";
        dropdown += "<input type='text' name='ssid' placeholder='Enter SSID'>";
    }

    String page = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
    <title>ESP32 WiFi Setup</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial; margin: 40px; background: #f2f2f2; }
        .container { background: white; padding: 20px; border-radius: 10px; max-width: 400px; margin: auto; }
        input, select { width: 100%; padding: 10px; margin-top: 10px; box-sizing: border-box; }
        button { margin-top: 20px; padding: 10px; width: 100%; }
    </style>
</head>
<body>
<div class="container">
    <h2>ESP32 WiFi Setup</h2>
    <form action="/save" method="POST" onsubmit="prepareSubmit()">
)rawliteral";

    page += dropdown;

    page += R"rawliteral(
        <label>Password</label>
        <input type="password" name="password" placeholder="Enter Password">
        <button type="submit">Save &amp; Connect</button>
    </form>
</div>
<script>
    function onDropdownChange(sel) {
        var manual = document.getElementById('ssidManual');
        if (sel.value === '__manual__') {
            manual.style.display = 'block';
            manual.name = 'ssid';
            sel.name = '';
        } else {
            manual.style.display = 'none';
            manual.name = '';
            sel.name = 'ssid';
        }
    }
    // Ensure the select has name='ssid' on load
    window.onload = function() {
        var sel = document.getElementById('ssidSelect');
        if (sel) sel.name = 'ssid';
    }
</script>
</body>
</html>
)rawliteral";

    return page;
}

// ===========================
// CONTROL PAGE ROUTES
// ===========================

void NetworkInstance::setupControlRoutes() {
    server.on("/", HTTP_GET, [this]() {
        server.send(200, "text/html", controlPageHTML);
    });

    server.on("/led/on", HTTP_GET, [this]() {
        handleLEDOn();
    });

    server.on("/led/off", HTTP_GET, [this]() {
        handleLEDOff();
    });

    server.on("/reset", HTTP_GET, [this]() {
        handleReset();
    });
}

void NetworkInstance::handleLEDOn() {
    manualOverride = false;
    if (statusLED != -1) {
        digitalWrite(statusLED, HIGH);
        Serial.println("LED turned ON");
    }
    server.send(200, "text/plain", "ON");
}

void NetworkInstance::handleLEDOff() {
    manualOverride = true;
    if (statusLED != -1) {
        digitalWrite(statusLED, LOW);
        Serial.println("LED turned OFF");
    }
    server.send(200, "text/plain", "OFF");
}

void NetworkInstance::handleReset() {
    preferences.begin("wifi", false);
    preferences.clear();
    preferences.end();

    Serial.println("Credentials cleared. Rebooting...");
    server.send(200, "text/plain", "Resetting");

    delay(1000);
    ESP.restart();
}

// ===========================
// HANDLE SAVE (AP mode)
// ===========================

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