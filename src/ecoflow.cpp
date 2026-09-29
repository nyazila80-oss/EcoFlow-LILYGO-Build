#include "config.h"
#include <atomic>
#include "web.h"

// AUDIT19.15.16: force bounded WebSocket CAN logging in this translation unit.
// CANDUMP previously existed only in main.cpp, so it did NOT affect ecoflow.cpp;
// the fallback path appended indefinitely to global String canLog when txlogging was enabled.
#ifndef CANDUMP
#define CANDUMP 1
#endif
#include "ecoflow.h"
#include "can.h"   // must provide sendCANFrame()
#include <string.h>
#include <freertos/semphr.h>

//EcoFlow PowerStream serial (from C4), 16 chars + null
static char SerialPS[17] = {0};
static std::atomic<uint32_t> g_peerSerialSeq{0};

String getPeerSerial() {
  char out[17];
  for (;;) {
    const uint32_t a=g_peerSerialSeq.load(std::memory_order_acquire);
    if (a & 1U) { taskYIELD(); continue; }
    memcpy(out,SerialPS,sizeof(out));
    const uint32_t b=g_peerSerialSeq.load(std::memory_order_acquire);
    if (a==b && !(b&1U)) break;
  }
  out[16]='\0';
  return String(out);
}

extern std::atomic<uint32_t> can_rx_count;
extern std::atomic<uint32_t> can_rx_dropped;
extern std::atomic<uint32_t> can_decoded;

extern float inputWatt;
extern float outputWatt;


// ================= XOR state =================
std::atomic<uint8_t> xor3C{0}; // Save C4 XOR
std::atomic<uint8_t> xor8C{0}; // Save 8C XOR
std::atomic<uint8_t> xor24{0}; // Save 8C XOR
std::atomic<uint8_t> xorCB{0}; // Save CB but only for 2031 & 2033 BMS Limits
static std::atomic<int> g_psObservedUpper{-1};
static std::atomic<int> g_psObservedLower{-1};
static std::atomic<uint32_t> g_psObservedUpperMs{0};
static std::atomic<uint32_t> g_psObservedLowerMs{0};

int ecoflowObservedUpperLimit(){ return g_psObservedUpper.load(std::memory_order_acquire); }
int ecoflowObservedLowerLimit(){ return g_psObservedLower.load(std::memory_order_acquire); }
uint32_t ecoflowObservedUpperAgeMs(){ const uint32_t t=g_psObservedUpperMs.load(std::memory_order_acquire); return t ? millis()-t : 0xFFFFFFFFUL; }
uint32_t ecoflowObservedLowerAgeMs(){ const uint32_t t=g_psObservedLowerMs.load(std::memory_order_acquire); return t ? millis()-t : 0xFFFFFFFFUL; }
std::atomic<uint8_t> xorCounter{0}; // Incrementing TX XOR byte, shared across decoder/main contexts

// ================= AUDIT20.4.3 RAW CB forensic recorder =================
// Passive raw-CAN recorder. Captures successful TX frames and all received TWAI
// frames before the normal RX prefilter. A validated decoded CB/2031 or CB/2033
// only marks the trigger; it does not transmit anything.
struct __attribute__((packed)) CbRawRec {
  uint32_t ms;
  uint32_t id;
  uint8_t flags;      // bit0=TX, bit1=EXT, bit2=RTR
  uint8_t dlc;
  uint8_t data[8];
};
static_assert(sizeof(CbRawRec)==18, "CbRawRec packing changed");
static constexpr uint16_t CBRAW_PRE_CAP = 160;
static constexpr uint16_t CBRAW_POST_CAP = 160;
static constexpr uint32_t CBRAW_POST_MS = 5000;
static CbRawRec g_cbRawPre[CBRAW_PRE_CAP], g_cbRawPost[CBRAW_POST_CAP];
static uint16_t g_cbRawPreHead=0, g_cbRawPreCount=0, g_cbRawPostCount=0;
static bool g_cbRawTriggered=false, g_cbRawFrozen=false;
static uint32_t g_cbRawTriggerMs=0;
static uint16_t g_cbRawTriggerTracker=0;
static portMUX_TYPE g_cbRawMux = portMUX_INITIALIZER_UNLOCKED;

void ecoflowCbRecorderRawFrame(bool tx,uint32_t id,bool ext,bool rtr,const uint8_t* data,uint8_t dlc){
  CbRawRec r={}; r.ms=millis(); r.id=id&0x1FFFFFFFUL;
  r.flags=(tx?1U:0U)|(ext?2U:0U)|(rtr?4U:0U); r.dlc=(dlc>8)?8:dlc;
  if(data && r.dlc) memcpy(r.data,data,r.dlc);
  portENTER_CRITICAL(&g_cbRawMux);
  if(!g_cbRawFrozen){
    if(!g_cbRawTriggered){
      g_cbRawPre[g_cbRawPreHead]=r;
      g_cbRawPreHead=(uint16_t)((g_cbRawPreHead+1U)%CBRAW_PRE_CAP);
      if(g_cbRawPreCount<CBRAW_PRE_CAP) ++g_cbRawPreCount;
    } else {
      if(g_cbRawPostCount<CBRAW_POST_CAP) g_cbRawPost[g_cbRawPostCount++]=r;
      if(g_cbRawPostCount>=CBRAW_POST_CAP || (uint32_t)(r.ms-g_cbRawTriggerMs)>=CBRAW_POST_MS) g_cbRawFrozen=true;
    }
  }
  portEXIT_CRITICAL(&g_cbRawMux);
}

void ecoflowCbRecorderTrigger(uint16_t tracker){
  if(tracker!=0x2031 && tracker!=0x2033) return;
  const uint32_t now=millis();
  portENTER_CRITICAL(&g_cbRawMux);
  if(!g_cbRawTriggered && !g_cbRawFrozen){
    g_cbRawTriggered=true; g_cbRawTriggerMs=now; g_cbRawTriggerTracker=tracker;
  }
  portEXIT_CRITICAL(&g_cbRawMux);
}

void ecoflowCbRecorderTick(){
  const uint32_t now=millis();
  portENTER_CRITICAL(&g_cbRawMux);
  if(g_cbRawTriggered&&!g_cbRawFrozen&&(uint32_t)(now-g_cbRawTriggerMs)>=CBRAW_POST_MS) g_cbRawFrozen=true;
  portEXIT_CRITICAL(&g_cbRawMux);
}
void ecoflowCbRecorderClear(){
  portENTER_CRITICAL(&g_cbRawMux);
  g_cbRawPreHead=0;g_cbRawPreCount=0;g_cbRawPostCount=0;g_cbRawTriggered=false;g_cbRawFrozen=false;
  g_cbRawTriggerMs=0;g_cbRawTriggerTracker=0;
  portEXIT_CRITICAL(&g_cbRawMux);
}
String ecoflowCbRecorderStatusJson(){
  bool trig,frozen;uint32_t tms;uint16_t trk,pre,post;
  portENTER_CRITICAL(&g_cbRawMux);
  trig=g_cbRawTriggered;frozen=g_cbRawFrozen;tms=g_cbRawTriggerMs;trk=g_cbRawTriggerTracker;pre=g_cbRawPreCount;post=g_cbRawPostCount;
  portEXIT_CRITICAL(&g_cbRawMux);
  String j;j.reserve(240);
  j=String("{\"ok\":true,\"mode\":\"raw-can\",\"triggered\":")+(trig?"true":"false")+
    ",\"frozen\":"+(frozen?String("true"):String("false"))+
    ",\"pre_entries\":"+String(pre)+",\"post_entries\":"+String(post)+
    ",\"total_entries\":"+String((uint32_t)pre+(uint32_t)post)+
    ",\"pre_capacity\":"+String(CBRAW_PRE_CAP)+",\"post_capacity\":"+String(CBRAW_POST_CAP)+
    ",\"trigger_tracker\":"+String(trk)+",\"trigger_ms\":"+String(tms)+"}";
  return j;
}

