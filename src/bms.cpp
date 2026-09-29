#include "bms.h"
#include <atomic>
#include "config.h"
#include <math.h>

static unsigned long bmsTimer = 0;
static unsigned long jkPollTimer = 0;
#define RS485_BAUD 9600
// Diagnostic scan: probe JK-PB UART1 addresses 0x00..0x0F and lock only after a fully validated reply.
#define JK_POLL_INTERVAL_MS 800
#define JK_RESPONSE_TIMEOUT_MS 1200
#define JK_DATA_STALE_MS 3000

// Coherent cross-core safety snapshot for consumers outside the BMS task/core.
// The JKPBBms object itself contains ordinary fields and must not be sampled
// directly from the PowerStream worker while the parser can update them.
static std::atomic<uint32_t> g_bmsSafetySeq{0};
static std::atomic<uint32_t> g_bmsSafetyMeta{0}; // bit0 valid, bits8..15 SOC
static std::atomic<int32_t>  g_bmsSafetyCurrentmA{0};
static std::atomic<uint32_t> g_bmsSafetyVoltageMilliV{0};
static std::atomic<int32_t> g_bmsSafetyTempDeciC{0};
static std::atomic<uint32_t> g_bmsSafetyFrames{0};
static std::atomic<uint32_t> g_bmsSafetyLastValidMs{0};
static void publishBmsSafetySnapshot(bool valid,uint8_t soc,uint8_t soh,float current,float voltage,float temp,uint32_t frames,uint32_t lastValidMs){
  g_bmsSafetySeq.fetch_add(1,std::memory_order_acq_rel); // odd = writer active
  g_bmsSafetyMeta.store((valid?1U:0U)|((uint32_t)soc<<8)|((uint32_t)soh<<16),std::memory_order_relaxed);
  g_bmsSafetyCurrentmA.store((int32_t)lroundf(current*1000.0f),std::memory_order_relaxed);
  g_bmsSafetyVoltageMilliV.store((uint32_t)lroundf(voltage*1000.0f),std::memory_order_relaxed);
  g_bmsSafetyTempDeciC.store((int32_t)lroundf(temp*10.0f),std::memory_order_relaxed);
  g_bmsSafetyFrames.store(frames,std::memory_order_relaxed);
  g_bmsSafetyLastValidMs.store(lastValidMs,std::memory_order_relaxed);
  g_bmsSafetySeq.fetch_add(1,std::memory_order_release); // even = stable
}
BmsSafetySnapshot bmsSafetySnapshotAtomic(){
  for(;;){
    const uint32_t a=g_bmsSafetySeq.load(std::memory_order_acquire); if(a&1U) continue;
    const uint32_t meta=g_bmsSafetyMeta.load(std::memory_order_relaxed);
    BmsSafetySnapshot out{(meta&1U)!=0,(uint8_t)(meta>>8),(uint8_t)(meta>>16),g_bmsSafetyCurrentmA.load(std::memory_order_relaxed),g_bmsSafetyVoltageMilliV.load(std::memory_order_relaxed),(int16_t)g_bmsSafetyTempDeciC.load(std::memory_order_relaxed),g_bmsSafetyFrames.load(std::memory_order_relaxed),g_bmsSafetyLastValidMs.load(std::memory_order_relaxed)};
    const uint32_t b=g_bmsSafetySeq.load(std::memory_order_acquire); if(a==b && !(b&1U)) return out;
  }
}

#ifndef VERBOSE_BMS_PRINTS
#define VERBOSE_BMS_PRINTS 0
#endif

float inputWatt = 0;
float outputWatt = 0;
std::atomic<uint32_t> bmsDiagLoopTicks{0};
std::atomic<uint32_t> bmsDiagTxAttempts{0};
std::atomic<uint32_t> bmsDiagTxStarted{0};
std::atomic<uint32_t> bmsDiagInitCount{0};

static bool prev_canTxEnabled = true;
static bool batteryMasterLast = true;

HardwareSerial& bmsSerial = Serial1;
JKPBBms bms;
static StaticSemaphore_t g_bmsObjectMutexBuf;
static SemaphoreHandle_t g_bmsObjectMutex=xSemaphoreCreateMutexStatic(&g_bmsObjectMutexBuf);
void bmsObjectLock(){ if(g_bmsObjectMutex) xSemaphoreTake(g_bmsObjectMutex,portMAX_DELAY); }
void bmsObjectUnlock(){ if(g_bmsObjectMutex) xSemaphoreGive(g_bmsObjectMutex); }
JKPBBms bmsDiagnosticSnapshot(){
  bmsObjectLock();
  JKPBBms out = bms;
  bmsObjectUnlock();
  return out;
}

static uint16_t modbusCrc16(const uint8_t *data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; ++i) {
    crc ^= data[i];
    for (uint8_t bit = 0; bit < 8; ++bit)
      crc = (crc & 1) ? uint16_t((crc >> 1) ^ 0xA001) : uint16_t(crc >> 1);
  }
  return crc;
}
static void setRS485Transmit(bool enable) { digitalWrite(RS485_CALLBACK, enable ? HIGH : LOW); }

uint16_t JKPBBms::le16(const uint8_t *p) { return uint16_t(p[0]) | (uint16_t(p[1]) << 8); }
int16_t JKPBBms::i16le(const uint8_t *p) { return (int16_t)le16(p); }
uint32_t JKPBBms::le32(const uint8_t *p) { return uint32_t(p[0]) | (uint32_t(p[1])<<8) | (uint32_t(p[2])<<16) | (uint32_t(p[3])<<24); }
int32_t JKPBBms::i32le(const uint8_t *p) { return (int32_t)le32(p); }

