"""Compile the exact HTTP OTA X-MD5 helper against host request/Update shims."""
from pathlib import Path
import subprocess
import tempfile

source=Path('src/ota.cpp').read_text()
fn=source[source.index('static bool otaApplyMd5('):source.index('void otaHandle()')]
program=r'''
#include <string>
#include <cctype>
#include <cassert>
struct String:std::string {using std::string::string; String(const std::string& s):std::string(s){} void toLowerCase(){for(char& c:*this)c=std::tolower((unsigned char)c);} };
struct Header {String data; String value()const{return data;}};
struct AsyncWebServerRequest {
  bool present=false; Header header;
  bool hasHeader(const char*)const{return present;}
  Header* getHeader(const char*){return &header;}
};
struct UpdateShim {int calls=0; bool accept=true; std::string last; bool setMD5(const char* p){++calls;last=p;return accept&&last.size()==32;}} Update;
''' + fn + r'''
int main(){
  AsyncWebServerRequest r;
  assert(otaApplyMd5(&r) && Update.calls==0);
  r.present=true;r.header.data=String("abc");
  assert(!otaApplyMd5(&r) && Update.calls==0);
  r.header.data=String("0000000000000000000000000000000g");
  assert(!otaApplyMd5(&r) && Update.calls==0);
  r.header.data=String("0123456789abcdef0123456789ABCDEF");
  assert(otaApplyMd5(&r) && Update.calls==1 && Update.last=="0123456789abcdef0123456789abcdef");
  Update.accept=false;
  assert(!otaApplyMd5(&r) && Update.calls==2);
}
'''
assert source.count('if (!otaApplyMd5(request))')==1
assert source.count('if(!otaApplyMd5(request))')==1
with tempfile.TemporaryDirectory() as d:
  path=Path(d);(path/'test.cpp').write_text(program)
  subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=undefined',str(path/'test.cpp'),'-o',str(path/'test')],check=True)
  subprocess.run([str(path/'test')],check=True)
print('PASS exact OTA X-MD5 helper: missing, short, nonhex, valid, setMD5 failure')
