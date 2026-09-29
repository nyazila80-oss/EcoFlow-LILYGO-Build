#pragma once
#include <Arduino.h>
#include <HardwareSerial.h>
#include <atomic>

struct BmsSafetySnapshot {
  bool valid;
  uint8_t soc;
  uint8_t soh;
  int32_t currentMilliA;
  uint32_t voltageMilliV;
  int16_t tempDeciC;
  uint32_t okStatusFrames;
  uint32_t lastValidMs;
};
BmsSafetySnapshot bmsSafetySnapshotAtomic();
void bmsObjectLock();
void bmsObjectUnlock();


// JK-PB V19 adapter for UART1 protocol 013 (9600 baud).
// Telemetry is requested with the JK FC10 trigger at 0x1620 and decoded
// from the proprietary 300-byte 55 AA EB 90 status payload.
class JKPBBms {
public:
  void begin(HardwareSerial *serial) { serial_ = serial; }
  void main_task(bool force = true);
  bool requestStatus();
  bool requestSetup();
  bool writeSettingU32(uint16_t offset, uint32_t value);
  void queueSetupRequest() { setupQueued_ = true; }
  bool serviceQueuedSetup() { if (!setupQueued_) return false; if (sendTrigger(0x161E)) { setupQueued_ = false; return true; } return false; }
  bool setup_request_pending() const { return setupQueued_; }
  bool waiting() const { return waiting_; }
  uint16_t active_request_register() const { return requestRegister_; }
  size_t frame_pos() const { return framePos_; }
  size_t raw_rx_pos() const { return rawRxPos_; }
  uint32_t last_valid_age_ms() const { return lastValidMs_ ? (millis()-lastValidMs_) : 0xFFFFFFFFUL; }
  uint32_t ok_status_frames() const { return okStatusFrames_; }
  uint32_t ok_setup_frames() const { return okSetupFrames_; }
  uint32_t rejected_frames() const { return rejectedFrames_; }
  uint32_t timeout_count() const { return timeoutCount_; }
  bool write_pending() const { return writeWaiting_; }
  bool last_write_ack_ok() const { return lastWriteAckOk_; }
  bool last_write_verified() const { return lastWriteVerified_; }
  uint16_t last_write_register() const { return lastWriteReg_; }
  uint32_t last_write_value() const { return lastWriteValue_; }
  uint32_t write_ack_ok_count() const { return writeAckOkCount_; }
  uint32_t write_verify_ok_count() const { return writeVerifyOkCount_; }
  uint32_t write_fail_count() const { return writeFailCount_; }

