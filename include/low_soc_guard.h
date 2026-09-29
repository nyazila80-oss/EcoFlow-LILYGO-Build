#pragma once
#include <Arduino.h>
void lowSocGuardTick();
bool lowSocGuardBlockRequested();
bool lowSocGuardSocBlocked();
const char* lowSocGuardState();
uint32_t lowSocGuardTransitions();

bool lowSocGuardRecoveryPending();
uint32_t lowSocGuardStaleEvents();