// Bounded page dump: no full-buffer malloc and no giant String allocation.
// offset is chronological across PRE then POST; limit is clamped to 32 rows.
String ecoflowCbRecorderDumpPage(uint16_t offset,uint8_t limit){
  if(limit==0||limit>32) limit=32;
  uint16_t pc,qc,head;bool trig,frozen;uint32_t tms;uint16_t trk;
  portENTER_CRITICAL(&g_cbRawMux);
  pc=g_cbRawPreCount;qc=g_cbRawPostCount;head=g_cbRawPreHead;trig=g_cbRawTriggered;frozen=g_cbRawFrozen;tms=g_cbRawTriggerMs;trk=g_cbRawTriggerTracker;
  portEXIT_CRITICAL(&g_cbRawMux);
  const uint16_t total=(uint16_t)(pc+qc);
  if(offset>total) offset=total;
  uint16_t end=(uint16_t)min((uint32_t)total,(uint32_t)offset+(uint32_t)limit);
  String out; out.reserve(256+(size_t)(end-offset)*72U);
  if(offset==0){
    out+="# EcoFlow RAW CB forensic recorder AUDIT20.4.3\n";
    out+="# raw CAN frames; PRE is bounded by frame capacity, POST by 5 s or capacity\n";
    out+="# triggered="+String(trig?"1":"0")+" frozen="+String(frozen?"1":"0")+" trigger_tracker=0x";
    char h[16];snprintf(h,sizeof(h),"%04X",trk);out+=h;out+=" trigger_ms="+String(tms)+"\n";
    out+="idx,phase,ms,dir,id,ext,rtr,dlc,data\n";
  }
  const uint16_t preStart=(uint16_t)((head+CBRAW_PRE_CAP-pc)%CBRAW_PRE_CAP);
  for(uint16_t i=offset;i<end;i++){
    CbRawRec r={}; const char* phase;
    portENTER_CRITICAL(&g_cbRawMux);
    if(i<pc){r=g_cbRawPre[(preStart+i)%CBRAW_PRE_CAP];phase="PRE";}else{r=g_cbRawPost[i-pc];phase="POST";}
    portEXIT_CRITICAL(&g_cbRawMux);
    char b[112];snprintf(b,sizeof(b),"%u,%s,%lu,%s,0x%08lX,%u,%u,%u,",(unsigned)i,phase,(unsigned long)r.ms,(r.flags&1)?"TX":"RX",(unsigned long)r.id,(r.flags&2)?1:0,(r.flags&4)?1:0,(unsigned)r.dlc);out+=b;
    for(uint8_t k=0;k<r.dlc;k++){char x[3];snprintf(x,sizeof(x),"%02X",r.data[k]);out+=x;}out+='\n';
  }
  return out;
}

// ================= Sequencer health input =================
#ifndef C4_LOSS_TIMEOUT_MS
#define C4_LOSS_TIMEOUT_MS 800
#endif

// Action Sequencer definitions
enum TxAction : uint8_t {
  A_70,
  A_0B_04, A_0B_02, A_0B_05, A_0B_50, A_0B_08,
  A_4F,
  A_68,
  A_13,
  A_CB_321, A_CB_141,
  A_5C,
  A_CB_150,
};

// One cycle step: each action and the gap in ms
struct Step { TxAction act; uint16_t gap_ms; };

static const Step kSeq[] = {
  {A_70,     25},
  {A_0B_04,   1},
  {A_0B_02,   1},
  {A_0B_05,   1},
  {A_0B_50,   1},
  {A_0B_08, 100},
  {A_4F,    100},
  {A_0B_04,   1},
  {A_0B_02,   1},
  {A_0B_05,   1},
  {A_0B_50,   1},
  {A_0B_08, 100},
  {A_68,     4},
  {A_13,     1},
  {A_CB_321, 1},
  {A_CB_141, 1},
  {A_5C,     1},
  {A_CB_150,100},
  {A_0B_04,  1},
  {A_0B_02,  1},
  {A_0B_05,  1},
  {A_0B_50,  1},
  {A_0B_08,200},
};
static const uint8_t kSeqCount = sizeof(kSeq)/sizeof(kSeq[0]);

// Runtime state
// Main loop exclusively owns running/index/deadline. Decoder publishes only heartbeat/start request.
static bool     g_seqRunning = false;
static uint8_t  g_seqIndex   = 0;
static uint32_t g_nextDueMs  = 0;
static std::atomic<uint32_t> g_lastC4ms{0};
static std::atomic<bool> g_seqStartRequested{false};

// Forward
static void sendAction(TxAction a);

// ================= Headers =================
uint8_t header_3C[] = {
    0xaa, 0x03, 0x84, 0x00, 0x3c, 0x2e, 0xac, 0x04,
    0x00, 0x00, 0x0b, 0x3c, 0x03, 0x14, 0x01, 0x01,
    0x03, 0x2f
};

uint8_t header_13[] = {
    0xAA ,0x03, 0xBA, 0x00, 0x13, 0x2C, 0x00, 0x1a,
    0x00, 0x00, 0x0B, 0x3C, 0x03, 0x14, 0x01, 0x00,
    0x03, 0x1A
};


uint8_t header_CB_2031[] = { // BMS Upper Ack
    0xAA, 0x03, 0x01, 0x00, 0xCB, 0x2E, 0xF7, 0x3A, 
    0x00, 0x00, 0x0B, 0x3C, 0x03, 0x14, 0x01, 0x01, 
    0x20, 0x31
};

uint8_t header_CB_2033[] = { // BMS Lower Ack
    0xAA, 0x03, 0x01, 0x00, 0xCB, 0x2E, 0xF7, 0x3A, 
    0x00, 0x00, 0x0B, 0x3C, 0x03, 0x14, 0x01, 0x01, 
    0x20, 0x33
};

uint8_t header_CB_321[] = { // BMS Lower Ack
    0xAA, 0x03, 0x01, 0x00, 0xCB, 0x2C, 0x5E, 0x47, 
    0x01, 0x00, 0x0B, 0x3C, 0x03, 0x08, 0x01, 0x00, 
    0x03, 0x21
};

uint8_t header_CB_141[] = { 
    0xAA, 0x03, 0x01, 0x00, 0xCB, 0x2C, 0x5F, 0x47, 
    0x01, 0x00, 0x0B, 0x3C, 0x03, 0x08, 0x01, 0x00, 
    0x01, 0x41
};

uint8_t header_CB_150[] = { 
    0xAA, 0x03, 0x01, 0x00, 0xCB, 0x2C, 0x72, 0x47, 
    0x01, 0x00, 0x0B, 0x3C, 0x03, 0x08, 0x01, 0x00, 
    0x01, 0x50
};

uint8_t header_70[] = {
    0xAA, 0x03, 0x20, 0x00, 0x70, 0x2C, 0x86, 0x44, 
    0x01, 0x00, 0x0B, 0x3C, 0x03, 0x35, 0x01, 0x00, 
    0x35, 0x10
};

uint8_t header_0B_02[] = {
    0xAA, 0x03, 0x1A, 0x00, 0x0B, 0x2C, 0x8E, 0x47, 
    0x01, 0x00, 0x0B, 0x3C, 0x03, 0x02, 0x01, 0x00, 
    0x03, 0x07
};

uint8_t header_0B_04[] = {
    0xAA, 0x03, 0x1A, 0x00, 0x0B, 0x2C, 0x8E, 0x47, 
    0x01, 0x00, 0x0B, 0x3C, 0x03, 0x04, 0x01, 0x00, 
    0x03, 0x07
};

uint8_t header_0B_05[] = {
    0xAA, 0x03, 0x1A, 0x00, 0x0B, 0x2C, 0x8C, 0x47, 
    0x01, 0x00, 0x0B, 0x3C, 0x03, 0x05, 0x01, 0x00, 
    0x03, 0x07
};

uint8_t header_0B_08[] = {
    0xAA, 0x03, 0x1A, 0x00, 0x0B, 0x2C, 0x8E, 0x47, 
    0x01, 0x00, 0x0B, 0x3C, 0x03, 0x08, 0x01, 0x00, 
    0x03, 0x07
};