bool JKPBBms::sendTrigger(uint16_t reg) {
  ++bmsDiagTxAttempts;
  if (!serial_ || waiting_ || writeWaiting_) return false;
  requestAddr_ = (detectedAddr_ >= 0) ? uint8_t(detectedAddr_) : probeAddr_;
  requestRegister_ = reg;
  uint8_t req[11] = { requestAddr_, 0x10, uint8_t(reg >> 8), uint8_t(reg), 0x00, 0x01, 0x02, 0x00, 0x00, 0, 0 };
  uint16_t crc = modbusCrc16(req, 9); req[9]=uint8_t(crc); req[10]=uint8_t(crc>>8);
  // DIAG19.15.3: never let a noisy UART monopolize the caller. Drain only a bounded
  // number of stale bytes; remaining bytes are consumed by main_task() in bounded slices.
  for (size_t n = 0; n < 128 && serial_->available(); ++n) serial_->read();
  framePos_=0; headerMatch_=0; rawRxPos_=0; waiting_=true; requestMs_=millis(); lastRxByteMs_=requestMs_;
  setRS485Transmit(true); delayMicroseconds(150);
  const size_t sent = serial_->write(req,sizeof(req));
  serial_->flush(); delayMicroseconds(150); setRS485Transmit(false);
  if (sent != sizeof(req)) {
    waiting_ = false; framePos_ = 0; headerMatch_ = 0;
    Serial.printf("[JK-55AA] TX trigger short write %u/%u\n", unsigned(sent), unsigned(sizeof(req)));
    return false;
  }
  ++bmsDiagTxStarted;
  Serial.printf("[JK-55AA] TX trigger 0x%04X addr=%u\n", reg, requestAddr_);
  return true;
}

bool JKPBBms::requestStatus() { return sendTrigger(0x1620); }
bool JKPBBms::requestSetup()  { return sendTrigger(0x161E); }

// AUDIT18.7: write exactly one documented JK-PB V19 UINT32 RW parameter.
// IMPORTANT: JK bulk reads expose UINT32 values little-endian, while standard
// Modbus FC10 writes use network/register order. Public captures confirm e.g.
// BalanEN 0x1078 value 1 as: ADDR 10 10 78 00 02 04 00 00 00 01 CRC.
// We therefore validate the 8-byte FC10 ACK first and only then queue 0x161E
// for read-back verification. No ACK => no "verified" result.
bool JKPBBms::writeSettingU32(uint16_t offset, uint32_t value) {
  // Do not replace the pending register/value before its setup read-back has
  // completed; otherwise a second write could misattribute verification.
  // The 300-byte setup payload starts its UINT32 fields at byte 6 and ends
  // before checksum byte 299. Never transmit a register we cannot verify.
  if (offset > 288 || (offset & 3u) || !serial_ || waiting_ || writeWaiting_ ||
      verifyWriteAfterSetup_ || setupQueued_ || detectedAddr_ < 0) return false;
  const uint16_t reg = uint16_t(0x1000u + offset);
  uint8_t req[13] = { uint8_t(detectedAddr_), 0x10, uint8_t(reg>>8), uint8_t(reg),
                      0x00, 0x02, 0x04,
                      uint8_t(value>>24), uint8_t(value>>16), uint8_t(value>>8), uint8_t(value), 0, 0 };
  const uint16_t crc = modbusCrc16(req, 11);
  req[11] = uint8_t(crc); req[12] = uint8_t(crc >> 8);
  // DIAG19.15.3: bounded stale-RX drain; an electrically noisy bus must not hang loop().
  for (size_t n = 0; n < 128 && serial_->available(); ++n) serial_->read();
  writeAckPos_ = 0; writeWaiting_ = true; writeRequestMs_ = millis();
  pendingWriteOffset_ = offset; pendingWriteReg_ = reg; pendingWriteValue_ = value;
  lastWriteReg_ = reg; lastWriteValue_ = value; lastWriteAckOk_ = false; lastWriteVerified_ = false;
  verifyWriteAfterSetup_ = false;
  setRS485Transmit(true); delayMicroseconds(150);
  const size_t sent = serial_->write(req,sizeof(req)); serial_->flush();
  delayMicroseconds(150); setRS485Transmit(false);
  if (sent != sizeof(req)) {
    writeWaiting_ = false; writeAckPos_ = 0; ++writeFailCount_;
    Serial.printf("[JK-55AA] WRITE short TX reg=0x%04X %u/%u\n", reg, unsigned(sent), unsigned(sizeof(req)));
    return false;
  }
  Serial.printf("[JK-55AA] WRITE cfg off=0x%04X reg=0x%04X value=%lu; awaiting FC10 ACK\n", offset, reg, (unsigned long)value);
  return true;
}

void JKPBBms::dumpRawRx(const char *reason) const {
  Serial.printf("[JK-55AA] RAW RX (%s), captured=%u bytes:\n", reason, unsigned(rawRxPos_));
  if (rawRxPos_ == 0) { Serial.println("  <no bytes received>"); return; }
  for (size_t i=0; i<rawRxPos_; ++i) {
    Serial.printf("%02X ", rawRx_[i]);
    if ((i & 0x0F) == 0x0F) Serial.println();
  }
  if ((rawRxPos_ & 0x0F) != 0) Serial.println();
}

