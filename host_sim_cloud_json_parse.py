"""Compile the exact firmware JSON member scanner and integer extractor on host."""
from pathlib import Path
import subprocess
import tempfile

source = Path('src/powerstream_api.cpp').read_text()
scanner = source[source.index('static bool findUniqueJsonMember('):source.index('static bool apiRequest(')]
number = source[source.index('static bool extractNumber('):source.index('bool powerStreamApiTest(')]
program = r'''
#include <string>
#include <cctype>
#include <cstdint>
#include <climits>
#include <cstring>
#include <cassert>
using String=std::string;
static bool isDigit(char c){return c>='0'&&c<='9';}
''' + scanner + number + r'''
int main(){
  int p=-1,v=-1;
  assert(findUniqueJsonMember(R"({"data":{"code":9},"code":0})","code",1,p));
  assert(!findUniqueJsonMember(R"({"code":0,"code":7})","code",1,p));
  assert(!findUniqueJsonMember(R"({"message":"\\\"code\\\":0"})","code",1,p));
  assert(!findUniqueJsonMember(R"([{"code":0}])","code",1,p));
  assert(!findUniqueJsonMember(R"({"code":0} trailing)","code",1,p));
  assert(extractNumber(R"({"data":{"upperLimit":70,"lowerLimit":"30"}})","upperLimit",v)&&v==70);
  assert(extractNumber(R"({"data":{"upperLimit":70,"lowerLimit":"30"}})","lowerLimit",v)&&v==30);
  assert(!extractNumber(R"({"upperLimit":70,"nested":{"upperLimit":71}})","upperLimit",v));
  assert(!extractNumber(R"({"upperLimit":2147483648})","upperLimit",v));
  assert(!extractNumber(R"({"upperLimit":99999999999999999999999})","upperLimit",v));
  assert(!extractNumber(R"({"upperLimit":70.5})","upperLimit",v));
  assert(extractNumber(R"({"lowerLimit":-2147483648})","lowerLimit",v)&&v==INT_MIN);
}
'''
with tempfile.TemporaryDirectory() as d:
    path=Path(d)
    (path/'test.cpp').write_text(program)
    subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=undefined',str(path/'test.cpp'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True)
print('PASS exact cloud parser: nesting, duplicates, strings, root, number bounds')