uint8_t header_0B_50[] = {
    0xAA, 0x03, 0x1A, 0x00, 0x0B, 0x2C, 0x8D, 0x47, 
    0x01, 0x00, 0x0B, 0x3C, 0x03, 0x50, 0x01, 0x00, 
    0x03, 0x07
};

uint8_t header_5C[] = {
    0xAA, 0x03, 0x0A, 0x00, 0x5C, 0x2C, 0x98, 0x46, 
    0x01, 0x00, 0x0B, 0x3C, 0x03, 0x08, 0x01, 0x00, 
    0x03, 0x22
};

uint8_t header_68[] = {
    0xAA, 0x03, 0x80, 0x00, 0x68, 0x2C, 0xB9, 0x45, 
    0x01, 0x00, 0x0B, 0x3C, 0x03, 0x21, 0x01, 0x00, 
    0x03, 0x01
};

uint8_t header_C4[] = {
    0xAA, 0x03, 0x45, 0x00, 0xC4, 0x2D, 0x29, 0x3B, 
    0x00, 0x00, 0x01, 0x4B, 0x14, 0x03, 0x01, 0x01, 
    0x03, 0x02
};

uint8_t header_4F[] = {
   0xAA, 0x03, 0x23, 0x00, 0x4F, 0x2C, 0x8A, 0x05, 
   0x00, 0x00, 0x0B, 0x3C, 0x03, 0x21, 0x01, 0x00, 
   0x03, 0x01
};

uint8_t header_8C[] = {
  0xAA, 0x03, 0x2C, 0x00, 0x8C, 0x2F, 0xBF, 0x00, 
  0x00, 0x00, 0x0B, 0x3C, 0x03, 0x14, 0x01, 0x01, 
  0x01, 0x05
};

uint8_t header_24[] = {
  0xAA, 0x03, 0x24, 0x00, 0x24, 0x2F, 0xCD, 0x3A,
  0x00, 0x00, 0x0B, 0x3C, 0x03, 0x14, 0x01, 0x01,
  0x01, 0x41
};

// ================= Payloads =================
uint8_t payload_13[] = {
// Start of Payload 0 - 2
0x01, 0x01, 0x01, 

//Max Voltage 3 - 4 
0x60, 0xEA, 

0x00, 0x00, 

// 7 temp
0x12,

0x00, 0x00,

0x00, 0x08,

//12 - 13
//Min Voltage
0xE8, 0xCA, 

// Static
0x00, 0x00,
// 136 or -120 (signed 2's complement)
0x00, //0x88

// Static
0xFF, 0xFF, 0xFF,

//20 temp
0x12, 

// 0 & 1?
0x00, //0x00

// Static
0x40, 0x9C, 0x00, 0x00, 

// 105 ?
0x68, //0x68

// Static
0x0C, 0x00, 0x00, 0x5F, 0x94, 0x00, 0x00, 0x04, 
0x00, 0x00, 0x00, 0x64, 


//39   40 Max Cell Voltage
0xB6, 0x0C, 
//41   42 Min Cell Voltage
0x9A, 0x0C, 

//43  44    45    46 // cell temp
0x12, 0x12, 0x12, 0x12, 

0x00, 0x01, 0x01, 0x00, 
0x00, 0x00, 0x00, 0x00, 0x00, 0x41, 

//57  58  Input Watts
0x00, 0x00, 

0x00, 0x00, 

//250 or -6 (signed 2's complement) Output watts
//61   62
0x6a, 0xFF, //0xFA, 0xFF

//63  64
0x02, 0x7B, 

0x7B, 0x02, 0x00, 0x00,

//0?
0x01, //0x00

// Static
0x00, 0x00, 0x1C, 0x00, 0x10, 


//16S Cell Voltage 
//75
0xB4, 0x0C, 0xB6, 0x0C, 0x9A, 0x0C, 0xAE, 0x0C, 
0xB1, 0x0C, 0xAF, 0x0C, 0xB1, 0x0C, 0xA5, 0x0C, 
0xB2, 0x0C, 0xB1, 0x0C, 0xB0, 0x0C, 0xB1, 0x0C,
0xAE, 0x0C, 0xB0, 0x0C, 0xAF, 0x0C, 0xAF, 0x0C, 
//107 108    109  110    111
0x02, 0x12, 0x00, 0x12, 0x00, 

// Firmwaware 112 - 117
0x56, 0x30, 0x2E, 0x30, 0x2E, 0x30, 

// static 118 - 121
0x03, 0x01, 0x00, 0x00, 

//Serial 122 - 137
0x4D, 0x31, 0x30, 0x32, 0x5A, 0x33, 0x42, 0x34, 
0x5A, 0x45, 0x35, 0x48, 0x30, 0x36, 0x30, 0x31, 

//Static 138 - 147
0x3C, 0x0B, 0x00, 0x00, 0x20, 0x41, 0x80, 0xB5, 0x80, 0x40, 

//Voltage 148 - 149
0x7A, 0xD1, 

0x05, 

0x41, 0x11, 0x01, 

0x00, 0x01, 
//4
0x04, 0x00, 

// End of Frame
0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 
0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
0x00, 0x00, 0x00, 0x00
};

uint8_t payload_3C[] = {
    0x01, 

    0x84, 0x00,

    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
    
    0x3c, 0x00, 0x0b, 0x00, 0x01, 0x4d, 0x03, 0x01, 
    0x01, 0x11, 0x01, 0x00, 0x01, 0x02, 0x01, 0x02, 
    0x00, 0xc8, 0x00, 0x00, 0x01, 0x00,

    0x6e, 0xd2, 
    
    0x00, 0x00, 0x51, 0x56, 0x00, 0x00, 0x01, 0x00,
    0x02, 0x8e, 0x88, 0x05, 0x41, 
    
    0x0f, 
    
    0x9a, 0xca, 
    
    0x00, 0x00, 0x49, 0xff, 0xff, 0xff, 0x00, 0x01, 
    0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
    
    0x15, 0x15, 
    
    0x40, 0x9c, 0x00, 0x00, 
    
    0x7f, 0x32, 0x02, 0x00, 
    0x7a, 0x02, 0x00, 0x00, 
    
    0x64, 
    0x05, 
    
    0x00, 0x64
  };

uint8_t payload_CB[] = {
    0x00
  };

uint8_t payload_70[] = {
    0x01, 0x4D, 0x31, 0x30, 0x32, 0x5A, 0x33, 0x42, 
    0x34, 0x5A, 0x45, 0x35, 0x48, 0x30, 0x36, 0x30, 
    0x31, 0x01, 0x0B, 0x3C, 0x01, 0x01, 0x03, 0x4D, 
    0x01, 0x00, 0x01, 0x11, 0x00, 0x00, 0x00, 0x00
  };

uint8_t payload_0B[] = {
    0x02, 0xF0, 0xD2, 0x00, 0x00, 0x00, 0x00, 0x00, 
    0x00, 0x01, 0xCf, 0x00, 0x00, 0x00, 0x01, 0x00, 
    0x03, 0x01, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 
    0x00, 0x00
  };

uint8_t payload_5C[] = {
    0x00, 0x02, 0x07, 0xD3, 0x00, 0x00, 0x00, 0x00, 
    0x00, 0x00
  };