void JKPBBms::advanceProbe(const char *reason) {
  if (detectedAddr_ >= 0) return;
  ++probeFailures_;
  // Give address 0 three complete attempts first. Thereafter give every address
  // two attempts before moving on. This keeps the first hardware test focused
  // on the Device Address=0 shown by the JK app, while still allowing fallback.
  const uint8_t limit = (requestAddr_ == 0) ? 3 : 2;
  if (probeFailures_ >= limit) {
    probeAddr_ = uint8_t((requestAddr_ + 1) & 0x0F);
    probeFailures_ = 0;
    Serial.printf("[JK-55AA] %s on addr %u; moving to addr %u\n", reason, requestAddr_, probeAddr_);
  } else {
    probeAddr_ = requestAddr_;
    Serial.printf("[JK-55AA] %s on addr %u; retry %u/%u\n", reason, requestAddr_, unsigned(probeFailures_ + 1), unsigned(limit));
  }
}

void JKPBBms::consumeByte(uint8_t b) {
  lastRxByteMs_ = millis();
  if (writeWaiting_) {
    // Direct FC10 write acknowledgement: ADDR 10 REG_H REG_L 00 02 CRC_L CRC_H.
    // Resynchronise on the detected slave address in case a stray byte precedes it.
    if (writeAckPos_ == 0 && b != uint8_t(detectedAddr_)) return;
    if (writeAckPos_ < sizeof(writeAck_)) writeAck_[writeAckPos_++] = b;
    if (writeAckPos_ == sizeof(writeAck_)) {
      const uint16_t got = uint16_t(writeAck_[6]) | (uint16_t(writeAck_[7]) << 8);
      const uint16_t calc = modbusCrc16(writeAck_, 6);
      const bool shape = writeAck_[0] == uint8_t(detectedAddr_) && writeAck_[1] == 0x10 &&
        writeAck_[2] == uint8_t(pendingWriteReg_ >> 8) && writeAck_[3] == uint8_t(pendingWriteReg_) &&
        writeAck_[4] == 0x00 && writeAck_[5] == 0x02;
      writeWaiting_ = false;
      lastWriteAckOk_ = shape && (got == calc);
      if (lastWriteAckOk_) {
        ++writeAckOkCount_; verifyWriteAfterSetup_ = true; setupQueued_ = true;
        Serial.printf("[JK-55AA] WRITE ACK OK reg=0x%04X; queued 0x161E read-back\n", pendingWriteReg_);
      } else {
        ++writeFailCount_;
        Serial.printf("[JK-55AA] WRITE ACK BAD reg=0x%04X shape=%u crc=%04X/%04X\n", pendingWriteReg_, shape?1:0, calc, got);
      }
      writeAckPos_ = 0;
    }
    return;
  }
  if (rawRxPos_ < sizeof(rawRx_)) rawRx_[rawRxPos_++] = b;
  static const uint8_t magic[4] = {0x55, 0xAA, 0xEB, 0x90};
  if (framePos_ == 0) {
    if (b == magic[headerMatch_]) {
      headerMatch_++;
      if (headerMatch_ == 4) {
        memcpy(frame_, magic, 4);
        framePos_ = 4;
        headerMatch_ = 0;
        Serial.println("[JK-55AA] Header 55 AA EB 90 found");
      }
    } else {
      headerMatch_ = (b == 0x55) ? 1 : 0;
    }
    return;
  }

  if (framePos_ < sizeof(frame_)) frame_[framePos_++] = b;

  if (requestRegister_ == 0x1620) {
    if (framePos_ == 308) {
      const bool directShape = frame_[300] == requestAddr_ && frame_[301] == 0x10 &&
                               frame_[302] == 0x16 && frame_[303] == 0x20 && frame_[304] == 0 && frame_[305] == 1;
      if (directShape) finishFrame();
    }
    if (waiting_ && framePos_ == 310) finishFrame();
  } else if (requestRegister_ == 0x161E) {
    // AUDIT18.5: the user's JK-PB V19 returns SETUP as 300-byte 55AA payload
    // followed immediately by the 8-byte Modbus FC10 ACK (308 bytes), exactly
    // like the working status path. Accept that observed layout in addition to
    // the public 310-byte padded and 332-byte extended variants.
    if (framePos_ == 308) {
      const bool directShape = frame_[300] == requestAddr_ && frame_[301] == 0x10 &&
        frame_[302] == 0x16 && frame_[303] == 0x1E && frame_[304] == 0x00 && frame_[305] == 0x01;
      if (directShape) finishFrame();
    }
    if (waiting_ && framePos_ == 310) {
      const bool paddedAckShape = frame_[300] == 0x00 && frame_[301] == requestAddr_ &&
        frame_[302] == 0x10 && frame_[303] == 0x16 && frame_[304] == 0x1E &&
        frame_[305] == 0x00 && frame_[306] == 0x01 && frame_[309] == 0x00;
      if (paddedAckShape) finishFrame();
    }
    if (waiting_ && framePos_ == 332) finishFrame();
  }
}

void JKPBBms::main_task(bool) {
  if (!serial_) return;
  // DIAG19.15.3 isolation guard: process at most one bounded UART slice per call.
  // A continuously asserted/noisy RX line can otherwise keep available() non-zero
  // forever and starve WiFi, HTTP, CAN TX sequencing and the rest of loop().
  size_t rxBudget = 128;
  while (rxBudget-- && serial_->available()) consumeByte(uint8_t(serial_->read()));

  if (writeWaiting_ && millis() - writeRequestMs_ > JK_RESPONSE_TIMEOUT_MS) {
    writeWaiting_ = false; writeAckPos_ = 0; lastWriteAckOk_ = false; lastWriteVerified_ = false; ++writeFailCount_;
    Serial.printf("[JK-55AA] WRITE ACK TIMEOUT reg=0x%04X\n", pendingWriteReg_);
  }
  if (waiting_ && millis() - requestMs_ > JK_RESPONSE_TIMEOUT_MS) {
    Serial.printf("[JK-55AA] TIMEOUT frame=%u bytes after header, raw=%u bytes\n", unsigned(framePos_), unsigned(rawRxPos_));
    if (VERBOSE_BMS_PRINTS) dumpRawRx("timeout/partial response");
    waiting_ = false; framePos_ = 0; headerMatch_ = 0;
    if (requestRegister_ == 0x161E && verifyWriteAfterSetup_) {
      verifyWriteAfterSetup_ = false; lastWriteVerified_ = false; ++writeFailCount_;
      Serial.println("[JK-55AA] WRITE VERIFY failed: setup read-back timeout");
    }
    ++timeoutCount_;
    advanceProbe("timeout");
  }
  if (valid_ && lastValidMs_ != 0 && millis() - lastValidMs_ > JK_DATA_STALE_MS) {
    valid_ = false;
    publishBmsSafetySnapshot(false,soc_,soh_,current_,voltage_,temp_[0],okStatusFrames_,lastValidMs_);
    Serial.println("[JK-55AA] DATA STALE -> invalidated");
  }
}

