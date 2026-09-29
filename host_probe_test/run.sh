#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
c++ -std=c++17 -Wall -Wextra -Werror -Ihost_probe_test/stubs -Iinclude src/ps_probe_trace.cpp host_probe_test/test.cpp -o /tmp/ps_probe_trace_host_test
/tmp/ps_probe_trace_host_test