  float get_voltage() const { return voltage_; }
  float get_current() const { return current_; }
  uint8_t get_state_of_charge() const { return soc_; }
  float get_cell_voltage(uint8_t i) const { return i < numCells_ ? cellV_[i] : 0.0f; }
  uint8_t get_num_cells() const { return numCells_; }
  uint8_t get_num_ntcs() const { return 2; }
  float get_ntc_temperature(uint8_t i) const { return i < 5 ? temp_[i] : temp_[0]; }
  float get_mos_temperature() const { return mosTemp_; }
  float get_balance_current() const { return balanceCurrent_; }
  float get_power() const { return power_; }
  uint32_t get_cycle_capacity_mah() const { return cycleCapacityMah_; }
  uint8_t get_battery_status() const { return batteryStatus_; }
  uint8_t get_soh() const { return soh_; }
  bool get_precharge_status() const { return prechargeStatus_; }
  uint32_t get_bms_runtime_s() const { return bmsRuntimeS_; }
  bool get_heating_status() const { return heatingStatus_; }
  bool get_charger_plugged() const { return chargerPlugged_; }
  uint32_t get_alarm_bits() const { return alarm_; }
  float get_wire_resistance(uint8_t i) const { return i < 32 ? wireResOhm_[i] : 0.0f; }
  bool setup_valid() const { return setupValid_; }
  uint32_t setup_age_ms() const { return setupValid_ ? (millis() - lastSetupMs_) : 0xFFFFFFFFUL; }
  float cfg_sleep_entry_v() const { return cfgSleepEntryV_; }
  float cfg_cell_uvp() const { return cfgCellUvp_; }
  float cfg_cell_uvpr() const { return cfgCellUvpr_; }
  float cfg_cell_ovp() const { return cfgCellOvp_; }
  float cfg_cell_ovpr() const { return cfgCellOvpr_; }
  float cfg_soc100_v() const { return cfgSoc100V_; }
  float cfg_soc0_v() const { return cfgSoc0V_; }
  float cfg_rcv_v() const { return cfgRcvV_; }
  float cfg_float_v() const { return cfgFloatV_; }
  float cfg_poweroff_v() const { return cfgPowerOffV_; }
  float cfg_balance_delta_v() const { return cfgBalanceDeltaV_; }
  float cfg_balance_start_v() const { return cfgBalanceStartV_; }
  float cfg_max_balance_a() const { return cfgMaxBalanceA_; }
  float cfg_charge_a() const { return cfgChargeA_; }
  float cfg_discharge_a() const { return cfgDischargeA_; }
  uint32_t cfg_charge_ocp_delay() const { return cfgChargeOcpDelay_; }
  uint32_t cfg_charge_ocpr() const { return cfgChargeOcpr_; }
  uint32_t cfg_discharge_ocp_delay() const { return cfgDischargeOcpDelay_; }
  uint32_t cfg_discharge_ocpr() const { return cfgDischargeOcpr_; }
  uint32_t cfg_scp_release() const { return cfgScpRelease_; }
  uint32_t cfg_scp_delay_us() const { return cfgScpDelayUs_; }
  float cfg_charge_otp() const { return cfgChargeOtp_; }
  float cfg_charge_otpr() const { return cfgChargeOtpr_; }
  float cfg_discharge_otp() const { return cfgDischargeOtp_; }
  float cfg_discharge_otpr() const { return cfgDischargeOtpr_; }
  float cfg_charge_utp() const { return cfgChargeUtp_; }
  float cfg_charge_utpr() const { return cfgChargeUtpr_; }
  float cfg_mos_otp() const { return cfgMosOtp_; }
  float cfg_mos_otpr() const { return cfgMosOtpr_; }
  uint32_t cfg_cell_count() const { return cfgCellCount_; }
  float cfg_capacity_ah() const { return cfgCapacityAh_; }
  bool cfg_charge_enabled() const { return cfgChargeEn_; }
  bool cfg_discharge_enabled() const { return cfgDischargeEn_; }
  bool cfg_balance_enabled() const { return cfgBalanceEn_; }
  uint32_t cfg_device_address() const { return cfgDeviceAddress_; }
  uint32_t cfg_precharge_s() const { return cfgPrechargeS_; }
  uint16_t cfg_function_bits() const { return cfgFunctionBits_; }
  uint8_t cfg_smart_sleep_h() const { return cfgSmartSleepH_; }

  float get_balance_capacity() const { return remainAh_; }
  float get_rate_capacity() const { return fullAh_; }
  bool get_charge_mosfet_status() const { return chargeMos_; }
  bool get_discharge_mosfet_status() const { return dischargeMos_; }
  bool get_balance_status(uint8_t) const { return balanceMos_; }
  uint32_t get_cycle_count() const { return cycleCount_; }
  const char* get_protection_status_summary() const { return alarm_ ? "ALARM" : "OK"; }
  const char* get_bms_name() const { return valid_ ? "JK-PB V19 55AA" : nullptr; }
  uint16_t get_0x12_full_charge_voltage() const { return 5760; }
  void set_0xE1_mosfet_control_charge(bool) {}
  void set_0xE1_mosfet_control_discharge(bool) {}
  bool valid() const { return valid_; }
  int8_t detected_address() const { return detectedAddr_; }

private:
  HardwareSerial *serial_ = nullptr;
  // JK-PB V19: 300-byte 55AA payload plus trailer. Support both observed forms:
  // direct 8-byte FC10 ACK (308 total) and 00 + ACK + 00 (310 total).
  uint8_t frame_[340] = {0};
  size_t framePos_ = 0;
  uint32_t lastRxByteMs_ = 0;
  uint8_t headerMatch_ = 0;
  uint32_t requestMs_ = 0;
  uint32_t lastValidMs_ = 0;
  bool waiting_ = false;
  bool setupQueued_ = false;
  bool writeWaiting_ = false;
  uint8_t writeAck_[8] = {0};
  uint8_t writeAckPos_ = 0;
  uint32_t writeRequestMs_ = 0;
  uint16_t pendingWriteOffset_ = 0;
  uint16_t pendingWriteReg_ = 0;
  uint32_t pendingWriteValue_ = 0;
  bool verifyWriteAfterSetup_ = false;
  bool lastWriteAckOk_ = false;
  bool lastWriteVerified_ = false;
  uint16_t lastWriteReg_ = 0;
  uint32_t lastWriteValue_ = 0;
  uint32_t writeAckOkCount_ = 0, writeVerifyOkCount_ = 0, writeFailCount_ = 0;
  uint32_t okStatusFrames_ = 0, okSetupFrames_ = 0, rejectedFrames_ = 0, timeoutCount_ = 0;
  int8_t detectedAddr_ = -1;
  uint8_t probeAddr_ = 0;
  uint8_t requestAddr_ = 0;
  uint16_t requestRegister_ = 0x1620;
  uint8_t probeFailures_ = 0;
  uint8_t rawRx_[384] = {0};
  size_t rawRxPos_ = 0;

