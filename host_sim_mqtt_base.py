"""Compile exact MQTT topic-base validation with host String shim."""
from pathlib import Path
import subprocess,tempfile
src=Path('src/mqtt.cpp').read_text()
fn=src[src.index('bool mqttBaseValid('):src.index('static void rebuildHotTopics()')]
program=r'''
#include <string>
#include <cctype>
#include <cassert>
struct String:std::string{using std::string::string; bool isEmpty()const{return empty();}};
''' + fn + r'''
int main(){
 assert(mqttBaseValid(String("ecoflow_bridge")));
 assert(mqttBaseValid(String("home/energy.1")));
 assert(!mqttBaseValid(String("")));
 assert(!mqttBaseValid(String("/root")));
 assert(!mqttBaseValid(String("root/")));
 assert(!mqttBaseValid(String("root//x")));
 assert(!mqttBaseValid(String("x/#")));
 assert(!mqttBaseValid(String("x/+")));
 assert(!mqttBaseValid(String("x/\"bad")));
 assert(!mqttBaseValid(String(65,'a')));
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'t.cpp').write_text(program)
 subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=undefined',str(p/'t.cpp'),'-o',str(p/'t')],check=True)
 subprocess.run([str(p/'t')],check=True)
web=Path('src/web.cpp').read_text().split('server.on(AsyncURIMatcher::exact("/api/net"), HTTP_POST,',1)[1]
assert web.index('if(!mqttBaseValid(mbase))') < web.index('wifiSaveCredentialsDeferred(ssid, pass)')
assert web.index('if(!portValid||portLong==0)') < web.index('wifiSaveCredentialsDeferred(ssid, pass)')
assert 'if(!mqttBaseValid(mqttCfg.base))mqttCfg.enabled=false;' in src
print('PASS MQTT base: valid topics, wildcards, quotes, empty components, length')
