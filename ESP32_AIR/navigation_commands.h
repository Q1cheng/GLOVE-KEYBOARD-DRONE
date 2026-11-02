#pragma once
#include <stdint.h>

// Offline prototype only. Not included by ESP32_AIR.ino or flight validated.

enum NavigationCommandPhase {
    NAV_COMMAND_IDLE, NAV_COMMAND_PREPARE, NAV_COMMAND_PROBE,
    NAV_COMMAND_PULSES, NAV_COMMAND_VERIFY, NAV_COMMAND_ACTIVE, NAV_COMMAND_UNKNOWN
};

struct NavigationFeedback {
    bool armed, fresh, sourceValid, gpsValid, homeValid, failsafeClear;
    bool altitudeHold, positionHold, rth, landing, neutral;
    uint32_t statusTime, navigationTime;
};

// No automatic retry: INAV's manual emergency-landing sequence is a toggle.
struct NavigationCommands {
    NavigationCommandPhase landPhase = NAV_COMMAND_IDLE;
    NavigationCommandPhase rthPhase = NAV_COMMAND_IDLE;
    bool landCancel = false;
    bool rthCancel = false;
    bool landRequested = false;
    bool rthRequested = false;
    bool positionHoldRequested = false;
    uint8_t landRises = 0;
    uint32_t landStarted = 0, landEdge = 0, landVerify = 0, rthStarted = 0;
    uint32_t landStatusTime = 0, landNavigationTime = 0;
    uint32_t rthStatusTime = 0, rthNavigationTime = 0;
    uint32_t lastLandAttempt = 0;
    bool haveLandAttempt = false;

    bool ready(const NavigationFeedback& fc) const {
        return fc.armed && fc.fresh && fc.sourceValid && fc.gpsValid &&
            fc.homeValid && fc.failsafeClear;
    }

    bool landBusy() const {
        return landPhase != NAV_COMMAND_IDLE;
    }

    bool ownsControls() const {
        return landBusy() || rthPhase != NAV_COMMAND_IDLE;
    }

    void unknownLand() {
        landPhase = NAV_COMMAND_UNKNOWN;
        positionHoldRequested = false;
    }

    void requestLand(uint32_t now, const NavigationFeedback& fc) {
        if (!ready(fc) || !fc.neutral || rthPhase != NAV_COMMAND_IDLE || fc.rth ||
            (haveLandAttempt && uint32_t(now - lastLandAttempt) < 5000)) {
            return;
        }
        if (landPhase == NAV_COMMAND_IDLE) {
            if (fc.landing || !fc.altitudeHold || fc.positionHold) {
                return;
            }
            landCancel = false;
        } else if (landPhase == NAV_COMMAND_ACTIVE && fc.landing) {
            landCancel = true;
        } else {
            return;
        }
        landRequested = !landCancel;
        landPhase = NAV_COMMAND_PREPARE;
        positionHoldRequested = false;
        landRises = 0;
        landEdge = now;
        lastLandAttempt = now;
        haveLandAttempt = true;
    }

    void requestRth(uint32_t now, const NavigationFeedback& fc) {
        if (!ready(fc) || !fc.neutral || landBusy() || fc.landing) {
            return;
        }
        if (rthPhase == NAV_COMMAND_IDLE && !fc.rth && fc.altitudeHold) {
            rthCancel = false;
        } else if (rthPhase == NAV_COMMAND_ACTIVE && fc.rth) {
            rthCancel = true;
        } else {
            return;
        }
        rthRequested = !rthCancel;
        rthStarted = now;
        rthStatusTime = fc.statusTime;
        rthNavigationTime = fc.navigationTime;
        rthPhase = NAV_COMMAND_VERIFY;
    }

    void update(uint32_t now, const NavigationFeedback& fc, bool disarm) {
        if (disarm || (fc.fresh && !fc.armed)) {
            *this = NavigationCommands();
            return;
        }
        if (ownsControls() && (!fc.fresh || !fc.sourceValid || !fc.failsafeClear)) {
            if (landBusy()) {
                unknownLand();
            }
            if (rthPhase != NAV_COMMAND_IDLE) {
                rthPhase = NAV_COMMAND_UNKNOWN;
            }
            return;
        }
        if (rthPhase == NAV_COMMAND_ACTIVE && !fc.rth) {
            // An unrequested FC transition is not a confirmed cancellation.
            rthPhase = NAV_COMMAND_UNKNOWN;
        }
        if (rthPhase == NAV_COMMAND_VERIFY) {
            bool freshReply = fc.statusTime != rthStatusTime &&
                fc.navigationTime != rthNavigationTime;
            bool confirmed = rthCancel ? (!fc.rth && !fc.landing && fc.altitudeHold) : fc.rth;
            if (freshReply && confirmed) {
                rthPhase = rthCancel ? NAV_COMMAND_IDLE : NAV_COMMAND_ACTIVE;
            } else if (uint32_t(now - rthStarted) >= 3000) {
                rthPhase = NAV_COMMAND_UNKNOWN;
            }
        }
        if (landPhase == NAV_COMMAND_ACTIVE && !fc.landing) {
            // Automatic touchdown/disarm is handled above; otherwise do not guess.
            unknownLand();
        }
        if (landPhase == NAV_COMMAND_PREPARE && uint32_t(now - landEdge) >= 500) {
            if (!ready(fc)) {
                unknownLand();
                return;
            }
            landStarted = landEdge = now;
            landStatusTime = fc.statusTime;
            landRises = 1;
            positionHoldRequested = true;
            landPhase = landCancel ? NAV_COMMAND_PULSES : NAV_COMMAND_PROBE;
        }
        if (landPhase == NAV_COMMAND_PROBE) {
            // Before the remaining four rises, require FC-confirmed POSHOLD.
            // This checks the CH7 assignment and navigation readiness, not GPS count.
            if (fc.positionHold && fc.statusTime != landStatusTime) {
                positionHoldRequested = false;
                landEdge = now;
                landPhase = NAV_COMMAND_PULSES;
            } else if (uint32_t(now - landStarted) >= 1500) {
                unknownLand();
            }
        }
        if (landPhase == NAV_COMMAND_PULSES) {
            if (uint32_t(now - landStarted) >= 3500 || !ready(fc)) {
                unknownLand();
                return;
            }
            if (uint32_t(now - landEdge) >= 250) {
                landEdge = now;
                if (positionHoldRequested) {
                    positionHoldRequested = false;
                    if (landRises == 5) {
                        landPhase = NAV_COMMAND_VERIFY;
                        landVerify = now;
                        landStatusTime = fc.statusTime;
                        landNavigationTime = fc.navigationTime;
                    }
                } else {
                    positionHoldRequested = true;
                    landRises++;
                }
            }
        }
        if (landPhase == NAV_COMMAND_VERIFY) {
            bool freshReply = fc.statusTime != landStatusTime &&
                fc.navigationTime != landNavigationTime;
            bool confirmed = landCancel ? (!fc.landing && fc.altitudeHold && !fc.rth) : fc.landing;
            if (freshReply && confirmed) {
                landPhase = landCancel ? NAV_COMMAND_IDLE : NAV_COMMAND_ACTIVE;
            } else if (uint32_t(now - landVerify) >= 3000) {
                unknownLand();
            }
        }
    }
};