uint8_t payload_68[] = {
    0x4d, 0x31, 0x30, 0x32, 0x5a, 0x33, 0x42, 0x34, 
    0x5a, 0x45, 0x35, 0x48, 0x30, 0x36, 0x30, 0x31, 
    0x60, 0xea, 0x00, 0x00, 0x4d, 0x03, 0x01, 0x01, 
    0xc8, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 
    0x00, 0x00, 0x00, 0x00, 0x01, 0x08, 0x18, 0xcb, 
    0x00, 0x00, 0xd1, 0x02, 0x00, 0x00, 0x16, 0x02, 
    0x01, 0x40, 0x9c, 0x00, 0x00, 0x5f, 0x94, 0x00, 
    0x00, 0xf5, 0x0b, 0x00, 0x00, 0x04, 0x00, 0x00, 
    0x00, 0xb8, 0x0c, 0x00, 0x00, 0x9d, 0x0c, 0x00, 
    0x00, 0x16, 0x16, 0x17, 0x17, 0x00, 0x54, 0x00, 
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x21, 0x0a, 
    0x00, 0x00, 0x01, 0x32, 0x05, 0x00, 0x00, 0x00, 
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x2c, 0x01, 
    0x00, 0x00, 0x00, 0x64, 0x00, 0x03, 0x00, 0x17, 
    0x16, 0x03, 0x00, 0x00, 0x54, 0xec, 0x00, 0x00, 
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
  };

uint8_t payload_C4[69];

uint8_t payload_4F[] = {
    0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFA, 0xFF, 
    0xFF, 0xFF, 0x7F, 0x32, 0x02, 0x00, 0x00, 0x64, 
    0x05, 0x00, 0x64, 0x00, 0x2C, 0x01, 0x00, 0x00, 
    0x00, 0x25, 0x00, 0xFF, 0xFF, 0x00, 0x00, 0x00, 
    0x00, 0x00, 0x00
  };

uint8_t payload_8C[] = { //Version Date
    0x3C, 0x00, 0x0B, 0x00, 0x01, 0x01, 0x03, 0x4D, 
    0x11, 0x01, 0x00, 0x01, 0x4A, 0x61, 0x6E, 0x20, 
    0x32, 0x32, 0x20, 0x32, 0x30, 0x32, 0x34, 0x20, 
    0x32, 0x32, 0x3A, 0x33, 0x39, 0x3A, 0x32, 0x33, 
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
    0x00, 0x00, 0x00, 0x00
  };

uint8_t payload_24[] = { //Version Date
    0x7E, 0x06, 0x00, 0x00, 0x3C, 0x00, 0x0B, 0x00, 
    0x4D, 0x31, 0x30, 0x32, 0x5A, 0x33, 0x42, 0x34, 
    0x5A, 0x45, 0x35, 0x48, 0x30, 0x36, 0x30, 0x31, 
    0xA6, 0xF1, 0x32, 0x33, 0x34, 0x36, 0x0B, 0x00, 
    0x39, 0x38, 0x36, 0x37
  };

// ================= Prepare functions =================


void prepareMessage13(uint8_t *message) {
  const CanBatterySnapshot bs = canBatterySnapshotAtomic();
  const CanDerivedSnapshot ds = canDerivedSnapshotAtomic();
  const CanIdentitySnapshot ident = canIdentitySnapshotAtomic();
  message[7] = bs.temp;
  message[12] = bs.volt& 0xFF;
  message[13] = (bs.volt>> 8) & 0xFF;
  message[20] = bs.temp;
  
  message[43] = bs.temp;
  message[44] = bs.temp;
  message[45] = bs.temp;
  message[46] = bs.temp;

uint16_t minCellMv = ds.minCellMv;
uint16_t maxCellMv = ds.maxCellMv;

// Store Max Cell Voltage (message[39-40])
message[39] = maxCellMv & 0xFF;
message[40] = (maxCellMv >> 8) & 0xFF;

// Store Min Cell Voltage (message[41-42])
message[41] = minCellMv & 0xFF;
message[42] = (minCellMv >> 8) & 0xFF;

int32_t snapInW=0, snapOutW=0; canPowerSnapshotAtomic(snapInW,snapOutW);
int16_t outputWattInt = (int16_t)snapOutW;
int16_t inputWattInt = (int16_t)snapInW;
  message[57] = inputWattInt & 0xFF;
  message[58] = (inputWattInt >> 8) & 0xFF;
  message[61] = outputWattInt & 0xFF;
  message[62] = (outputWattInt >> 8) & 0xFF;
  memcpy(&message[122], ident.serial, 16);
  message[148] = ds.fullChargeMv & 0xFF;
  message[149] = (ds.fullChargeMv >> 8) & 0xFF;

}

void prepareMessage3C(uint8_t *message) {
  const CanBatterySnapshot bs = canBatterySnapshotAtomic();
  const CanIdentitySnapshot ident = canIdentitySnapshotAtomic();
  memcpy(&message[3], ident.serial, 16);
  message[41] = (ident.chgvolt + 3) & 0xFF;
  message[42] = ((ident.chgvolt + 3) >> 8) & 0xFF;
  message[56] = bs.soc;
  message[57] = (bs.volt) & 0xFF;
  message[58] = ((bs.volt) >> 8) & 0xFF;
  message[114] = message[115] = bs.temp;

  message[120] = bs.chgruntime & 0xFF;
  message[121] = (bs.chgruntime >> 8) & 0xFF;
  message[122] = (bs.chgruntime >> 16) & 0xFF;
  message[123] = (bs.chgruntime >> 24) & 0xFF;

  message[124] = bs.disruntime & 0xFF;
  message[125] = (bs.disruntime >> 8) & 0xFF;
  message[126] = (bs.disruntime >> 16) & 0xFF;
  message[127] = (bs.disruntime >> 24) & 0xFF;

  message[128] = bs.upper;
  message[129] = bs.lower;
}

void prepareMessageEB(uint8_t *message) {
// Nothing to prepare yet... need to work out the message structure
}

void prepareMessage0B(uint8_t *message) {
  const CanBatterySnapshot bs = canBatterySnapshotAtomic();
  message[1] = (bs.volt + 1000) & 0xFF;         // Consistently +1000mV Battery Voltage
  message[2] = ((bs.volt + 1000) >> 8) & 0xFF;

  message[9] = (bs.volt - 1896) & 0xFF;         //Roughly - 1896, Maybe BMS release or trigger voltage?
  message[10] = ((bs.volt - 1896) >> 8) & 0xFF; //
}

void prepareMessageCB(uint8_t *message) {
  //message[0] = config.flagCB ? 0x01 : 0x00;
}

void prepareMessage70(uint8_t *message) {
  const CanIdentitySnapshot ident = canIdentitySnapshotAtomic();
  memcpy(&message[1], ident.serial, 16);
}

void prepareMessage5C(uint8_t *message) {
  const CanBatterySnapshot bs = canBatterySnapshotAtomic();
  message[2] = (bs.volt) & 0xFF;
  message[3] = ((bs.volt) >> 8) & 0xFF;
  message[4] = 0x00;
}

void prepareMessage68(uint8_t *message) {
  const CanBatterySnapshot bs = canBatterySnapshotAtomic();
  const CanDerivedSnapshot ds = canDerivedSnapshotAtomic();
  const CanIdentitySnapshot ident = canIdentitySnapshotAtomic();
  int32_t snapInW=0, snapOutW=0; canPowerSnapshotAtomic(snapInW,snapOutW);
  int16_t outputWattInt = (int16_t)snapOutW;
  int16_t inputWattInt = (int16_t)snapInW;
  memcpy(&message[0], ident.serial, 16);
  message[37] = bs.soc;
  message[38] = (bs.volt) & 0xFF;
  message[39] = ((bs.volt) >> 8) & 0xFF;
  message[46] = bs.temp;
  if(inputWattInt > 0) message[47] = 0x02; else message[47] = 0x00;
  int16_t balanceCapInt = (int16_t)(ds.balanceCapMilli / 1000U);
  message[57] = (balanceCapInt * 1000) & 0xFF;
  message[58] = ((balanceCapInt * 1000) >> 8) & 0xFF;

uint16_t minCellMv = ds.minCellMv;
uint16_t maxCellMv = ds.maxCellMv;
message[65] = maxCellMv & 0xFF;
message[66] = (maxCellMv >> 8) & 0xFF;
message[69] = minCellMv & 0xFF;
message[70] = (minCellMv >> 8) & 0xFF;


  message[78] = inputWattInt & 0xFF;
  message[79] = (inputWattInt >> 8) & 0xFF;
  message[82] = outputWattInt & 0xFF;
  message[83] = (outputWattInt >> 8) & 0xFF;

  message[86] = bs.disruntime & 0xFF;
  message[87] = (bs.disruntime >> 8) & 0xFF;
  message[88] = (bs.disruntime >> 16) & 0xFF;
  message[89] = (bs.disruntime >> 24) & 0xFF;

  message[91] = bs.upper;
  message[92] = bs.lower;
}

