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
#include "esp_heap_caps.h"

static std::atomic<AsyncWebServerRequest*> sActiveHttpOta{nullptr};
struct OtaTrace {
  uint32_t id=0, startedMs=0, lastMs=0;
  size_t contentLength=0, bytes=0, chunks=0;
  uint8_t state=0; int updateError=0;
  uint32_t heapStart=0, largestStart=0, heapLast=0, largestLast=0;
  char stage[24]="idle";
};
static OtaTrace sTrace;
static std::atomic<uint32_t> sTraceSeq{0};
static void traceStage(const char* stage) {
  strlcpy(sTrace.stage, stage, sizeof(sTrace.stage)); sTrace.lastMs=millis();
  sTrace.heapLast=ESP.getFreeHeap();
  sTrace.largestLast=heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
  sTrace.updateError=Update.getError();
  Serial.printf("OTA_TRACE id=%u stage=%s state=%u bytes=%u chunks=%u err=%d heap=%u largest8=%u\n",
    sTrace.id,sTrace.stage,sTrace.state,(unsigned)sTrace.bytes,(unsigned)sTrace.chunks,sTrace.updateError,sTrace.heapLast,sTrace.largestLast);
}
static uint8_t otaState(AsyncWebServerRequest* request) { return request->_tempObject ? *static_cast<uint8_t*>(request->_tempObject) : 0; }
static void otaSetState(AsyncWebServerRequest* request, uint8_t state) { if(request->_tempObject)*static_cast<uint8_t*>(request->_tempObject)=state; sTrace.state=state; }
static bool otaStartState(AsyncWebServerRequest* request, bool filesystem) {
  if(request->_tempObject)return false;
  request->_tempObject=malloc(sizeof(uint8_t)); if(!request->_tempObject)return false;
  *static_cast<uint8_t*>(request->_tempObject)=0;
  AsyncWebServerRequest* expected=nullptr;
  if(!sActiveHttpOta.compare_exchange_strong(expected,request,std::memory_order_acq_rel)){otaSetState(request,1);return false;}
  sTrace=OtaTrace(); sTrace.id=++sTraceSeq; sTrace.startedMs=millis(); sTrace.contentLength=request->contentLength();
  sTrace.heapStart=ESP.getFreeHeap(); sTrace.largestStart=heap_caps_get_largest_free_block(MALLOC_CAP_8BIT); traceStage(filesystem?"fs_request":"fw_request");
  request->onDisconnect([request,filesystem](){
    traceStage("disconnect");
    if(otaState(request)==3)Update.abort();
    if(filesystem&&otaState(request)!=2)SPIFFS.begin(false);
    AsyncWebServerRequest* owner=request; sActiveHttpOta.compare_exchange_strong(owner,nullptr,std::memory_order_acq_rel);
    if(otaState(request)==2){delay(250);ESP.restart();}
  }); return true;
}
static bool otaApplyMd5(AsyncWebServerRequest* request){
  if(!request->hasHeader("X-MD5"))return true; String md5=request->getHeader("X-MD5")->value();
  if(md5.length()!=32)return false; for(size_t i=0;i<md5.length();++i)if(!isxdigit((unsigned char)md5[i]))return false; md5.toLowerCase(); return Update.setMD5(md5.c_str());
}
void otaHandle(){ArduinoOTA.handle();}
void otaInit(AsyncWebServer& server){
  ArduinoOTA.setPassword(remoteAuthPassword());
  ArduinoOTA.onStart([](){if(ArduinoOTA.getCommand()==U_SPIFFS){Serial.println("Start updating filesystem...");SPIFFS.end();}else Serial.println("Start updating firmware...");})
    .onEnd([](){Serial.println("\nUpdate finished.");}).onProgress([](unsigned int p,unsigned int t){Serial.printf("Progress: %u%%\r",(p*100)/t);})
    .onError([](ota_error_t e){if(!SPIFFS.begin(false))Serial.println("SPIFFS remount after OTA error failed");Serial.printf("Error[%u]\n",e);});
  ArduinoOTA.begin();
  IPAddress ip=WiFi.isConnected()?WiFi.localIP():WiFi.softAPIP(); Serial.println("OTA ready. IP: "+ip.toString());

  server.on("/ota_update",HTTP_GET,[](AsyncWebServerRequest* request){if(!remoteOtaAuthRequest(request))return;if(!SPIFFS.exists("/ota_update.html")){request->send(404,"text/plain","File not found");return;}auto* res=request->beginResponse(SPIFFS,"/ota_update.html","text/html");res->addHeader("Cache-Control","no-store");request->send(res);});
  server.on("/ota_trace",HTTP_GET,[](AsyncWebServerRequest* request){
    if(!remoteOtaAuthRequest(request))return;
    String j="{\"id\":"+String(sTrace.id)+",\"stage\":\""+String(sTrace.stage)+"\",\"state\":"+String(sTrace.state)+",\"content_length\":"+String((unsigned)sTrace.contentLength)+",\"bytes\":"+String((unsigned)sTrace.bytes)+",\"chunks\":"+String((unsigned)sTrace.chunks)+",\"update_error\":"+String(sTrace.updateError)+",\"heap_start\":"+String(sTrace.heapStart)+",\"largest_start\":"+String(sTrace.largestStart)+",\"heap_last\":"+String(sTrace.heapLast)+",\"largest_last\":"+String(sTrace.largestLast)+",\"age_ms\":"+String(millis()-sTrace.startedMs)+"}";
    request->send(200,"application/json",j);
  });

  server.on("/ota_update",HTTP_POST,
    [](AsyncWebServerRequest* request){
      if(!remoteOtaAuthRequest(request))return;if(!remoteMutationAllowed(request)){request->send(403,"text/plain","same-origin required");return;}
      bool ok=otaState(request)==2&&!Update.hasError(); traceStage(ok?"http_200":"http_500");
      auto* res=request->beginResponse(ok?200:500,"text/plain",ok?"OK":"FAIL");res->addHeader("Connection","close");request->send(res);
    },
    [](AsyncWebServerRequest* request,String filename,size_t index,uint8_t* data,size_t len,bool final){
      if(!request->authenticate(remoteAuthUser(),remoteAuthPassword())||!remoteMutationAllowed(request))return;
      if(index==0){
        if(!otaStartState(request,false))return; Serial.printf("OTA: Start '%s' contentLength=%u\n",filename.c_str(),(unsigned)request->contentLength());
        if(!filename.endsWith(".bin")||filename.equalsIgnoreCase("spiffs.bin")){otaSetState(request,1);traceStage("reject_name");return;}
        traceStage("begin_pre"); if(!Update.begin(UPDATE_SIZE_UNKNOWN,U_FLASH)){otaSetState(request,1);traceStage("begin_fail");Update.printError(Serial);return;}
        otaSetState(request,3);traceStage("begin_ok"); if(!otaApplyMd5(request)){Update.abort();otaSetState(request,1);traceStage("md5_fail");return;}
      }
      if(!request->_tempObject||otaState(request)!=3)return;
      if(len){sTrace.chunks++; if(Update.write(data,len)!=len){sTrace.bytes=index;Update.printError(Serial);Update.abort();otaSetState(request,1);traceStage("write_fail");return;}sTrace.bytes=index+len;if((sTrace.chunks&31)==0)traceStage("writing");}
      if(final){traceStage("end_pre");if(Update.end(true)){otaSetState(request,2);traceStage("end_ok");}else{Update.printError(Serial);Update.abort();otaSetState(request,1);traceStage("end_fail");}}
    });

  server.on("/ota_fs",HTTP_POST,
    [](AsyncWebServerRequest* request){if(!remoteOtaAuthRequest(request))return;if(!remoteMutationAllowed(request)){request->send(403,"text/plain","same-origin required");return;}bool ok=otaState(request)==2&&!Update.hasError();traceStage(ok?"fs_http_200":"fs_http_500");auto* res=request->beginResponse(ok?200:500,"text/plain",ok?"OK":"FAIL");res->addHeader("Connection","close");request->send(res);},
    [](AsyncWebServerRequest* request,String filename,size_t index,uint8_t* data,size_t len,bool final){
      if(!request->authenticate(remoteAuthUser(),remoteAuthPassword())||!remoteMutationAllowed(request))return;
      if(index==0){if(!otaStartState(request,true))return;if(!filename.equalsIgnoreCase("spiffs.bin")){otaSetState(request,1);traceStage("fs_reject_name");return;}SPIFFS.end();traceStage("fs_begin_pre");if(!Update.begin(UPDATE_SIZE_UNKNOWN,U_SPIFFS)){SPIFFS.begin(false);otaSetState(request,1);traceStage("fs_begin_fail");return;}otaSetState(request,3);traceStage("fs_begin_ok");if(!otaApplyMd5(request)){Update.abort();SPIFFS.begin(false);otaSetState(request,1);traceStage("fs_md5_fail");return;}}
      if(!request->_tempObject||otaState(request)!=3)return;if(len){sTrace.chunks++;if(Update.write(data,len)!=len){sTrace.bytes=index;Update.abort();SPIFFS.begin(false);otaSetState(request,1);traceStage("fs_write_fail");return;}sTrace.bytes=index+len;}
      if(final){traceStage("fs_end_pre");if(Update.end(false)){otaSetState(request,2);traceStage("fs_end_ok");}else{Update.abort();otaSetState(request,1);SPIFFS.begin(false);traceStage("fs_end_fail");}}
    });
}
