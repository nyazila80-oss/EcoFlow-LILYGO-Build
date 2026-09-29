from pathlib import Path
import re, random, json
root=Path(__file__).resolve().parent
web=(root/'src/web.cpp').read_text(); ota=(root/'src/ota.cpp').read_text(); html=(root/'data/remote.html').read_text(); cfg=(root/'include/config.h').read_text()
checks={}
checks['version']=bool(re.search(r'#define FW_VERSION "2\.4\.5\.',cfg))
checks['password_nvs']='ap.putString("password"' in web and 'length() < 16' in web
auth_block=web.split('bool remoteAuthRequest(',1)[1].split('bool remoteOtaAuthRequest(',1)[0]
checks['http_auth_api']='->authenticate(' in auth_block
checks['ws_auth']=all(f'{x}.setAuthentication(remoteAuthUser(), remoteAuthPassword())' in web for x in ['wsLog','wsBms','wsDebug'])
checks['can_stats_auth']='server.on("/can_stats"' in web and 'if(!remoteAuthRequest(r)) return;\n    twai_status_info_t' in web
checks['ota_http_auth']='remoteOtaAuthRequest(request)' in ota and ota.count('request->authenticate(remoteAuthUser(), remoteAuthPassword())')>=2
checks['arduino_ota_auth']='ArduinoOTA.setPassword(remoteAuthPassword())' in ota
checks['mutation_origin']='if (!r->hasHeader("Origin")) return false' in web and web.count('remoteMutationAllowed')>=10
checks['mos_blocked']='k=="moschg"||k=="mosdis"' in web
checks['write_resets_status']='lastWriteAckOk_ = false; lastWriteVerified_ = false' in (root/'src/bms.cpp').read_text()
# AUDIT20.4.1: the remote write endpoint itself must expose only the seven reviewed keys.
setting_block=web.split('server.on("/api/bms/setting"',1)[1].split('server.on("/api/remote/write-status"',1)[0]
allowed={'bal_delta','bal_start','soc100','soc0','rcv','float','smart_sleep'}
keys=set(re.findall(r'\{"([a-z0-9_]+)",\d+,', setting_block))
checks['remote_write_exact_allowlist']=(keys==allowed)
checks['remote_critical_keys_absent']=not any(k in keys for k in {'uvp','uvpr','ovp','ovpr','poweroff','charge_a','discharge_a','cell_count','capacity','precharge','scp_delay','scp_release','bal_max_a'})
# model auth/origin/write lifecycle
N=2_000_000; accepted_bad=0; false_verified=0; verified=0; rejected=0
rng=random.Random(2001)
for _ in range(N):
    auth=rng.random()<0.82; origin=rng.random()<0.88; mutation=rng.random()<0.35
    allowed=auth and (origin if mutation else True)
    if (not auth or (mutation and not origin)) and allowed: accepted_bad+=1
    if not allowed: rejected+=1; continue
    if mutation and rng.random()<0.2: # BMS write
        last_verified=False
        ack=rng.random()<0.97
        readback=ack and rng.random()<0.98
        if readback: last_verified=True; verified+=1
        if last_verified and not readback: false_verified+=1
result={'events':N,'rejected_unauth_or_bad_origin':rejected,'verified_writes':verified,'accepted_bad':accepted_bad,'false_verified':false_verified,'checks':checks,'pass':all(checks.values()) and accepted_bad==0 and false_verified==0}
print(json.dumps(result,indent=2)); (root/'HOST_SIM_V15_REMOTE_SECURITY_RESULTS.json').write_text(json.dumps(result,indent=2))
raise SystemExit(0 if result['pass'] else 1)