void prepareMessage4F(uint8_t *message) {
  const CanBatterySnapshot bs = canBatterySnapshotAtomic();
int32_t inputWattInt=0, outputWattInt=0; canPowerSnapshotAtomic(inputWattInt,outputWattInt);
  // Convert float to int16_t
  message[0] = bs.soc;
  if(inputWattInt > 0) message[1] = 0x02; else message[1] = 0x00;
  message[2] = inputWattInt & 0xFF;
  message[3] = (inputWattInt >> 8) & 0xFF;
  message[4] = (inputWattInt >> 16) & 0xFF;
  message[5] = (inputWattInt >> 24) & 0xFF;
  message[6] = outputWattInt & 0xFF;
  message[7] = (outputWattInt >> 8) & 0xFF;
  message[8] = (outputWattInt >> 16) & 0xFF;
  message[9] = (outputWattInt >> 24) & 0xFF;
  message[10] = bs.chgruntime & 0xFF;
  message[11] = (bs.chgruntime >> 8) & 0xFF;
  message[12] = (bs.chgruntime >> 16) & 0xFF;
  message[13] = (bs.chgruntime >> 24) & 0xFF;
  message[15] = bs.upper;
  message[16] = bs.lower;
}

void prepareMessage8C(uint8_t *message) {
// Nothing to prepare yet... need to work out the message structure
}

void prepareMessage24(uint8_t *message) {
  const CanIdentitySnapshot ident = canIdentitySnapshotAtomic();
  memcpy(&message[8], ident.serial, 16);
}

// ================= Wrapper functions =================

void ecoflowSend3C() {
  prepareMessage3C(payload_3C);
  sendCANMessage(header_3C, payload_3C, sizeof(header_3C), sizeof(payload_3C));
}

void ecoflowSend8C() {
  prepareMessage8C(payload_8C);
  sendCANMessage(header_8C, payload_8C, sizeof(header_8C), sizeof(payload_8C));
}

void ecoflowSend24() {
  prepareMessage24(payload_24);
  sendCANMessage(header_24, payload_24, sizeof(header_24), sizeof(payload_24));
}

void ecoflowSendCB2031() {
  prepareMessageCB(payload_CB);
  sendCANMessage(header_CB_2031, payload_CB, sizeof(header_CB_2031), sizeof(payload_CB));
}

void ecoflowSendCB2033() {
  prepareMessageCB(payload_CB);
  sendCANMessage(header_CB_2033, payload_CB, sizeof(header_CB_2033), sizeof(payload_CB));
}


// ================= CRC helper =================

uint16_t crc16(const uint8_t *data, uint16_t len) {
  static const uint16_t table[] PROGMEM = {
      0, 49345, 49537, 320, 49921, 960, 640, 49729,
      50689, 1728, 1920, 51009, 1280, 50625, 50305, 1088,
      52225, 3264, 3456, 52545, 3840, 53185, 52865, 3648,
      2560, 51905, 52097, 2880, 51457, 2496, 2176, 51265,
      55297, 6336, 6528, 55617, 6912, 56257, 55937, 6720,
      7680, 57025, 57217, 8000, 56577, 7616, 7296, 56385,
      5120, 54465, 54657, 5440, 55041, 6080, 5760, 54849,
      53761, 4800, 4992, 54081, 4352, 53697, 53377, 4160,
      61441, 12480, 12672, 61761, 13056, 62401, 62081, 12864,
      13824, 63169, 63361, 14144, 62721, 13760, 13440, 62529,
      15360, 64705, 64897, 15680, 65281, 16320, 16000, 65089,
      64001, 15040, 15232, 64321, 14592, 63937, 63617, 14400,
      10240, 59585, 59777, 10560, 60161, 11200, 10880, 59969,
      60929, 11968, 12160, 61249, 11520, 60865, 60545, 11328,
      58369, 9408, 9600, 58689, 9984, 59329, 59009, 9792,
      8704, 58049, 58241, 9024, 57601, 8640, 8320, 57409,
      40961, 24768, 24960, 41281, 25344, 41921, 41601, 25152,
      26112, 42689, 42881, 26432, 42241, 26048, 25728, 42049,
      27648, 44225, 44417, 27968, 44801, 28608, 28288, 44609,
      43521, 27328, 27520, 43841, 26880, 43457, 43137, 26688,
      30720, 47297, 47489, 31040, 47873, 31680, 31360, 47681,
      48641, 32448, 32640, 48961, 32000, 48577, 48257, 31808,
      46081, 29888, 30080, 46401, 30464, 47041, 46721, 30272,
      29184, 45761, 45953, 29504, 45313, 29120, 28800, 45121,
      20480, 37057, 37249, 20800, 37633, 21440, 21120, 37441,
      38401, 22208, 22400, 38721, 21760, 38337, 38017, 21568,
      39937, 23744, 23936, 40257, 24320, 40897, 40577, 24128,
      23040, 39617, 39809, 23360, 39169, 22976, 22656, 38977,
      34817, 18624, 18816, 35137, 19200, 35777, 35457, 19008,
      19968, 36545, 36737, 20288, 36097, 19904, 19584, 35905,
      17408, 33985, 34177, 17728, 34561, 18368, 18048, 34369,
      33281, 17088, 17280, 33601, 16640, 33217, 32897, 16448};
  uint16_t crc = 0;
  for (uint16_t i = 0; i < len; i++) {
    crc = pgm_read_word_near(table + ((crc ^ data[i]) & 0xFF)) ^ (crc >> 8);
  }
  return crc;
}

// ================= TX serialization =================
// A logical EcoFlow message spans multiple TWAI frames. Decoder replies and the
// main-loop sequencer can run on different tasks; serialize the whole message so
// their fragments can never interleave on the bus.
static StaticSemaphore_t g_canTxMutexBuf;
static SemaphoreHandle_t g_canTxMutex = nullptr;

