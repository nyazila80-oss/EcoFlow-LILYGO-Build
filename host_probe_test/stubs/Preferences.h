#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <map>
#include <string>
#include <vector>
extern bool failNextPut;
extern std::map<std::string, std::vector<uint8_t>> fakeNvs;
class Preferences {
  bool open_{false};
  std::string ns_;
public:
  bool begin(const char* name, bool readOnly=false) {
    ns_=name;
    if(readOnly && !fakeNvs.count(ns_)) return false;
    if(!readOnly) fakeNvs.try_emplace(ns_);
    open_=true;
    return true;
  }
  size_t getBytesLength(const char*) const { return open_ ? fakeNvs[ns_].size() : 0; }
  size_t getBytes(const char*, void* out, size_t length) const {
    const auto& v=fakeNvs[ns_];
    if(!open_ || v.size()!=length) return 0;
    std::memcpy(out,v.data(),length);
    return length;
  }
  size_t putBytes(const char*, const void* data, size_t length) {
    if(!open_ || failNextPut) { failNextPut=false; return 0; }
    auto& v=fakeNvs[ns_];
    const auto* p=static_cast<const uint8_t*>(data);
    v.assign(p,p+length);
    return length;
  }
  void end() { open_=false; }
};
