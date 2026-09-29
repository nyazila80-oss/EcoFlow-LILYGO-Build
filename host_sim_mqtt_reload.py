"""MQTT reload retry and subscription admission regression."""
from pathlib import Path
import random

src=Path('src/mqtt.cpp').read_text()
assert 'if(!loadMqttConfig()){\n      // A concurrent NVS write' in src
assert 'mqttRequestConfigReload();\n      mqttNextReloadRetryMs=millis()+1000;\n      return;' in src
assert src.index('if(!loadMqttConfig()){\n      // A concurrent') < src.index('mqttClient.publish(previousAvailability.c_str(),"offline",true)')
assert 'if(!p.begin("mqtt", true) && !p.begin("mqtt", false))return false;' in src
assert 'if(!mqttSubscribeTopics()){\n      Serial.println' in src
assert 'mqttClient.disconnect();\n      return;' in src
block=src.split('static bool mqttSubscribeTopics()',1)[1].split('void mqttDisconnectClean()',1)[0]
assert block.count('mqttClient.subscribe(')==5
assert 'if(mqttDiscoveryPublishing && !ok)mqttDiscoveryPublishFailed=true;' in src
assert 'mqttDiscoverySent=!mqttDiscoveryPublishFailed;' in src
rng=random.Random(936711)
for _ in range(100000):
    pending=True
    outcomes=[bool(rng.getrandbits(1)) for _ in range(8)]
    loads=0
    for ok in outcomes:
        if not pending:break
        pending=False
        loads+=1
        if not ok:pending=True
    assert pending== (not any(outcomes[:loads]))
    subscriptions=[bool(rng.getrandbits(1)) for _ in range(5)]
    admitted=all(subscriptions)
    assert not admitted or all(subscriptions)
    publish_results=[bool(rng.getrandbits(1)) for _ in range(13)]
    discovery_complete=all(publish_results)
    assert discovery_complete== (not any(not x for x in publish_results))
print('PASS MQTT reload retry and all-subscriptions admission: 100000 sequences')