// ================= sendCANMessage =================
void sendCANMessage(uint8_t* header, uint8_t* payload, size_t headerSize, size_t payloadSize) {

  #define IDX_TRK0   16  // tracker = last 4 header bytes
  #define IDX_TRK1   17

  if (!header || headerSize != 18) { Serial.println("sendCANMessage: bad header (expected exactly 18 bytes)"); return; }
  // This encoder reads header[16] and header[17] for the tracker below.
  // Fail closed before any indexed access if a malformed/short header is ever supplied.
  if (payloadSize > 512) { Serial.println("sendCANMessage: payload too large; dropped"); return; }
  if (payloadSize && !payload) { Serial.println("sendCANMessage: null payload with nonzero length"); return; }

  if (!g_canTxMutex) { Serial.println("sendCANMessage: TX mutex unavailable; dropped"); return; }
  // AUDIT20.4.5.9.30: never wait forever behind a stalled logical CAN TX.
  // Dropping a competing message is safer than pinning its caller indefinitely.
  if (xSemaphoreTake(g_canTxMutex, pdMS_TO_TICKS(150)) != pdTRUE) return;

  // Work on a private header copy. RX replies and the main-loop sequencer may
  // transmit concurrently; mutating global header templates would race on byte 6.
  uint8_t localHeader[18]; memcpy(localHeader, header, 18);
  const uint8_t msg_type = localHeader[4];

    uint8_t  t0 = localHeader[16], t1 = localHeader[17];
    uint16_t trackerBE = ((uint16_t)t0 << 8) | (uint16_t)t1;

  uint32_t id_first, id_middle, id_last;
  const bool use_length_byte = (msg_type == 0xA0);

  /*if (use_length_byte) {
    // A0: length-prefixed frames (len + up to 7 data)
    id_first  = 0x00431403;
    id_middle = 0x00831403;
    id_last   = 0x00C31403;*/
  /*if (msg_type == 0xE2) {
    id_first  = 0x10014001;
    id_middle = 0x10114001;
    id_last   = 0x10214001;
  }*/
     /*else if (msg_type == 0x13 || msg_type == 0x49) {
    // 0x13 / 0x49 (and default): classic 8-byte frames
    id_first  = 0x10003001;
    id_middle = 0x10103001;
    id_last   = 0x10203001;
  }*else */
 
   uint8_t xor_key;

    id_first  = 0x10003001;
    id_middle = 0x10103001;
    id_last   = 0x10203001;

  if (msg_type == 0x3C) {
    xor_key = xor3C.load(std::memory_order_acquire);
  } else if (msg_type == 0x8C) {
    xor_key = xor8C.load(std::memory_order_acquire);
  } else if (msg_type == 0x24) {
    xor_key = xor24.load(std::memory_order_acquire);
  } else if (msg_type == 0xCB) {
    if (trackerBE == 0x2031 || trackerBE == 0x2033) {
      xor_key = xorCB.load(std::memory_order_acquire); 
    } else xor_key = xorCounter.fetch_add(1,std::memory_order_relaxed);
  } else {
      xor_key = xorCounter.fetch_add(1,std::memory_order_relaxed);
    }

  // ALWAYS generate a new XOR key and write it into header[6]
  //uint8_t xor_key = (uint8_t)random(0, 256);
  localHeader[6] = xor_key;

  // AUDIT19.15.24: build the encoded message in one bounded buffer.
  // Previous code used three variable-length stack arrays (encoded, crc_buf,
  // final_msg), peaking at ~1.6 KiB for the guarded maximum payload.  All
  // production headers are exactly 18 bytes, so fail closed on any other size
  // and keep one fixed-size buffer instead. This preserves byte-for-byte
  // framing while materially reducing loop-task stack pressure.
  static constexpr size_t CAN_HEADER_SIZE = 18;
  static constexpr size_t CAN_MAX_PAYLOAD = 512;
  uint8_t final_msg[CAN_HEADER_SIZE + CAN_MAX_PAYLOAD + 2];
  memcpy(final_msg, localHeader, CAN_HEADER_SIZE);
  for (size_t i = 0; i < payloadSize; i++) final_msg[CAN_HEADER_SIZE + i] = payload[i] ^ xor_key;
  const size_t crcLen = CAN_HEADER_SIZE + payloadSize;
  const uint16_t crc = crc16(final_msg, crcLen);
  final_msg[crcLen]     = (uint8_t)(crc & 0xFF);
  final_msg[crcLen + 1] = (uint8_t)(crc >> 8);

  const size_t total = crcLen + 2;
  char logBuffer[128];

  // --- Framing & TX ---
  size_t pos = 0;
  size_t frame_idx = 0;
  bool cbrecAllTxSent = true;

  while (pos < total) {
    size_t remain = total - pos;

    if (!use_length_byte) {
      // 13/49 etc: raw 8B frames
      uint8_t chunk = (remain > 8) ? 8 : (uint8_t)remain;
      bool is_last  = (remain <= 8);
      uint32_t id   = (frame_idx == 0) ? id_first : (is_last ? id_last : id_middle);

      if (!sendCANFrame(id, &final_msg[pos], chunk)) { cbrecAllTxSent = false; break; }
if (txLoggingAtomic()) {
      double ts = now_seconds();
      int len = snprintf(logBuffer, sizeof(logBuffer), "(%012.6f) vcanTx %08lX#", ts, id);
      for (uint8_t j = 0; j < chunk; j++) {
        len += snprintf(logBuffer + len, sizeof(logBuffer) - len, "%02X", final_msg[pos + j]);
      }
      streamCanLog(logBuffer);

    }
      pos += chunk;

    } else {
      // A0: [len][<=7 data] → DLC = len + 1
      uint8_t chunk = (remain > 7) ? 7 : (uint8_t)remain;
      if (chunk == 0) break;

      uint8_t frame_bytes[8];
      frame_bytes[0] = chunk;                       // length of following bytes
      memcpy(&frame_bytes[1], &final_msg[pos], chunk);

      bool is_last  = (remain <= 7);
      uint32_t id   = (frame_idx == 0) ? id_first : (is_last ? id_last : id_middle);

      if (!sendCANFrame(id, frame_bytes, (uint8_t)(chunk + 1))) { cbrecAllTxSent = false; break; }
if (txLoggingAtomic()) {
      double ts = now_seconds();
      int len = snprintf(logBuffer, sizeof(logBuffer), "(%012.6f) vcanTx %08lX#", ts, id);
      for (uint8_t j = 0; j < (uint8_t)(chunk + 1); j++) {
        len += snprintf(logBuffer + len, sizeof(logBuffer) - len, "%02X", frame_bytes[j]);
      }
      streamCanLog(logBuffer);

    }
      pos += chunk;
    }

    frame_idx++;
    // vTaskDelay(1);   // remove this hard delay
if ((frame_idx & 0x3U) == 0U) taskYIELD(); // cooperative yield every 4 frames
  }
  (void)cbrecAllTxSent; // raw TX frames are recorded in sendCANFrame()
  xSemaphoreGive(g_canTxMutex);
}

// ================= Sequencer =================

void canSequencer_onHeartbeatC4() {
  g_lastC4ms.store(millis(), std::memory_order_release);
  g_seqStartRequested.store(true, std::memory_order_release);
}

void canTxSequencerTick() {
  const uint32_t now = millis();
  const uint32_t last = g_lastC4ms.load(std::memory_order_acquire);
  const bool startReq = g_seqStartRequested.exchange(false, std::memory_order_acq_rel);
  if (!g_seqRunning && startReq) {
    g_seqRunning = true; g_seqIndex = 0; g_nextDueMs = now; canHealth.store(true,std::memory_order_release);
  }
  // stop if heartbeat lost; wrap-safe unsigned subtraction
  if (g_seqRunning && (uint32_t)(now - last) > C4_LOSS_TIMEOUT_MS) {
    g_seqRunning = false; canHealth.store(false,std::memory_order_release);
  }
  if (!g_seqRunning || !canTxEnabledAtomic()) return;
  if ((int32_t)(now - g_nextDueMs) < 0) return;

  // send current step
  const Step& step = kSeq[g_seqIndex];
  sendAction(step.act);

  // schedule next
  g_nextDueMs = now + step.gap_ms;
  g_seqIndex = (uint8_t)((g_seqIndex + 1) % kSeqCount);
}

// ================= Send action dispatcher =================