void JKPBBms::finishFrame() {
  waiting_ = false;
  const size_t received = framePos_;
  bool magicOk = received >= 300 && frame_[0]==0x55 && frame_[1]==0xAA && frame_[2]==0xEB && frame_[3]==0x90;
  // Byte 4 is a JK frame sequence number, not the frame type. Public V19
  // documentation explicitly describes it as 0x01/0x02. Do not bind 0x1620
  // to sequence 0x02 or 0x161E to sequence 0x01; the trailing validated ACK
  // identifies the requested register unambiguously.
  const bool sequenceOk = received >= 300 && (frame_[4] == 0x01 || frame_[4] == 0x02);
  const bool headerReservedOk = received >= 300 && frame_[5] == 0x00;
  uint8_t sum = 0;
  if (received >= 300) for (size_t i=0; i<299; ++i) sum = uint8_t(sum + frame_[i]);
  bool payloadChecksumOk = received >= 300 && (sum == frame_[299]);

  // Trailer variants observed in public JK-PB V19 captures. Validate structurally
  // and by CRC; do not infer validity from length alone.
  int ackOffset = -1;
  uint16_t ackCalc = 0, ackGot = 0;
  auto validAckAt = [&](size_t off) -> bool {
    if (received < off + 8) return false;
    if (frame_[off] != requestAddr_ || frame_[off+1] != 0x10 ||
        frame_[off+2] != uint8_t(requestRegister_ >> 8) || frame_[off+3] != uint8_t(requestRegister_) ||
        frame_[off+4] != 0x00 || frame_[off+5] != 0x01) return false;
    const uint16_t calc = modbusCrc16(&frame_[off], 6);
    const uint16_t got = uint16_t(frame_[off+6]) | (uint16_t(frame_[off+7]) << 8);
    if (calc != got) return false;
    ackCalc = calc; ackGot = got; ackOffset = int(off);
    return true;
  };

  bool ackCrcOk = false;
  if (requestRegister_ == 0x1620) {
    if (received == 308) ackCrcOk = validAckAt(300);
    else if (received == 310) ackCrcOk = frame_[300] == 0x00 && frame_[309] == 0x00 && validAckAt(301);
  } else if (requestRegister_ == 0x161E) {
    if (received == 308) ackCrcOk = validAckAt(300);
    else if (received == 310) ackCrcOk = frame_[300] == 0x00 && frame_[309] == 0x00 && validAckAt(301);
    else if (received == 332) ackCrcOk = validAckAt(324);
  }
  Serial.printf("[JK-55AA] RX %u bytes header-seq=%s sum8=%s ACK=%s offset=%d\n",
    unsigned(received), (sequenceOk && headerReservedOk) ? "OK" : "BAD", payloadChecksumOk ? "OK" : "BAD",
    ackCrcOk ? "OK" : "BAD", ackOffset);
  if (received >= 300) Serial.printf("[JK-55AA] SUM8 calc=%02X got=%02X\n", sum, frame_[299]);
  if (ackCrcOk) {
    Serial.print("[JK-55AA] ACK: ");
    for (size_t i=ackOffset; i<size_t(ackOffset)+8; ++i) Serial.printf("%02X ", frame_[i]);
    Serial.printf(" calcCRC=%04X gotCRC=%04X\n", ackCalc, ackGot);
  } else {
    Serial.print("[JK-55AA] Trailer: ");
    for (size_t i=300; i<received; ++i) Serial.printf("%02X ", frame_[i]);
    Serial.println();
  }

  static bool dumpedFirstCompleteFrame = false;
  if (VERBOSE_BMS_PRINTS && (!dumpedFirstCompleteFrame || !(magicOk && sequenceOk && headerReservedOk && payloadChecksumOk && ackCrcOk))) {
    Serial.printf("[JK-55AA] RAW RX frame (%u bytes from header):\n", unsigned(received));
    for (size_t i=0; i<received; ++i) {
      Serial.printf("%02X ", frame_[i]);
      if ((i & 0x0F) == 0x0F) Serial.println();
    }
    if ((received & 0x0F) != 0) Serial.println();
    dumpedFirstCompleteFrame = true;
  }

  if (magicOk && sequenceOk && headerReservedOk && payloadChecksumOk && ackCrcOk) {
    if (detectedAddr_ < 0) {
      detectedAddr_ = requestAddr_;
      Serial.printf("[JK-55AA] LOCKED device address %d after validated frame+ACK\n", detectedAddr_);
    }
    if (requestRegister_ == 0x161E) { parseSetup(); if (setupValid_) ++okSetupFrames_; }
    else { parseStatus(); if (valid_) { ++okStatusFrames_; publishBmsSafetySnapshot(true,soc_,soh_,current_,voltage_,temp_[0],okStatusFrames_,lastValidMs_); } }
  } else {
    // Reject this transaction, but retain the last validated telemetry until
    // JK_DATA_STALE_MS expires. One bad poll must not instantly kill CAN data.
    Serial.println("[JK-55AA] Frame rejected; retaining last valid data until stale timeout");
    ++rejectedFrames_;
    if (requestRegister_ == 0x161E && verifyWriteAfterSetup_) {
      verifyWriteAfterSetup_ = false; lastWriteVerified_ = false; ++writeFailCount_;
      Serial.println("[JK-55AA] WRITE VERIFY failed: rejected setup read-back");
    }
    advanceProbe("rejected frame");
  }

  framePos_ = 0; headerMatch_ = 0;
}

