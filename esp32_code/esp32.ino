#include <dummy.h>

#include <WiFi.h>
#include <PubSubClient.h>
#include <esp_sleep.h>
#include <driver/rtc_io.h>
#include <time.h>

#define uS_TO_S_FACTOR 1000000ULL

#define PI_RESPONSE_PIN GPIO_NUM_20
#define PI_PULSE_PIN GPIO_NUM_21

#define PI_SIGNAL_LIVE_PIN GPIO_NUM_12
#define PI_EXIT_PIN GPIO_NUM_13
#define MOSFET_PIN GPIO_NUM_1
#define SHUTDOWN_PIN GPIO_NUM_10

RTC_DATA_ATTR int bootCount = 0;
RTC_DATA_ATTR int syncAttemptCount = 0;
RTC_DATA_ATTR bool isNight = false;
RTC_DATA_ATTR int syncRetries = 0;
RTC_DATA_ATTR int timeToSleep = 20;
RTC_DATA_ATTR bool shouldBeOn = false;
RTC_DATA_ATTR bool keepOff = false;
RTC_DATA_ATTR bool exited = false;
RTC_DATA_ATTR int syncInterval = 50;

const char* WIFI_SSID = "";
const char* WIFI_PASS = "";

const char* MQTT_BROKER = "10.0.0.48";
const char* MQTT_CLIENT_ID = "esp32";

bool livestreamRequested = false;

const char* ntpServer = "pool.ntp.org";
const char* timeZone = "CST6CDT,M3.2.0/2:00:00,M11.1.0/2:00:00";

unsigned long timeUntilTimeout = millis();
unsigned long lastPiPulseMillis = millis();
unsigned long currentLoopMillis = millis();

WiFiClient espClient;
PubSubClient mqttClient(espClient);



bool sync_time() {

  time_t now;
  struct tm timeinfo;
  int retries = 0;

  wifi_setup();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Unable to connect to WiFi");
    return false;
  }

  Serial.print("Getting time...");
  configTzTime(timeZone, ntpServer);

  while (!getLocalTime(&timeinfo) && retries < 10) {

    Serial.print(".");
    delay(1000);
    retries++;
  }

  if (retries == 10) {
    Serial.println(" Failed to obtain time");
    return false;
  } else {
    Serial.print(" Success! Current time: ");
    int currentHour = timeinfo.tm_hour;
    Serial.println(currentHour);

    if (currentHour < 6 || currentHour > 20) {
      isNight = true;
      Serial.println("Time outside of range.");
    } else {
      isNight = false;
      Serial.println("Time inside of range.");
    }
    return true;
  }
}



void mqtt_callback(char* topic, byte* message, unsigned int length) {

  Serial.print("Message arrived on topic: ");
  Serial.print(topic);
  Serial.print(". Message: ");

  String messageTemp;

  for (int i = 0; i < length; i++) {
    messageTemp += (char)message[i];
  }

  Serial.println(messageTemp);

  if (String(topic) == "birdfeeder/esp32/commands" && messageTemp == "stream") {
    Serial.println("Received command to livestream.");
    livestreamRequested = true;
    mqttClient.publish("birdfeeder/esp32/status", "streamReceived");
    digitalWrite(PI_SIGNAL_LIVE_PIN, HIGH);
    delay(4000);
    digitalWrite(PI_SIGNAL_LIVE_PIN, LOW);
  }
  else if (String(topic) == "birdfeeder/esp32/commands" && messageTemp == "on") {
    mqttClient.publish("birdfeeder/esp32/status", "pi on");
    piOn();
    shouldBeOn = true;
    keepOff = false;
  }
  else if (String(topic) == "birdfeeder/esp32/commands" && messageTemp == "off") {
    mqttClient.publish("birdfeeder/esp32/status", "pi off");
    piOff();
    keepOff = true;
    exited = false;
  }
  else if (String(topic) == "birdfeeder/esp32/commands" && messageTemp == "exit") {
    mqttClient.publish("birdfeeder/esp32/status", "exitSignalReceived");
    piExit();
    exited = true;
  }
  else if (String(topic) == "birdfeeder/esp32/commands" && messageTemp == "restart_pi") {
    Serial.println("Pi restarting..");
    mqttClient.publish("birdfeeder/esp32/status", "restartPiSignalReceived");
    piOff();
    delay(2000);
    piOn();
    exited = false;
  }
  else if (String(topic) == "birdfeeder/esp32/commands" && messageTemp == "restart_esp32") {
    Serial.println("ESP32 Restarting..");
    mqttClient.publish("birdfeeder/esp32/status", "restartESP32SignalReceived");
    delay(1000);
    ESP.restart();
  }
}



