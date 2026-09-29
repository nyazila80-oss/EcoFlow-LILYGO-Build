#include "ota.h"

#include <Arduino.h>
#include <ArduinoOTA.h>
#include <Update.h>
#include <wi-fi.h>
#include <FS.h>
#include <SPIFFS.h>
#include "web.h"
#include <atomic>
#include <ctype.h>

// ESPAsyncWebServer frees request->_tempObject in its request destructor.
// Store the upload state in malloc-owned memory, never as an integer pointer.
static std::atomic<AsyncWebServerRequest*> sActiveHttpOta{nullptr};
static uint8_t otaState(AsyncWebServerRequest* request) {
  return request->_tempObject ? *static_cast<uint8_t*>(request->_tempObject) : 0;
}
static bool otaStartState(AsyncWebServerRequest* request, bool filesystem) {
  if (request->_tempObject) return false;
  request->_tempObject = malloc(sizeof(uint8_t));
  if (!request->_tempObject) return false;
  *static_cast<uint8_t*>(request->_tempObject) = 0;
  AsyncWebServerRequest* expected = nullptr;
  if (!sActiveHttpOta.compare_exchange_strong(expected, request, std::memory_order_acq_rel)) {
    *static_cast<uint8_t*>(request->_tempObject) = 1;
    return false;
  }
  // Update is a process-global writer. Hold ownership until disconnect so an
  // aborted upload cannot leave it busy, and a second HTTP upload cannot
  // overwrite the first one's partition or success result.
  request->onDisconnect([request, filesystem]() {
    if (otaState(request) == 3) {
      Update.abort();
    }
    if (filesystem && otaState(request) != 2) SPIFFS.begin(false);
    AsyncWebServerRequest* owner = request;
    sActiveHttpOta.compare_exchange_strong(owner, nullptr, std::memory_order_acq_rel);
    if (otaState(request) == 2) {
      delay(250);
      ESP.restart();
    }
  });
  return true;
}
static void otaSetState(AsyncWebServerRequest* request, uint8_t state) {
  if (request->_tempObject) *static_cast<uint8_t*>(request->_tempObject) = state;
}
static bool otaApplyMd5(AsyncWebServerRequest* request) {
  if (!request->hasHeader("X-MD5")) return true;
  String md5 = request->getHeader("X-MD5")->value();
  if (md5.length() != 32) return false;
  for (size_t i=0; i<md5.length(); ++i) {
    if (!isxdigit((unsigned char)md5[i])) return false;
  }
  md5.toLowerCase();
  return Update.setMD5(md5.c_str());
}

void otaHandle() {
  ArduinoOTA.handle();
}