void JKPBBms::parseStatus() {
  // Decode into temporaries first. Only commit after sanity checks, so a
  // checksum-valid but implausible frame cannot overwrite the last good data.
  const uint32_t present = le32(&frame_[70]);
  float newCellV[32] = {0};
  uint8_t newNumCells = 0;
  for (uint8_t i=0; i<32; ++i) {
    newCellV[i] = le16(&frame_[6 + i*2]) / 1000.0f;
    if (present & (1UL << i)) newNumCells = i + 1;
  }

  const float newVoltage = le32(&frame_[150]) / 1000.0f;
  const float newCurrent = i32le(&frame_[158]) / 1000.0f;
  const float newTemp0 = i16le(&frame_[162]) / 10.0f;
  const float newTemp1 = i16le(&frame_[164]) / 10.0f;
  const float newMosTemp = i16le(&frame_[144]) / 10.0f;
  const float newPower = le32(&frame_[154]) / 1000.0f;
  const float newBalanceCurrent = i16le(&frame_[170]) / 1000.0f;
  const uint8_t newBatteryStatus = frame_[172];
  const uint8_t newSoh = frame_[190];
  const bool newPrechargeStatus = frame_[191] != 0;
  const uint32_t newBmsRuntimeS = le32(&frame_[194]);
  const bool newHeatingStatus = frame_[215] != 0;
  const bool newChargerPlugged = frame_[245] != 0;
  const uint32_t newCycleCapacityMah = le32(&frame_[186]);
  float newTempExtra[3] = { i16le(&frame_[254])/10.0f, i16le(&frame_[256])/10.0f, i16le(&frame_[258])/10.0f };
  float newWire[32] = {0}; for (uint8_t i=0;i<32;i++) newWire[i]=i16le(&frame_[80+i*2])/1000.0f;
  const uint32_t newAlarm = le32(&frame_[166]);
  const uint8_t newSoc = frame_[173];
  const float newRemainAh = i32le(&frame_[174]) / 1000.0f;
  const float newFullAh = le32(&frame_[178]) / 1000.0f;
  const uint32_t newCycleCount = le32(&frame_[182]);
  const bool newChargeMos = frame_[198] != 0;
  const bool newDischargeMos = frame_[199] != 0;
  const bool newBalanceMos = frame_[200] != 0;

  bool sane = newNumCells >= 4 && newNumCells <= 32 &&
              newVoltage > 5.0f && newVoltage < 120.0f &&
              newSoc <= 100 && newSoh <= 100 && newRemainAh >= 0.0f &&
              newFullAh > 0.0f && newFullAh < 2000.0f &&
              newRemainAh <= newFullAh * 1.10f &&
              newTemp0 > -80.0f && newTemp0 < 150.0f &&
              newTemp1 > -80.0f && newTemp1 < 150.0f;
  for (uint8_t i=0; sane && i<newNumCells; ++i)
    sane = newCellV[i] > 1.0f && newCellV[i] < 5.0f;

  if (!sane) {
    Serial.println("[JK-55AA] STATUS sanity check failed; retaining last valid data until stale timeout");
    return;
  }

  memcpy(cellV_, newCellV, sizeof(cellV_));
  numCells_ = newNumCells;
  voltage_ = newVoltage;
  current_ = newCurrent;
  temp_[0] = newTemp0;
  temp_[1] = newTemp1; temp_[2]=newTempExtra[0]; temp_[3]=newTempExtra[1]; temp_[4]=newTempExtra[2];
  mosTemp_=newMosTemp; power_=newPower; balanceCurrent_=newBalanceCurrent; batteryStatus_=newBatteryStatus; cycleCapacityMah_=newCycleCapacityMah;
  soh_=newSoh; prechargeStatus_=newPrechargeStatus; bmsRuntimeS_=newBmsRuntimeS; heatingStatus_=newHeatingStatus; chargerPlugged_=newChargerPlugged;
  memcpy(wireResOhm_, newWire, sizeof(wireResOhm_));
  alarm_ = newAlarm;
  soc_ = newSoc;
  remainAh_ = newRemainAh;
  fullAh_ = newFullAh;
  cycleCount_ = newCycleCount;
  chargeMos_ = newChargeMos;
  dischargeMos_ = newDischargeMos;
  balanceMos_ = newBalanceMos;
  valid_ = true;
  lastValidMs_ = millis();

  Serial.printf("[JK-55AA] STATUS V=%.3fV I=%.3fA SOC=%u%% Rem=%.3fAh Full=%.3fAh T1=%.1fC T2=%.1fC cells=%u MOS C/D=%u/%u cycles=%lu\n",
    voltage_, current_, soc_, remainAh_, fullAh_, temp_[0], temp_[1], numCells_,
    chargeMos_, dischargeMos_, (unsigned long)cycleCount_);
}