void mqtt_connect() {

  mqttClient.setServer(MQTT_BROKER, 1883);
  mqttClient.setCallback(mqtt_callback);

  if (!mqttClient.connected()) {

    Serial.print("Attempting MQTT connection...");

    if (mqttClient.connect(MQTT_CLIENT_ID)) {
      Serial.println("Connected");
      mqttClient.subscribe("birdfeeder/esp32/commands");
    } else {
      Serial.print("failed, rc= ");
      Serial.println(mqttClient.state());
      Serial.println("Retrying soon..");
    }
  }
}



void timer_activated() {

  livestreamRequested = false;

  wifi_setup();

  timeUntilTimeout = millis() + 15000;
  lastPiPulseMillis = millis();
  currentLoopMillis = millis();
  bool timedOut = false;

  if (!keepOff && !exited) {

    Serial.println("Checking if Pi has timed out...");
    while (millis() < timeUntilTimeout && !keepOff && !exited) {

      currentLoopMillis = millis();

      mqttClient.loop();

      if (millis() - lastPiPulseMillis > 100 && digitalRead(PI_PULSE_PIN) == HIGH) {
        lastPiPulseMillis = currentLoopMillis;
      }

      if (currentLoopMillis - lastPiPulseMillis > 10000) {
        Serial.println("Pi has timed out.");
        timedOut = true;
        break;
      }
    
      delay(50);
    }
      if (livestreamRequested) {
        handleLiveOperation();
      }

      if (timedOut && !keepOff && !exited) {

        piOff();
        delay(3000);
        piOn();
      } else if (!keepOff && !exited) {
        Serial.println("Pi is responsive.");
      }
  } else {

    unsigned long keepOffTimeUntilTimeout = millis() + 5000;
    while (millis() < keepOffTimeUntilTimeout) {
      if (mqttClient.connected()) {
        mqttClient.loop();
      }
      delay(500);
    }

  }
 
  Serial.println("Going back to sleep.");
  wifi_shutdown();
  goToDeepSleep();
}

void handleLiveOperation() {

  lastPiPulseMillis = millis();
  currentLoopMillis = millis();
  bool timedOut = false;

  Serial.println("Monitoring Pi's status...");
  while (digitalRead(PI_RESPONSE_PIN) == LOW) {

    currentLoopMillis = millis();

    if (!mqttClient.connected()) {
      unsigned long startMillis = millis();
        mqttClient.connect(MQTT_CLIENT_ID);
        if (mqttClient.connected()) {
          Serial.println("MQTT client reconnected.");
          mqttClient.subscribe("birdfeeder/esp32/commands");
        }
        unsigned long durationMillis = millis() - startMillis;
        timeUntilTimeout += durationMillis;
        lastPiPulseMillis += durationMillis;
        currentLoopMillis += durationMillis;
      }
      mqttClient.loop();

    if (millis() - lastPiPulseMillis > 100 && digitalRead(PI_PULSE_PIN) == HIGH) {
      lastPiPulseMillis = currentLoopMillis;
    }

    if (currentLoopMillis - lastPiPulseMillis > 10000) {
      Serial.println("Pi has timed out.");
      timedOut = true;
      break;
    }

    delay(50);
  }

  if (timedOut) {

    piOff();
    delay(3000);
    piOn();
  }

  livestreamRequested = false;
  Serial.println("Exiting streaming function.");
}


bool wifi_setup() {

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting to Wifi...");

  unsigned long lastMillis = millis();

  while (WiFi.status() != WL_CONNECTED && millis() - lastMillis < 15000) {
    Serial.print(".");
    delay(1000);
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println(" Success.");
    Serial.println(WiFi.localIP());
    WiFi.onEvent(wifi_reconnect, ARDUINO_EVENT_WIFI_STA_DISCONNECTED);
    mqtt_connect();
    return true;
  } else {
    Serial.println("WiFi is unable to connect.");
    return false;
  }
}



void wifi_shutdown() {

  WiFi.removeEvent(ARDUINO_EVENT_WIFI_STA_DISCONNECTED);
  Serial.println("WiFi shutting down..");
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
}



void wifi_reconnect(WiFiEvent_t event, WiFiEventInfo_t info) {

  unsigned long startMillis = millis();

  Serial.print("Disconnected. Reason: ");
  Serial.println((int)info.wifi_sta_disconnected.reason);
  unsigned long lastMillis = millis();
  Serial.println("Trying to reconnect...");
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  while (WiFi.status() != WL_CONNECTED && millis() - lastMillis < 15000) {
    Serial.print(".");
    delay(1000);
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("WiFi reconnected.");
    mqtt_connect();
  } else {
    Serial.println("Unable to reconnect.");
  }

  unsigned long durationMillis = millis() - startMillis;
  timeUntilTimeout += durationMillis;
  lastPiPulseMillis += durationMillis;
  currentLoopMillis += durationMillis;
}



void piOn() {
  Serial.println("Turning Pi on..");
  digitalWrite(MOSFET_PIN, HIGH);
}



