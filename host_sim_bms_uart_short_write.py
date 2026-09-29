"""Compile the actual RS485 request functions with a fault-injecting UART shim."""
from pathlib import Path
import subprocess
import tempfile

src = Path('src/bms.cpp').read_text()


def function(signature):
    start = src.index(signature)
    brace = src.index('{', start)
    level = 1
    end = brace + 1
    while level:
        level += (src[end] == '{') - (src[end] == '}')
        end += 1
    return src[start:end]


cpp = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
using std::size_t;
uint32_t clockMs=100;
uint32_t millis(){return clockMs;}
void delayMicroseconds(int){}
constexpr int RS485_CALLBACK=1, HIGH=1, LOW=0;
int line=LOW;
void digitalWrite(int,int v){line=v;}
struct SerialLog { template<typename... T> void printf(const char*,T...){ } } Serial;
struct FakeSerial {
  size_t limit=100;
  int flushes=0;
  int available(){return 0;}
  int read(){return -1;}
  size_t write(const uint8_t*,size_t n){return limit<n?limit:n;}
  void flush(){++flushes;}
};
uint32_t bmsDiagTxAttempts=0,bmsDiagTxStarted=0;
uint16_t modbusCrc16(const uint8_t* p,size_t n){
  uint16_t c=0xffff;
  for(size_t i=0;i<n;++i){c^=p[i];for(int bit=0;bit<8;++bit)c=(c&1)?uint16_t((c>>1)^0xa001):uint16_t(c>>1);}
  return c;
}
void setRS485Transmit(bool v){digitalWrite(RS485_CALLBACK,v?HIGH:LOW);}
class JKPBBms {
public:
  FakeSerial* serial_=nullptr;
  bool waiting_=false,writeWaiting_=false,verifyWriteAfterSetup_=false,setupQueued_=false;
  int detectedAddr_=0;
  uint8_t probeAddr_=0,requestAddr_=0,headerMatch_=0,writeAckPos_=0;
  uint8_t writeAck_[8]{};
  uint16_t requestRegister_=0,pendingWriteOffset_=0,pendingWriteReg_=0,lastWriteReg_=0;
  uint32_t pendingWriteValue_=0,lastWriteValue_=0,writeRequestMs_=0,requestMs_=0,lastRxByteMs_=0;
  size_t framePos_=0,rawRxPos_=0;
  bool lastWriteAckOk_=false,lastWriteVerified_=false;
  uint32_t writeFailCount_=0;
  bool sendTrigger(uint16_t);
  bool writeSettingU32(uint16_t,uint32_t);
};
constexpr int JK_RESPONSE_TIMEOUT_MS=1200;
'''
cpp += '\n' + function('bool JKPBBms::sendTrigger(uint16_t reg)')
cpp += '\n' + function('bool JKPBBms::writeSettingU32(uint16_t offset, uint32_t value)')
cpp += r'''
int main(){
  FakeSerial uart;
  JKPBBms b; b.serial_=&uart;
  uart.limit=4;
  assert(!b.sendTrigger(0x1620));
  assert(!b.waiting_ && line==LOW && bmsDiagTxStarted==0 && uart.flushes==1);
  uart.limit=11;
  assert(b.sendTrigger(0x1620));
  assert(b.waiting_ && line==LOW && bmsDiagTxStarted==1);
  b.waiting_=false;
  assert(!b.writeSettingU32(292,1) && uart.flushes==2);
  assert(!b.writeSettingU32(281,1) && uart.flushes==2);
  uart.limit=7;
  assert(!b.writeSettingU32(280,0));
  assert(!b.writeWaiting_ && !b.lastWriteAckOk_ && !b.lastWriteVerified_ && b.writeFailCount_==1 && line==LOW);
  uart.limit=13;
  assert(b.writeSettingU32(280,0));
  assert(b.writeWaiting_ && b.writeFailCount_==1 && line==LOW);
  puts("BMS UART short-write fault injection: PASS");
}
'''

with tempfile.TemporaryDirectory() as d:
    path = Path(d)
    (path / 'test.cpp').write_text(cpp)
    subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-fsanitize=undefined',
                    str(path / 'test.cpp'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