  bool valid_ = false;
  float voltage_ = 0.0f, current_ = 0.0f;
  float cellV_[32] = {0};
  float temp_[5] = {0};
  float mosTemp_ = 0.0f, balanceCurrent_ = 0.0f, power_ = 0.0f;
  float wireResOhm_[32] = {0};
  uint32_t cycleCapacityMah_ = 0;
  uint8_t batteryStatus_ = 0, soh_ = 0;
  bool prechargeStatus_ = false, heatingStatus_ = false, chargerPlugged_ = false;
  uint32_t bmsRuntimeS_ = 0;
  bool setupValid_ = false;
  uint32_t lastSetupMs_ = 0;
  float cfgSleepEntryV_=0, cfgCellUvp_=0, cfgCellUvpr_=0, cfgCellOvp_=0, cfgCellOvpr_=0;
  float cfgSoc100V_=0, cfgSoc0V_=0, cfgRcvV_=0, cfgFloatV_=0, cfgPowerOffV_=0;
  float cfgBalanceDeltaV_=0, cfgBalanceStartV_=0, cfgMaxBalanceA_=0;
  float cfgChargeA_=0, cfgDischargeA_=0;
  uint32_t cfgChargeOcpDelay_=0, cfgChargeOcpr_=0, cfgDischargeOcpDelay_=0, cfgDischargeOcpr_=0;
  uint32_t cfgScpRelease_=0, cfgScpDelayUs_=0;
  float cfgChargeOtp_=0, cfgChargeOtpr_=0, cfgDischargeOtp_=0, cfgDischargeOtpr_=0;
  float cfgChargeUtp_=0, cfgChargeUtpr_=0, cfgMosOtp_=0, cfgMosOtpr_=0;
  uint32_t cfgCellCount_=0, cfgDeviceAddress_=0, cfgPrechargeS_=0;
  float cfgCapacityAh_=0;
  bool cfgChargeEn_=false, cfgDischargeEn_=false, cfgBalanceEn_=false;
  uint16_t cfgFunctionBits_=0;
  uint8_t cfgSmartSleepH_=0;

  float remainAh_ = 0.0f, fullAh_ = 50.0f;
  uint8_t soc_ = 0, numCells_ = 16;
  bool chargeMos_ = false, dischargeMos_ = false, balanceMos_ = false;
  uint32_t cycleCount_ = 0, alarm_ = 0;

  void consumeByte(uint8_t b);
  void finishFrame();
  void parseStatus();
  void parseSetup();
  bool sendTrigger(uint16_t reg);
  void advanceProbe(const char *reason);
  void dumpRawRx(const char *reason) const;
  static uint16_t le16(const uint8_t *p);
  static int16_t i16le(const uint8_t *p);
  static uint32_t le32(const uint8_t *p);
  static int32_t i32le(const uint8_t *p);
};

extern HardwareSerial& bmsSerial;
extern JKPBBms bms;
JKPBBms bmsDiagnosticSnapshot();
extern float inputWatt;
extern float outputWatt;
extern std::atomic<uint32_t> bmsDiagLoopTicks;
extern std::atomic<uint32_t> bmsDiagTxAttempts;
extern std::atomic<uint32_t> bmsDiagTxStarted;
extern std::atomic<uint32_t> bmsDiagInitCount;
// Runtime CAN safety gate; does not modify the user's canTxEnabled setting.
bool bmsTelemetryValidForCan();
void bmsLoopInit();
void bmsLoopTick();
void bmsInit();
void batteryMasterInit();
void applyBatteryMasterIfChanged();
inline void bmsPoll(bool force = true) { bms.main_task(force); }