static void sendAction(TxAction a) {
  if (!canTxEnabledAtomic()) return;

  switch (a) {
    case A_70:
      if (canMessageEnabledAtomic("message70")) {
        prepareMessage70(payload_70);
        sendCANMessage(header_70, payload_70, sizeof(header_70), sizeof(payload_70));
      }
      break;

    case A_0B_04:
      if (canMessageEnabledAtomic("message0B")) {
        prepareMessage0B(payload_0B);
        sendCANMessage(header_0B_04, payload_0B, sizeof(header_0B_04), sizeof(payload_0B));
      }
      break;
    case A_0B_02:
      if (canMessageEnabledAtomic("message0B")) {
        prepareMessage0B(payload_0B);
        sendCANMessage(header_0B_02, payload_0B, sizeof(header_0B_02), sizeof(payload_0B));
      }
      break;
    case A_0B_05:
      if (canMessageEnabledAtomic("message0B")) {
        prepareMessage0B(payload_0B);
        sendCANMessage(header_0B_05, payload_0B, sizeof(header_0B_05), sizeof(payload_0B));
      }
      break;
    case A_0B_50:
      if (canMessageEnabledAtomic("message0B")) {
        prepareMessage0B(payload_0B);
        sendCANMessage(header_0B_50, payload_0B, sizeof(header_0B_50), sizeof(payload_0B));
      }
      break;
    case A_0B_08:
      if (canMessageEnabledAtomic("message0B")) {
        prepareMessage0B(payload_0B);
        sendCANMessage(header_0B_08, payload_0B, sizeof(header_0B_08), sizeof(payload_0B));
      }
      break;

    case A_4F:
      if (canMessageEnabledAtomic("message4F")) {
        prepareMessage4F(payload_4F);
        sendCANMessage(header_4F, payload_4F, sizeof(header_4F), sizeof(payload_4F));
      }
      break;

    case A_68:
      if (canMessageEnabledAtomic("message68")) {
        prepareMessage68(payload_68);
        sendCANMessage(header_68, payload_68, sizeof(header_68), sizeof(payload_68));
      }
      break;

    case A_13:
      if (canMessageEnabledAtomic("message13")) {
        prepareMessage13(payload_13);
        sendCANMessage(header_13, payload_13, sizeof(header_13), sizeof(payload_13));
      }
      break;

    case A_CB_321:
      if (canMessageEnabledAtomic("messageCB")) {
        prepareMessageCB(payload_CB);
        sendCANMessage(header_CB_321, payload_CB, sizeof(header_CB_321), sizeof(payload_CB));
      }
      break;

    case A_CB_141:
      if (canMessageEnabledAtomic("messageCB")) {
        prepareMessageCB(payload_CB);
        sendCANMessage(header_CB_141, payload_CB, sizeof(header_CB_141), sizeof(payload_CB));
      }
      break;

    case A_5C:
      if (canMessageEnabledAtomic("message5C")) {
        prepareMessage5C(payload_5C);
        sendCANMessage(header_5C, payload_5C, sizeof(header_5C), sizeof(payload_5C));
      }
      break;

    case A_CB_150:
      if (canMessageEnabledAtomic("messageCB")) {
        prepareMessageCB(payload_CB);
        sendCANMessage(header_CB_150, payload_CB, sizeof(header_CB_150), sizeof(payload_CB));
      }
      break;
  }
}

// ================= Xor Counter Initialiser =================

void ecoflowMessagesInit() {
  xorCounter.store((uint8_t)random(0, 256), std::memory_order_relaxed);
  if (!g_canTxMutex) g_canTxMutex = xSemaphoreCreateMutexStatic(&g_canTxMutexBuf);
  if (!g_canTxMutex) Serial.println("[CAN-TX] FATAL: TX serialization mutex unavailable");
}

// ================= EcoFlow CAN Rx Processor =================