void JKPBBms::parseSetup() {
  // A failed new setup read must not inherit the success bit of an older one.
  setupValid_ = false;
  // 0x161E SETUP frame. Decode to temporaries first and commit only after
  // plausibility checks. Offsets follow the JK-PB V19 55AA frame map.
  const float sleepEntryV = le32(&frame_[6])/1000.0f;
  const float cellUvp = le32(&frame_[10])/1000.0f;
  const float cellUvpr = le32(&frame_[14])/1000.0f;
  const float cellOvp = le32(&frame_[18])/1000.0f;
  const float cellOvpr = le32(&frame_[22])/1000.0f;
  const float balDelta = le32(&frame_[26])/1000.0f;
  const float soc100 = le32(&frame_[30])/1000.0f;
  const float soc0 = le32(&frame_[34])/1000.0f;
  const float rcv = le32(&frame_[38])/1000.0f;
  const float floatV = le32(&frame_[42])/1000.0f;
  const float powerOff = le32(&frame_[46])/1000.0f;
  const float chargeA = i32le(&frame_[50])/1000.0f;
  const uint32_t chargeDelay = le32(&frame_[54]);
  const uint32_t chargeRelease = le32(&frame_[58]);
  const float dischargeA = le32(&frame_[62])/1000.0f;
  const uint32_t dischargeDelay = le32(&frame_[66]);
  const uint32_t dischargeRelease = le32(&frame_[70]);
  const uint32_t scpRelease = le32(&frame_[74]);
  const float maxBalA = le32(&frame_[78])/1000.0f;
  const float chgOtp = i32le(&frame_[82])/10.0f;
  const float chgOtpr = i32le(&frame_[86])/10.0f;
  const float dsgOtp = i32le(&frame_[90])/10.0f;
  const float dsgOtpr = i32le(&frame_[94])/10.0f;
  const float chgUtp = i32le(&frame_[98])/10.0f;
  const float chgUtpr = i32le(&frame_[102])/10.0f;
  const float mosOtp = i32le(&frame_[106])/10.0f;
  const float mosOtpr = i32le(&frame_[110])/10.0f;
  const uint32_t cellCount = le32(&frame_[114]);
  const uint32_t chargeEnRaw = le32(&frame_[118]);
  const uint32_t dischargeEnRaw = le32(&frame_[122]);
  const uint32_t balanceEnRaw = le32(&frame_[126]);
  const float capacityAh = le32(&frame_[130])/1000.0f;
  const uint32_t scpDelayUs = le32(&frame_[134]);
  const float balStart = le32(&frame_[138])/1000.0f;
  const uint32_t deviceAddress = le32(&frame_[270]);
  const uint32_t prechargeS = le32(&frame_[274]);
  const uint16_t functionBits = le16(&frame_[282]);
  const uint8_t smartSleepH = frame_[286];

  // AUDIT18.3: validate the fields that prove this is a real JK settings frame.
  // Do not reject an otherwise CRC/checksum-valid setup frame only because a
  // firmware-specific/non-critical field (device address, precharge, function
  // bits, smart-sleep) is outside an assumed range.  V19.x variants differ here.
  uint32_t failMask = 0;
  auto bad = [&](bool cond, uint8_t bit){ if (cond) failMask |= (1UL << bit); };
  bad(!(cellCount >= 4 && cellCount <= 32), 0);
  bad(!(sleepEntryV >= 1.2f && sleepEntryV <= 5.0f), 1);
  bad(!(cellUvp >= 1.2f && cellUvp <= 4.5f), 2);
  bad(!(cellUvpr >= 1.2f && cellUvpr <= 4.5f), 3);
  bad(!(cellOvp >= 2.0f && cellOvp <= 5.0f), 4);
  bad(!(cellOvpr >= 2.0f && cellOvpr <= 5.0f), 5);
  bad(!(capacityAh > 0.0f && capacityAh <= 20000.0f), 6);
  bad(!(chargeA >= 0.0f && chargeA <= 1000.0f), 7);
  bad(!(dischargeA >= 0.0f && dischargeA <= 1000.0f), 8);
  bad(!(chargeEnRaw <= 1 && dischargeEnRaw <= 1 && balanceEnRaw <= 1), 9);

  if (failMask) {
    Serial.printf("[JK-55AA] SETUP core sanity failed mask=0x%08lX cells=%lu cap=%.3fAh sleep=%.3f UVP=%.3f UVPR=%.3f OVP=%.3f OVPR=%.3f chg=%.3fA dsg=%.3fA sw=%lu/%lu/%lu addr=%lu pre=%lu smart=%u\n",
      (unsigned long)failMask, (unsigned long)cellCount, capacityAh, sleepEntryV, cellUvp, cellUvpr, cellOvp, cellOvpr, chargeA, dischargeA,
      (unsigned long)chargeEnRaw, (unsigned long)dischargeEnRaw, (unsigned long)balanceEnRaw,
      (unsigned long)deviceAddress, (unsigned long)prechargeS, unsigned(smartSleepH));
    if (verifyWriteAfterSetup_) {
      verifyWriteAfterSetup_ = false; lastWriteVerified_ = false; ++writeFailCount_;
      Serial.println("[JK-55AA] WRITE VERIFY failed: invalid setup read-back");
    }
    return;
  }

  cfgSleepEntryV_=sleepEntryV; cfgCellUvp_=cellUvp; cfgCellUvpr_=cellUvpr; cfgCellOvp_=cellOvp; cfgCellOvpr_=cellOvpr;
  cfgBalanceDeltaV_=balDelta; cfgSoc100V_=soc100; cfgSoc0V_=soc0; cfgRcvV_=rcv;
  cfgFloatV_=floatV; cfgPowerOffV_=powerOff; cfgChargeA_=chargeA;
  cfgChargeOcpDelay_=chargeDelay; cfgChargeOcpr_=chargeRelease; cfgDischargeA_=dischargeA;
  cfgDischargeOcpDelay_=dischargeDelay; cfgDischargeOcpr_=dischargeRelease; cfgScpRelease_=scpRelease;
  cfgMaxBalanceA_=maxBalA; cfgChargeOtp_=chgOtp; cfgChargeOtpr_=chgOtpr;
  cfgDischargeOtp_=dsgOtp; cfgDischargeOtpr_=dsgOtpr; cfgChargeUtp_=chgUtp; cfgChargeUtpr_=chgUtpr;
  cfgMosOtp_=mosOtp; cfgMosOtpr_=mosOtpr; cfgCellCount_=cellCount;
  cfgChargeEn_=chargeEnRaw != 0; cfgDischargeEn_=dischargeEnRaw != 0; cfgBalanceEn_=balanceEnRaw != 0;
  cfgCapacityAh_=capacityAh; cfgScpDelayUs_=scpDelayUs; cfgBalanceStartV_=balStart;
  cfgDeviceAddress_=deviceAddress; cfgPrechargeS_=prechargeS; cfgFunctionBits_=functionBits; cfgSmartSleepH_=smartSleepH;
  setupValid_=true; lastSetupMs_=millis();
  if (verifyWriteAfterSetup_) {
    const size_t pos = 6u + size_t(pendingWriteOffset_);
    if (pos + 4u <= 299u) {
      const uint32_t got = le32(&frame_[pos]);
      lastWriteVerified_ = (got == pendingWriteValue_);
      if (lastWriteVerified_) ++writeVerifyOkCount_; else ++writeFailCount_;
      Serial.printf("[JK-55AA] WRITE VERIFY reg=0x%04X wanted=%lu read=%lu => %s\n",
        pendingWriteReg_, (unsigned long)pendingWriteValue_, (unsigned long)got, lastWriteVerified_ ? "OK" : "MISMATCH");
    } else { lastWriteVerified_ = false; ++writeFailCount_; }
    verifyWriteAfterSetup_ = false;
  }
  Serial.printf("[JK-55AA] SETUP parsed: %luS %.1fAh OVP %.3f UVP %.3f addr %lu\n",
    (unsigned long)cfgCellCount_, cfgCapacityAh_, cfgCellOvp_, cfgCellUvp_, (unsigned long)cfgDeviceAddress_);
}

