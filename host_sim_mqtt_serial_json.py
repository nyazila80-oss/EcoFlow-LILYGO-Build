"""Run the exact MQTT serial escape loop and parse resulting JSON on host."""
from pathlib import Path
import json
import subprocess
import tempfile

src=Path('src/mqtt.cpp').read_text()
start=src.index('  char psJson[33]; size_t psLen=0;')
end=src.index('  // Fixed stack buffer:',start)
loop=src[start:end]
program=r'''
#include <string>
#include <cstdio>
using String=std::string;
int main(){
 const String values[]={"HW51ZEH49GB10829", "a\\b\"c", std::string("ab\x01" "cd",5)};
 for(const auto& psStr:values){
''' + loop + r'''
  printf("{\"ps_serial_number\":\"%s\"}\n",psJson);
 }
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.cpp').write_text(program)
 subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=undefined',str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 out=subprocess.check_output([str(p/'test')],text=True)
 values=[json.loads(line)['ps_serial_number'] for line in out.splitlines()]
 assert values==['HW51ZEH49GB10829','a\\b"c','ab?cd'], values
print('PASS exact MQTT C4 serial escaping: regular, quote/backslash, control')