void processEcoFlowCAN(const twai_message_t &rx) {
  uint32_t id = rx.identifier;

  // AUDIT19.15.27: TWAI classic CAN payload storage is 8 bytes. Reject an
  // impossible DLC before any rx.data copy/log loop, even if a malformed
  // software-injected frame ever reaches this function.
  if (rx.data_length_code > 8) {
    streamDebug("14001 invalid DLC > 8 — dropped");
    return;
  }
  // Only the observed 29-bit EcoFlow data frames belong to this decoder.
  // Reject RTR/standard frames before they can perturb reassembly state.
  if (rx.rtr || !rx.extd) {
    streamDebug("14001 non-data/non-extended CAN frame — dropped");
    return;
  }
  uint32_t fullID = id & 0x1FFFFFFF;

  // 14001 IDs
  #define MSG14001_START_ID   0x10014001UL
  #define MSG14001_MID_ID     0x10114001UL
  #define MSG14001_END_ID     0x10214001UL

  // Fixed parts
  #define MSG14001_HDR_LEN    18
  #define MSG14001_TIMEOUT_MS 300

  // Header indices
  #define IDX_TYPE   4   // msg_type
  #define IDX_XOR    6   // XOR key (unencoded)
  #define IDX_LEN_LO 2   // payload length (lo)
  #define IDX_LEN_HI 3   // payload length (hi)
  #define IDX_TRK0   16  // tracker = last 4 header bytes
  #define IDX_TRK1   17

  #ifndef MSG14001_MAX_PAYLOAD
  #define MSG14001_MAX_PAYLOAD 2048
  #endif
  #define MSG14001_BUF_CAP (MSG14001_HDR_LEN + MSG14001_MAX_PAYLOAD + 2)

  static uint8_t  buf[MSG14001_BUF_CAP];
  static uint32_t reassemblyEpoch = 0;
  static size_t   have = 0;
  static bool     active = false;
  static uint32_t lastTime = 0;

  // dynamic fields for the in-progress message
  static bool     lenKnown = false;
  static uint16_t payloadLen = 0;
  static size_t   targetTotal = 0; // = 18 + payloadLen + 2 once known

  // monitoring
  static uint16_t typeCount[256] = {0};
  static uint8_t  curType = 0xFF;       static bool curTypeValid = false;
  static uint16_t curTrackerBE = 0;     static bool curTrackerValid = false;
  static uint8_t  lastType = 0;
  static uint16_t lastTrackerBE = 0;

  auto reset_state = [&](){
    have = 0; active = false; lastTime = 0;
    lenKnown = false; payloadLen = 0; targetTotal = 0;
    curTypeValid = false; curTrackerValid = false; curType = 0xFF; curTrackerBE = 0;
  };

  // BUS-OFF is a hard stream boundary. Even if no pre-fault frame remains in
  // the application queue, discard any partial reassembly before accepting a
  // post-recovery fragment.
  const uint32_t busEpochNow = canCurrentBusEpoch();
  if (reassemblyEpoch != busEpochNow) {
    reset_state();
    reassemblyEpoch = busEpochNow;
  }

  auto append_bytes = [&](const uint8_t* data, uint8_t dlc){
    if (!active || dlc == 0) return;
    // Fail closed on any physical-buffer overflow or bytes beyond the declared
    // message length. Clamping could otherwise accept a max-size message with
    // trailing garbage after a valid CRC.
    if (have > MSG14001_BUF_CAP || (size_t)dlc > (MSG14001_BUF_CAP - have) ||
        (lenKnown && (have > targetTotal || (size_t)dlc > (targetTotal - have)))) {
      streamDebug("14001 reassembly overflow/trailing bytes — dropping");
      reset_state();
      return;
    }
    memcpy(&buf[have], data, dlc);
    have += dlc;
    lastTime = millis();

    // Capture type early
    if (!curTypeValid && have >= (IDX_TYPE + 1)) {
      curType = buf[IDX_TYPE];
      curTypeValid = true;
    }
    // Determine payload length when we have first 4 header bytes
    if (!lenKnown && have >= (IDX_LEN_HI + 1)) {
      payloadLen = (uint16_t)buf[IDX_LEN_LO] | ((uint16_t)buf[IDX_LEN_HI] << 8); // little-endian
      // Guard against oversize messages
      if (payloadLen > MSG14001_MAX_PAYLOAD) {
        char m[96];
        snprintf(m, sizeof(m), "14001 oversize payload %u > cap %u — dropping",
                 payloadLen, (unsigned)MSG14001_MAX_PAYLOAD);
        streamDebug(m);
        reset_state();
        return;
      }
      targetTotal = (size_t)MSG14001_HDR_LEN + (size_t)payloadLen + 2U;
      lenKnown = true;
    }
    // Tracker available once full header is buffered
    if (!curTrackerValid && have >= MSG14001_HDR_LEN) {
      curTrackerBE = ((uint16_t)buf[IDX_TRK0] << 8)  |  (uint16_t)buf[IDX_TRK1];
      curTrackerValid = true;
    }
  };

  auto is_printable = [](uint8_t c){ return (c >= 32 && c <= 126); };

  auto try_finish = [&](){
    if (!active || !lenKnown) return false;
    if (have < targetTotal)   return false;

    uint8_t msg_type = buf[IDX_TYPE];
    uint8_t xor_key  = buf[IDX_XOR];

    uint8_t  t0 = buf[IDX_TRK0], t1 = buf[IDX_TRK1];
    uint16_t trackerBE = ((uint32_t)t0 << 8) | (uint32_t)t1;

    // AUDIT19.15.27: validate CRC before decoding or acting on the message.
    // Our TX encoder emits CRC low byte then high byte. Accept the swapped
    // representation too for compatibility with captures that may expose the
    // two CRC bytes in network order, but never accept a CRC mismatch.
    const uint16_t crcCalc = crc16(buf, (uint16_t)(targetTotal - 2U));
    const uint16_t crcLE = (uint16_t)buf[targetTotal - 2] | ((uint16_t)buf[targetTotal - 1] << 8);
    const uint16_t crcBE = ((uint16_t)buf[targetTotal - 2] << 8) | (uint16_t)buf[targetTotal - 1];
    if (crcCalc != crcLE && crcCalc != crcBE) {
      char m[112];
      snprintf(m, sizeof(m), "14001 CRC mismatch calc=%04X wire=%02X%02X — dropping",
               crcCalc, buf[targetTotal - 2], buf[targetTotal - 1]);
      streamDebug(m);
      reset_state();
      return true;
    }
    const uint16_t crc = crcCalc;

    static uint8_t decoded[MSG14001_MAX_PAYLOAD];
    for (uint16_t i = 0; i < payloadLen; ++i)
      decoded[i] = buf[MSG14001_HDR_LEN + i] ^ xor_key;

    typeCount[msg_type]++; lastType = msg_type; lastTrackerBE = trackerBE;
    if (msg_type == 0xCB && (trackerBE == 0x2031 || trackerBE == 0x2033)) ecoflowCbRecorderTrigger(trackerBE);

    if (msg_type == 0xC4) {
      // Serial is expected at [3..18] for C4
      char serial[17] = {0};
      bool printable = (payloadLen >= 19);
      for (int i = 0; i < 16 && i + 3 < payloadLen; ++i) {
        uint8_t c = decoded[3 + i];
        serial[i] = is_printable(c) ? (char)c : '?';
        if (!is_printable(c)) printable = false;
      }

      g_peerSerialSeq.fetch_add(1,std::memory_order_acq_rel); // odd = writer active
      if (printable) {
        strncpy(SerialPS, serial, sizeof(SerialPS) - 1);
        SerialPS[sizeof(SerialPS) - 1] = '\0';
      } else {
        SerialPS[0] = '\0'; // invalid / missing → clear
      }
      g_peerSerialSeq.fetch_add(1,std::memory_order_release); // even = stable

      char dbg[256];
      snprintf(dbg, sizeof(dbg),
               "14001 OK type=C4 len=%u cnt=%u XOR=0x%02X CRC=%04X tracker=%02X%02X (BE=0x%04X) serial=%s%s",
               payloadLen, (unsigned)typeCount[msg_type], xor_key, crc,
               t0, t1, (uint16_t)trackerBE,
               serial, printable ? "" : " (non-printable/missing)");
      streamDebug(dbg);

      // Save XOR for 3C reply
      xor3C.store(xor_key,std::memory_order_release);

      // Reply to heartbeat only
      if (canTxEnabledAtomic() && canMessageEnabledAtomic("message3C")) {
        ecoflowSend3C();
      }

      // Begin sequencer
      canSequencer_onHeartbeatC4();

    } else if (msg_type == 0xDE) {
      char dbg[128];
      snprintf(dbg, sizeof(dbg),
               "14001 OK type=DE len=%u cnt=%u XOR=0x%02X CRC=%04X tracker=%02X%02X (BE=0x%04X)",
               payloadLen, (unsigned)typeCount[msg_type], xor_key, crc,
               t0, t1, (uint16_t)trackerBE);
      streamDebug(dbg);

      if (trackerBE == 0x0105) {
        xor8C.store(xor_key,std::memory_order_release);
        if (canTxEnabledAtomic() && canMessageEnabledAtomic("message8C")) {
          ecoflowSend8C();
        }
      }
      if (trackerBE == 0x0141) {
        xor24.store(xor_key,std::memory_order_release);
        if (canTxEnabledAtomic() && canMessageEnabledAtomic("message24")) {
          ecoflowSend24();
        }
      }

    } else if (msg_type == 0xCB) {

      if (trackerBE == 0x2031) {
        char dbg[128];
        snprintf(dbg, sizeof(dbg),
                 "14001 OK type=CB len=%u cnt=%u XOR=0x%02X CRC=%04X BE=0x%04X Upper Limit=%u",
                 payloadLen, (unsigned)typeCount[msg_type], xor_key, crc,
                 (uint16_t)trackerBE, (payloadLen ? decoded[0] : 0));
        streamDebug(dbg);

        xorCB.store(xor_key,std::memory_order_release);
        if (payloadLen >= 1) { g_psObservedUpper.store(decoded[0],std::memory_order_release); g_psObservedUpperMs.store(millis(),std::memory_order_release); }

        if (canTxEnabledAtomic() && canMessageEnabledAtomic("messageCB")) {
          ecoflowSendCB2031();
        }
      }

      if (trackerBE == 0x2033) {
        char dbg[128];
        snprintf(dbg, sizeof(dbg),
                 "14001 OK type=CB len=%u cnt=%u XOR=0x%02X CRC=%04X BE=0x%04X Lower Limit=%u",
                 payloadLen, (unsigned)typeCount[msg_type], xor_key, crc,
                 (uint16_t)trackerBE, (payloadLen ? decoded[0] : 0));
        streamDebug(dbg);

        xorCB.store(xor_key,std::memory_order_release);
        if (payloadLen >= 1) { g_psObservedLower.store(decoded[0],std::memory_order_release); g_psObservedLowerMs.store(millis(),std::memory_order_release); }

        if (canTxEnabledAtomic() && canMessageEnabledAtomic("messageCB")) {
          ecoflowSendCB2033();
        }
      }

    } else {
      char preview[3*8+1] = {0};
      int p = 0;
      int show = (payloadLen < 8) ? payloadLen : 8;
      for (int i = 0; i < show; ++i)
        p += snprintf(preview + p, sizeof(preview) - p, "%02X", decoded[i]);

      char dbg[256];
      snprintf(dbg, sizeof(dbg),
               "14001 OK type=0x%02X len=%u cnt=%u XOR=0x%02X CRC=%04X tracker=%02X%02X (BE=0x%04X) payload[0..%d]=%s",
               msg_type, payloadLen, (unsigned)typeCount[msg_type], xor_key, crc,
               t0, t1, (uint16_t)trackerBE, show-1, preview);
      streamDebug(dbg);
    }

    reset_state();
    return true;
  };

  // AUDIT20.4.5.9.33: expire an old partial message BEFORE the newly
  // received frame is admitted. Previously timeout was checked only after
  // routing, so a late END could complete and validate a >300 ms old partial
  // message before the timeout reset ran. A fresh START is allowed to replace
  // the old partial state immediately.
  if (active && (uint32_t)(millis() - lastTime) > MSG14001_TIMEOUT_MS) {
    streamDebug("14001 timeout before frame — reset");
    reset_state();
  }

  // ----- route incoming frame -----
  if (fullID == MSG14001_START_ID) {
    reset_state(); active = true; lastTime = millis();
    append_bytes(rx.data, rx.data_length_code);
    streamDebug("14001 start");
  } else if (fullID == MSG14001_MID_ID) {
    append_bytes(rx.data, rx.data_length_code);
  } else if (fullID == MSG14001_END_ID) {
    append_bytes(rx.data, rx.data_length_code);
    // An END frame must terminate exactly at the declared message length.
    // Early/extra termination is malformed and is discarded immediately
    // instead of leaving a partial session alive until timeout.
    if (!active) {
      // append_bytes may have reset state after an invalid length.
    } else if (!lenKnown || have != targetTotal) {
      char m[112];
      snprintf(m, sizeof(m), "14001 END length mismatch have=%u target=%u — dropping",
               (unsigned)have, (unsigned)targetTotal);
      streamDebug(m);
      reset_state();
    } else {
      (void)try_finish();
    }
  }

  // ----- timeout -----
  if (active && (millis() - lastTime > MSG14001_TIMEOUT_MS)) {
    streamDebug("14001 timeout — reset");
    reset_state();
  }

  // AUDIT20.4.4: raw RX logging moved to canRxTask before decoder prefilter.
}