bool bmsTelemetryValidForCan() {
  // AUDIT20.4.5.9.29 LOOP-STALL FAIL-CLOSED:
  // Do not rely on bms.main_task() getting CPU time to flip snapshot.valid false.
  // CAN RX/decode runs in independent FreeRTOS tasks and may still attempt replies
  // while Arduino loop() is stalled. Therefore every CAN TX admission re-checks
  // the age of the last validated JK status frame directly from the atomic snapshot.
  const BmsSafetySnapshot bs = bmsSafetySnapshotAtomic();
  if (!bs.valid || bs.lastValidMs == 0) return false;
  return (uint32_t)(millis() - bs.lastValidMs) <= JK_DATA_STALE_MS;
}

void bmsInit() {
  ++bmsDiagInitCount;
  pinMode(RS485_CALLBACK, OUTPUT); pinMode(RS485_EN, OUTPUT);
  digitalWrite(RS485_EN, HIGH); setRS485Transmit(false);
  bmsSerial.begin(RS485_BAUD, SERIAL_8N1, RS485_RX, RS485_TX);
  bms.begin(&bmsSerial);
  Serial.printf("[JK-55AA] UART1 protocol 013, %u baud; diagnostic: addr 0 x3, then addr 1..15 x2\n", RS485_BAUD);
  Serial.println("[JK-55AA] Poll mode: FC10 0x1620 -> 300-byte status + validated 308/310-byte trailer forms");
  batteryMasterInit(); bmsLoopInit();
}

void batteryMasterInit() {
  // JK adapter is telemetry-only. BatteryMaster therefore controls CAN TX only;
  // it never changes or simulates JK charge/discharge MOS state.
  batteryMasterLast = batteryMasterAtomic();
  prev_canTxEnabled = canTxEnabledAtomic();
}

void applyBatteryMasterIfChanged() {
  if (batteryMasterAtomic() == batteryMasterLast) return;

  if (!batteryMasterAtomic()) {
    prev_canTxEnabled = canTxEnabledAtomic();
    setCanTxEnabledAtomic(false);
    Serial.println("[BatteryMaster] OFF: CAN TX disabled; JK MOS state unchanged (read-only)");
  } else {
    setCanTxEnabledAtomic(prev_canTxEnabled);
    Serial.println("[BatteryMaster] ON: previous CAN TX preference restored; JK MOS state unchanged");
  }
  batteryMasterLast = batteryMasterAtomic();
}

void bmsLoopInit() {
  bmsTimer = millis();
}