void otaInit(AsyncWebServer& server) {

  // AUDIT20.1: protect network OTA with the same generated admin secret.
  ArduinoOTA.setPassword(remoteAuthPassword());

  // --- OTA (ArduinoOTA) ---
  ArduinoOTA.onStart([](){
              const int cmd = ArduinoOTA.getCommand();
              if (cmd == U_SPIFFS) {
                Serial.println("Start updating filesystem...");
                // PlatformIO uploadfsota uses ArduinoOTA/U_SPIFFS, not /ota_fs.
                // The mounted filesystem must be released before Update can write it.
                SPIFFS.end();
              } else {
                Serial.println("Start updating firmware...");
              }
            })
            .onEnd([](){ Serial.println("\nUpdate finished."); })
            .onProgress([](unsigned int progress, unsigned int total){
              Serial.printf("Progress: %u%%\r", (progress * 100) / total);
            })
            .onError([](ota_error_t error){
              // A failed filesystem OTA may leave SPIFFS unmounted after onStart().
              // Remounting is safe for firmware OTA too and avoids requiring a reboot
              // merely to recover the old filesystem.
              if (!SPIFFS.begin(false)) Serial.println("SPIFFS remount after OTA error failed");
              Serial.printf("Error[%u]: ", error);
              if (error == OTA_AUTH_ERROR) Serial.println("Auth Failed");
              else if (error == OTA_BEGIN_ERROR) Serial.println("Begin Failed");
              else if (error == OTA_CONNECT_ERROR) Serial.println("Connect Failed");
              else if (error == OTA_RECEIVE_ERROR) Serial.println("Receive Failed");
              else if (error == OTA_END_ERROR) Serial.println("End Failed");
            });

  ArduinoOTA.begin();

  IPAddress ip = WiFi.isConnected() ? WiFi.localIP() : WiFi.softAPIP();
  Serial.println("OTA ready. IP: " + ip.toString());

  // === OTA Manual Update: form page (GET) ===
  server.on("/ota_update", HTTP_GET, [](AsyncWebServerRequest* request){
    if(!remoteOtaAuthRequest(request)) return;
    if (!SPIFFS.exists("/ota_update.html")) {
      request->send(404, "text/plain", "File not found");
      return;
    }
    AsyncWebServerResponse* res = request->beginResponse(SPIFFS, "/ota_update.html", "text/html");
    res->addHeader("Cache-Control", "no-store");
    request->send(res);
  });

  // POST: streaming upload + final response
  server.on("/ota_update", HTTP_POST,
    // Called once the upload is finished (or error flagged)
    [](AsyncWebServerRequest* request){
      if(!remoteOtaAuthRequest(request)) return;
      if(!remoteMutationAllowed(request)){request->send(403,"text/plain","same-origin required");return;}
      // A request succeeds only after its own upload reached Update.end().
      // Update.hasError() alone can be false for a missing/rejected upload.
      const bool ok = otaState(request) == 2 && !Update.hasError();

      // Schedule reboot only after the client connection is really closed,
      // so the browser can receive the 200 OK and won't show a network error.
      AsyncWebServerResponse *res =
        request->beginResponse(ok ? 200 : 500, "text/plain", ok ? "OK" : "FAIL");
      res->addHeader("Connection", "close");
      request->send(res);
    },

    // Called repeatedly with file chunks
    [](AsyncWebServerRequest* request, String filename, size_t index,
       uint8_t *data, size_t len, bool final)
    {
      if(!request->authenticate(remoteAuthUser(), remoteAuthPassword()) || !remoteMutationAllowed(request)) return;
      if (index == 0) {
        if (!otaStartState(request, false)) return;
        Serial.printf("OTA: Start '%s' (contentLength=%u)\n",
                      filename.c_str(), (unsigned)request->contentLength());
        if (!filename.endsWith(".bin") || filename.equalsIgnoreCase("spiffs.bin")) {
          Serial.println("OTA: rejected filename (firmware .bin required)");
          otaSetState(request, 1);
          return;
        }
        // start with max available size
        if (!Update.begin(UPDATE_SIZE_UNKNOWN, U_FLASH)) {
          Update.printError(Serial);
          otaSetState(request, 1);
          return;
        }
        otaSetState(request, 3);
        // An invalid optional checksum must not silently disable verification.
        if (!otaApplyMd5(request)) {
          Serial.println("OTA: invalid X-MD5 header");
          Update.abort(); otaSetState(request, 1); return;
        }
      }

      if (!request->_tempObject || otaState(request) != 3) return;

      if (len) {
        if (Update.write(data, len) != len) {
          Update.printError(Serial);
          Update.abort();
          otaSetState(request, 1);
          return;
        }
      }

      if (final) {
        if (Update.end(true)) {
          Serial.printf("OTA: End ok, total=%u bytes\n", (unsigned)(index + len));
          otaSetState(request, 2);
        } else {
          Update.printError(Serial);
          Update.abort();
          otaSetState(request, 1);
        }
      }
    }
  );

  // === SPIFFS filesystem image OTA ===
  server.on("/ota_fs", HTTP_POST,
    [](AsyncWebServerRequest* request){
      if(!remoteOtaAuthRequest(request)) return;
      if(!remoteMutationAllowed(request)){request->send(403,"text/plain","same-origin required");return;}
      const bool ok=otaState(request) == 2 && !Update.hasError();
      AsyncWebServerResponse* res=request->beginResponse(ok?200:500,"text/plain",ok?"OK":"FAIL");
      res->addHeader("Connection","close");
      request->send(res);
    },
    [](AsyncWebServerRequest* request, String filename, size_t index, uint8_t *data, size_t len, bool final){
      if(!request->authenticate(remoteAuthUser(), remoteAuthPassword()) || !remoteMutationAllowed(request)) return;
      if(index==0){
        if (!otaStartState(request, true)) return;
        Serial.printf("OTA FS: Start '%s' size=%u\n",filename.c_str(),(unsigned)request->contentLength());
        if(!filename.equalsIgnoreCase("spiffs.bin")){
          Serial.println("OTA FS: rejected filename (spiffs.bin required)");
          otaSetState(request, 1);
          return;
        }
        SPIFFS.end();
        if(!Update.begin(UPDATE_SIZE_UNKNOWN, U_SPIFFS)){ Update.printError(Serial); SPIFFS.begin(false); otaSetState(request,1); return; }
        otaSetState(request,3);
        if(!otaApplyMd5(request)){
          Serial.println("OTA FS: invalid X-MD5 header");
          Update.abort(); SPIFFS.begin(false); otaSetState(request,1); return;
        }
      }
      if(!request->_tempObject || otaState(request) != 3) return;
      if(len && Update.write(data,len)!=len) {
        Update.printError(Serial);
        Update.abort();
        SPIFFS.begin(false);
        otaSetState(request,1);
        return;
      }
      if(final){
        // buildfs produces a full partition image. Reject a truncated SPIFFS
        // upload instead of letting end(true) activate partial filesystem data.
        if(Update.end(false)) { Serial.printf("OTA FS: End ok, total=%u bytes\n",(unsigned)(index+len)); otaSetState(request,2); }
        else { Update.printError(Serial); Update.abort(); otaSetState(request,1); SPIFFS.begin(false); }
      }
    }
  );

}