void piOff() {
  Serial.println("Sending Pi shutdown signal..");
  digitalWrite(SHUTDOWN_PIN, HIGH);

  unsigned long shutdownTimeout = millis() + 10000;
  bool shutdownSignalReceived = false;

  while (millis() < shutdownTimeout && digitalRead(PI_RESPONSE_PIN) == LOW){
    delay(100);
    if (digitalRead(PI_RESPONSE_PIN) == HIGH) {
      shutdownSignalReceived = true;
    }
  }
  digitalWrite(SHUTDOWN_PIN, LOW);

  if (shutdownSignalReceived){
    delay(10000);
    Serial.println("Pi has successfully shutdown.");
  }
  else {
    Serial.println("Pi failed to received shutdown signal. Forcing shutdown...");
  }
  digitalWrite(MOSFET_PIN, LOW);
}

void piExit() {
  Serial.println("Exiting Pi's python script..");
  digitalWrite(PI_EXIT_PIN, HIGH);
  delay(5000);
  digitalWrite(PI_EXIT_PIN, LOW);
}

void goToDeepSleep() {

  Serial.println("Entering deep sleep...");
  digitalWrite(PI_SIGNAL_LIVE_PIN, LOW);
  rtc_gpio_init(MOSFET_PIN);

  rtc_gpio_set_direction(MOSFET_PIN, RTC_GPIO_MODE_OUTPUT_ONLY);

  if (keepOff) {
    rtc_gpio_set_level(MOSFET_PIN, LOW);
  }
  else {
    if (!shouldBeOn){
      rtc_gpio_set_level(MOSFET_PIN, LOW);
    }
    else {
      rtc_gpio_set_level(MOSFET_PIN, HIGH);
    }
  }
  rtc_gpio_hold_en(MOSFET_PIN);
  esp_deep_sleep_start();
}



void setup() {

  pinMode(PI_SIGNAL_LIVE_PIN, OUTPUT);
  digitalWrite(PI_SIGNAL_LIVE_PIN, LOW);

  pinMode(PI_EXIT_PIN, OUTPUT);
  digitalWrite(PI_EXIT_PIN, LOW);

  pinMode(SHUTDOWN_PIN, OUTPUT);
  digitalWrite(SHUTDOWN_PIN, LOW);
  
  rtc_gpio_hold_dis(MOSFET_PIN);
  pinMode(MOSFET_PIN, OUTPUT);

  if (!shouldBeOn || keepOff) {
    digitalWrite(MOSFET_PIN, LOW);
  }
  else {
    digitalWrite(MOSFET_PIN, HIGH);
  }

  pinMode(PI_RESPONSE_PIN, INPUT_PULLDOWN);
  pinMode(PI_PULSE_PIN, INPUT_PULLDOWN);

  esp_sleep_pd_config(ESP_PD_DOMAIN_RTC_PERIPH, ESP_PD_OPTION_ON);
  esp_sleep_pd_config(ESP_PD_DOMAIN_RC_FAST, ESP_PD_OPTION_ON);
  esp_sleep_pd_config(ESP_PD_DOMAIN_XTAL, ESP_PD_OPTION_ON);

  esp_sleep_enable_timer_wakeup(timeToSleep * uS_TO_S_FACTOR);

  Serial.begin(115200);
  delay(500);

  bootCount++;
  syncAttemptCount++;
  Serial.println("Boot number:" + String(bootCount));

  esp_sleep_wakeup_cause_t wakeup_reason = esp_sleep_get_wakeup_cause();
  bool timeSuccessfullyObtained = false;


  if (syncAttemptCount == 1 && syncRetries < 10) {

    Serial.println("Syncing time...");
    timeSuccessfullyObtained = sync_time();

    if (!timeSuccessfullyObtained) {
      Serial.println("Failed to sync.");
      syncAttemptCount--;
      syncRetries++;
    } else {
      syncRetries = 0;
    }
  } else if (syncAttemptCount % syncInterval == 0) {

    Serial.println("Syncing time...");
    timeSuccessfullyObtained = sync_time();

    if (!timeSuccessfullyObtained) {
      Serial.println("Failed to sync.");
      syncAttemptCount--;
      syncRetries++;
    } else {
      syncRetries = 0;
    }
  }

  if (!isNight) {

    timeToSleep = 60;
    Serial.println("Currently day time.");
    syncInterval = 50;
    if (!keepOff && !shouldBeOn && !exited) {
      shouldBeOn = true;
      piOn();
    }

  } else {

      timeToSleep = 600;
      Serial.println("Currently night time.");
      syncInterval = 6;
      if (shouldBeOn) {

        shouldBeOn = false;
        piOff();
      }

      wifi_shutdown();
      goToDeepSleep();
    }



  switch (wakeup_reason) {

    case ESP_SLEEP_WAKEUP_TIMER:

      Serial.println("Wakeup caused by timer.");
      timer_activated();
      break;

    default:
      Serial.println("Unknown wakeup cause.");
      Serial.println("Going to sleep...");
      goToDeepSleep();
      break;
  }
}



void loop() {
}