void bmsLoopTick() {
  ++bmsDiagLoopTicks;
  // JK-PB V19 telemetry: trigger the complete dynamic/status frame at 0x1620.
  bmsObjectLock();
  bms.main_task(false);
  // Keep the proven 0x1620 telemetry path continuous. Setup/configuration
  // frames (0x161E) are requested only explicitly from the web UI. Mixing
  // automatic setup transactions into the 800 ms status poll can starve or
  // delay telemetry on JK-PB firmware variants whose setup reply differs.
  // A manual setup read is queued by the web UI and gets priority at the next
  // idle bus slot. This avoids random HTTP timing returning "BMS busy".
  const bool setupStarted = bms.serviceQueuedSetup();
  if (!setupStarted && !bms.setup_request_pending() && millis() - jkPollTimer >= JK_POLL_INTERVAL_MS) {
    if (bms.requestStatus()) jkPollTimer = millis();
  }
  bmsObjectUnlock();
  if (millis() - bmsTimer <= 3000) return;
  bmsTimer = millis();

  bmsObjectLock();
  bms.main_task(true);
  bmsObjectUnlock();

  // Keep the user's config.canTxEnabled preference untouched. The central CAN
  // transmit primitive separately gates TX on bmsTelemetryValidForCan().
  if (battSyncAtomic() && !bms.valid()) {
    inputWatt = 0;
    outputWatt = 0;
    setCanPowerSnapshotAtomic(0, 0);
    return;
  }

  // --- Charging runtime estimation ---
  float balance_capacity = bms.get_balance_capacity(); // Ah
  float charging_capacity = bms.get_rate_capacity() - balance_capacity;
  float current = bms.get_current(); // A

  if (current > 0) {
    inputWatt = bms.get_voltage() * bms.get_current();
    outputWatt = 0;
  } else if (bms.get_current() < 0) {
    outputWatt = bms.get_voltage() * bms.get_current();  // Will be negative
    inputWatt = 0;
  } else {
    inputWatt = 0;
    outputWatt = 0;
  }

  // --- Discharge runtime estimation ---
  float standby_current = 0.0195f; // 19.5mA in Amps, always positive
  float used_current = current < -0.01f ? fabs(current) : standby_current;
  float discharge_runtime_hours = balance_capacity / used_current;
  int discharge_runtime_minutes = int(discharge_runtime_hours * 60);

  // --- Charging runtime estimation ---
  int charge_runtime_minutes = 0;
  if (current > 0.01f) {
    float charge_runtime_hours = charging_capacity / current;
    charge_runtime_minutes = int(charge_runtime_hours * 60);
  } else {
    charge_runtime_minutes = 0;
  }

  float runtime_hours = balance_capacity / used_current;
  int runtime_minutes = int(runtime_hours * 60);

  int hours = int(runtime_hours);
  int minutes = int((runtime_hours - hours) * 60);

  if (bms.get_bms_name() != NULL) {
#if VERBOSE_BMS_PRINTS
    Serial.println("***********************************************");
    Serial.print("State of charge:\t"); Serial.print(bms.get_state_of_charge()); Serial.println("\t% ");
    Serial.print("Current:\t\t"); Serial.print(bms.get_current()); Serial.println("\tA  ");
    Serial.print("Voltage:\t\t"); Serial.print(bms.get_voltage()); Serial.println("\tV  ");

    for (uint8_t i = 0; i < bms.get_num_cells(); i++) {
      Serial.print((String)"Cell " + (i + 1) + " -\t\t");
      Serial.print(bms.get_cell_voltage(i), 3);
      Serial.print("\tV\t");
      Serial.println(bms.get_balance_status(i) ? "(balancing)" : "(not balancing)");
    }

    Serial.print("Balance capacity:\t"); Serial.print(bms.get_balance_capacity()); Serial.println("\tAh  ");
    Serial.print("Rate capacity:\t\t"); Serial.print(bms.get_rate_capacity()); Serial.println("\tAh  ");

    for (uint8_t i = 0; i < bms.get_num_ntcs(); i++) {
      Serial.print((String)"Termometer " + (i + 1) + " -\t\t");
      Serial.print(bms.get_ntc_temperature(i));
      Serial.println("\tdeg.\t");
    }

    Serial.print((String)"Charge mosfet" + " -\t\t");
    bms.get_charge_mosfet_status() ? Serial.print("Enabled") : Serial.print("Disabled");
    Serial.println("");

    Serial.print((String)"Discharge mosfet" + " -\t");
    bms.get_discharge_mosfet_status() ? Serial.print("Enabled") : Serial.print("Disabled");
    Serial.println("");

    Serial.print((String)"Cycle count" + " -\t\t"); Serial.print(bms.get_cycle_count()); Serial.println("");
    Serial.print((String)"protection_status" + " -\t"); Serial.print(bms.get_protection_status_summary()); Serial.println("");
    Serial.print((String)"get_bms_name" + " -\t\t"); Serial.print(bms.get_bms_name()); Serial.println("");

    Serial.printf("Estimated dischargeruntime: %dH-%dM (%d minutes, using %s)\n",
      hours, minutes, runtime_minutes,
      (fabs(current) > 0.01f) ? "measured current" : "standby current"
    );

    Serial.printf("Estimated charging time: %d min\n", charge_runtime_minutes);
#endif
  }

  setCanPowerSnapshotAtomic((int32_t)inputWatt, (int32_t)outputWatt);

  uint16_t snapMin=65535, snapMax=0;
  for(uint8_t i=0;i<16;i++){ uint16_t mv=(uint16_t)(bms.get_cell_voltage(i)*1000.0f); if(mv<snapMin)snapMin=mv; if(mv>snapMax)snapMax=mv; }
  setCanDerivedSnapshotAtomic(snapMin,snapMax,(uint16_t)(bms.get_balance_capacity()*1000.0f),(uint16_t)bms.get_0x12_full_charge_voltage());

  // JK MOS control is read-only; config mirrors only the actual BMS state.
  // Always update config to reflect the actual BMS state for display
  setMosStatusAtomic(bms.get_charge_mosfet_status(), bms.get_discharge_mosfet_status());

  if (battSyncAtomic()) {
    config.soc = bms.get_state_of_charge();
    config.volt = bms.get_voltage() * 1000; // Convert to mV
    config.temp = bms.get_ntc_temperature(0); // Assuming first NTC is the main temperature sensor
    config.chgruntime = (current > 0.01f) ? charge_runtime_minutes : 0;
    config.disruntime = (current < -0.01f) ? runtime_minutes : 0;
    syncCanBatterySnapshotAtomic();
  }
}
