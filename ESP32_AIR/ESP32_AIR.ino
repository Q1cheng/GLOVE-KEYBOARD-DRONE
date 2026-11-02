#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <Adafruit_NeoPixel.h>

bool primaryControlValid = false;
bool fcControlFault = false;
bool previousPrimaryControlValid = false;

// ESP NOW
const uint8_t ESPNOW_CHANNEL = 6;

// GROUND --> AIR PACKET
uint8_t rightMacAddress[6] = {0x44, 0x1B, 0xF6, 0xFF, 0x3A, 0xC0};

volatile bool newGroundPacketAvailable = false;

// Ground packet that is parsed
uint8_t groundPacketBuffer[51];

// Ground packet received buffer
uint8_t groundRxBuffer[51];

portMUX_TYPE groundPacketMux = portMUX_INITIALIZER_UNLOCKED;

uint8_t groundProtocolVersion = 0;
uint8_t groundMessageType = 0;
uint16_t groundPayloadLength = 0;

uint16_t groundReceivedCrc = 0;
uint8_t groundStatusFlags = 0;
uint32_t groundSkippedPackets = 0;
uint16_t groundSequenceNumber = 0;
uint16_t lastGroundSequenceNumber = 0;
bool haveLastGroundSequenceNumber = false;

bool groundLinkValid = false;
unsigned long lastGroundPacketTime = 0;

uint32_t groundTimestampMs = 0;

//Keyboard mode
uint16_t groundControlMask = 0;

bool keyboardPacketValid = false;

// Glove mode
// Left
bool leftGloveValid = false;
bool leftImuValid = false;

float leftQuatW = 1.0f;
float leftQuatX = 0.0f;
float leftQuatY = 0.0f;
float leftQuatZ = 0.0f;

bool leftThumbBent = false;
bool leftIndexBent = false;

bool leftFist = false;
bool leftHandOpen = false;

// Right
bool rightImuValid = false;

float rightQuatW = 1.0f;
float rightQuatX = 0.0f;
float rightQuatY = 0.0f;
float rightQuatZ = 0.0f;

bool rightThumbBent = false;
bool rightIndexBent = false;

bool rightFist = false;
bool rightHandOpen = false;

struct Vec3 {
    float x;
    float y;
    float z;
};

struct Quat {
    float w;
    float x;
    float y;
    float z;
};

Quat leftNeutralQuat = {1.0f, 0.0f, 0.0f, 0.0f};

Quat rightNeutralQuat = {1.0f, 0.0f, 0.0f, 0.0f};

bool gloveOrientationCalibrated = false;
bool gloveOrientationCaptured = false;
bool gloveFlexCalibrated = false;

bool gloveCalibrationHeld = false;
bool gloveCalibrationInProgress = false;
bool gloveCalibrationTriggered = false;
bool gloveCalibrationRejected = false;

unsigned long gloveCalibrationStartTime = 0;

const unsigned long GLOVE_CALIBRATION_TIME = 3000;
const unsigned long GLOVE_CONTROL_DELAY = 5000;
bool gloveControlDelayStarted = false;
bool gloveControlsReady = false;
unsigned long gloveControlDelayStartTime = 0;

// Glove commands
unsigned long gloveRthStartTime = 0;
bool gloveRthTriggered = false; 

unsigned long gloveLandStartTime = 0;
bool gloveLandTriggered = false;

unsigned long gloveArmStartTime = 0;
bool gloveArmTriggered = false;
bool gloveArmGestureAccepted = false;

unsigned long gloveDisarmStartTime = 0;
bool gloveDisarmTriggered = false;
bool gloveDisarmGestureAccepted = false;

unsigned long gloveBuzzerHoldStartTime = 0;
bool gloveBuzzerTriggered = false;
bool gloveBuzzerHoldTriggered = false;

const uint16_t CRSF_MIN = 172;
const uint16_t CRSF_LOW = 752;
const uint16_t CRSF_CENTER = 992;
const uint16_t CRSF_HIGH = 1232;
const uint16_t CRSF_MAX = 1811;



// Glove movement outputs
uint16_t gloveRoll = CRSF_CENTER;
uint16_t glovePitch = CRSF_CENTER;
uint16_t gloveYaw = CRSF_CENTER;
uint16_t gloveThrottle = CRSF_CENTER;


// ELRS mode
bool elrsValid = false;
unsigned long lastElrsPacketTime = 0;

uint16_t elrsRoll = CRSF_CENTER;
uint16_t elrsPitch = CRSF_CENTER;
uint16_t elrsYaw = CRSF_CENTER;
uint16_t elrsThrottle = CRSF_CENTER;

// CRSF packet
uint8_t crsfBuffer[64];
uint8_t crsfIndex = 0;
uint16_t crsfChannels[16];

// Commands
bool armSwitchCommand = false;
bool landCommand = false;
bool rthCommand = false;
bool manualBuzzerEnabled = false;

// Mode
bool keyboardModeRequest = false;
bool gloveModeRequest = false;
bool elrsModeRequest = false;

bool previousKeyboardModeRequest = false;
bool previousGloveModeRequest = false;
bool previousElrsModeRequest = false;

const uint8_t MODE_NONE = 0;
const uint8_t MODE_KEYBOARD = 1;
const uint8_t MODE_GLOVE = 2;
const uint8_t MODE_ELRS = 3;

uint8_t requestedMode = MODE_NONE;
uint8_t currentMode = MODE_NONE;

// Final controls
uint16_t finalRoll = CRSF_CENTER;
uint16_t finalPitch = CRSF_CENTER;
uint16_t finalYaw = CRSF_CENTER;
uint16_t finalThrottle = CRSF_MIN;

uint16_t keyboardRoll = CRSF_CENTER;
uint16_t keyboardPitch = CRSF_CENTER;
uint16_t keyboardYaw = CRSF_CENTER;
uint16_t keyboardThrottle = CRSF_CENTER;

// Current request
bool armRequest = false;
bool disarmRequest = false;
bool rthRequest = false;
bool landRequest = false;
bool keyboardBuzzerState = false;

// Previous Request
bool previousArmRequest = false;
bool previousDisarmRequest = false;
bool previousRthRequest = false;
bool previousLandRequest = false;

// ELRS UART
const uint8_t ELRS_RX_PIN = 17;
const uint8_t ELRS_TX_PIN = 18;

const float DIRECTION_THRESHOLD = 0.75f;

// LEFT PALM
bool leftPalmForward = false;
bool leftPalmBackward = false;
bool leftPalmLeft = false;
bool leftPalmRight = false;
bool leftPalmUp = false;
bool leftPalmDown = false;

// RIGHT PALM
bool rightPalmForward = false;
bool rightPalmBackward = false;
bool rightPalmLeft = false;
bool rightPalmRight = false;
bool rightPalmUp = false;
bool rightPalmDown = false;

// LEFT FINGERS
bool leftFingersForward = false;
bool leftFingersBackward = false;
bool leftFingersLeft = false;
bool leftFingersRight = false;
bool leftFingersUp = false;
bool leftFingersDown = false;

// RIGHT FINGERS
bool rightFingersForward = false;
bool rightFingersBackward = false;
bool rightFingersLeft = false;
bool rightFingersRight = false;
bool rightFingersUp = false;
bool rightFingersDown = false;

// INAV telemetry
bool fcArmed = false;
bool fcRthActive = false;
bool fcLandActive = false;
bool fcLanded = false;
bool fcFailsafeActive = false;
bool fcFlightMode = false;
bool fcAltHoldActive = false;

// FC -> Air CRSF receive buffer
uint8_t fcRxBuffer[64];
uint8_t fcRxIndex = 0;

// General FC telemetry connection
bool fcTelemetryValid = false;
unsigned long lastFcTelemetryTime = 0;

const unsigned long FC_TELEMETRY_TIMEOUT = 500;

// CRSF main telemetry
// GPS - CRSF 0x02
bool fcGpsValid = false;

int32_t fcLatitudeE7 = 0;
int32_t fcLongitudeE7 = 0;

uint16_t fcGroundSpeedDeciKph = 0;
uint16_t fcGpsCourseCentideg = 0;

int32_t fcGpsAltitudeM = 0;

uint8_t fcSatelliteCount = 0;


// Vario - CRSF 0x07
bool fcVarioValid = false;

int16_t fcVerticalSpeedCms = 0;


// Battery - CRSF 0x08
bool fcBatteryValid = false;

uint16_t fcBatteryVoltageDeciV = 0;
uint16_t fcBatteryCurrentDeciA = 0;

uint32_t fcMahUsed = 0;

uint8_t fcBatteryPercent = 0;


// Barometer - CRSF 0x09
bool fcBaroValid = false;

int32_t fcBaroAltitudeDm = 0;


// ESC RPM - CRSF 0x0C
bool fcRpmValid = false;

int32_t fcMotorRpm[4] = {0, 0, 0, 0};


// ESC temperature - CRSF 0x0D
bool fcTemperatureValid = false;

uint8_t fcEscTemperatureCount = 0;
int16_t fcEscTemperatureDeciC[4] = {0, 0, 0, 0};


// Attitude - CRSF 0x1E
bool fcAttitudeValid = false;

int16_t fcPitchRad10000 = 0;
int16_t fcRollRad10000 = 0;
int16_t fcYawRad10000 = 0;


// Failsafe from flight mode - CRSF 0x21
bool fcFailsafeStatusValid = false;

unsigned long lastFcGpsTime = 0;
unsigned long lastFcVarioTime = 0;
unsigned long lastFcBatteryTime = 0;
unsigned long lastFcBaroTime = 0;
unsigned long lastFcRpmTime = 0;
unsigned long lastFcTemperatureTime = 0;
unsigned long lastFcAttitudeTime = 0;
unsigned long lastFcFailsafeTime = 0;

// MSP command IDs
const uint16_t MSP_RC_COMMAND = 105;
const uint16_t MSP_BOXIDS_COMMAND = 119;
const uint16_t MSP_NAV_STATUS_COMMAND = 121;
const uint16_t MSP2_INAV_STATUS_COMMAND = 0x2000;
const uint16_t MSP_COMP_GPS_COMMAND = 107;

const uint8_t INAV_BOX_NAV_ALTHOLD_PERMANENT_ID = 3;

// MSP2 INAV STATUS
uint16_t fcCycleTimeUs = 0;

uint16_t fcI2cErrorCount = 0;

uint16_t fcSensorStatus = 0;

uint16_t fcSystemLoadPercent = 0;

uint8_t fcConfigProfile = 0;
uint8_t fcBatteryProfile = 0;

uint32_t fcArmingFlags = 0;

uint32_t fcActiveModeFlagsLow = 0;
uint32_t fcActiveModeFlagsHigh = 0;

bool fcBoxIdsValid = false;
int8_t fcAltHoldModeBitIndex = -1;

uint8_t fcMixerProfile = 0;

// Derived
bool fcStatusValid = false;

unsigned long lastFcStatusTime = 0;
const unsigned long FC_STATUS_TIMEOUT = 1500;

bool fcArmStateMatchesCommand = false;

// MSP NAV STATUS
bool fcNavStatusValid = false;

uint8_t fcNavMode = 0;
uint8_t fcNavState = 0;
uint8_t fcNavError = 0;

bool fcLandingActive = false;

unsigned long lastFcNavStatusTime = 0;
const unsigned long FC_NAV_STATUS_TIMEOUT = 1000;

// MSP_RC
bool fcRcCheckValid = false;
uint8_t fcRcAccuracyPercent = 0;

uint16_t expectedRcForCheck[8];

unsigned long lastFcRcCheckTime = 0;
const unsigned long FC_RC_CHECK_TIMEOUT = 1500;

const uint16_t RC_CHECK_TOLERANCE = 10;

// MSP_COMP_GPS
bool fcHomeDataValid = false;

uint16_t fcDistanceToHomeM = 0;
int16_t fcDirectionToHomeDeg = 0;

bool fcGpsHeartbeat = false;

unsigned long lastFcHomeDataTime = 0;
const unsigned long FC_HOME_DATA_TIMEOUT = 1500;

// MSP scheduler
uint8_t mspRequestSlot = 0;
unsigned long lastMspRequestTime = 0;

const unsigned long MSP_REQUEST_INTERVAL = 125;

// Queued MSP request
bool mspRequestPending = false;
uint16_t pendingMspCommandID = 0;
unsigned long mspRequestSentTime = 0;

const unsigned long MSP_RESPONSE_TIMEOUT = 200;

HardwareSerial ElrsSerial(2);

// STM32
const uint8_t FC_RX_PIN = 7;  
const uint8_t FC_TX_PIN = 6;  

HardwareSerial FcSerial(1);

// CRSF output to flight controller
uint16_t fcChannels[16];
uint8_t fcCrsfFrame[26];

unsigned long lastFcSendTime = 0;

const unsigned long FC_SEND_INTERVAL = 10;

// CRSF telemtry timing
uint8_t groundPacketsSinceTelemetry = 0;

bool telemetrySendScheduled = false;

uint32_t telemetrySendTargetUs = 0;

bool espNowReady = false;
uint8_t espNowErrorFlags = 0;

const uint8_t ESPNOW_ERROR_CHANNEL = 1 << 0;
const uint8_t ESPNOW_ERROR_INIT = 1 << 1;
const uint8_t ESPNOW_ERROR_PEER = 1 << 2;

// AIR --> GROUND PACKET
const uint8_t AIR_TELEMETRY_VERSION = 1;
const uint8_t AIR_TELEMETRY_TYPE = 0x51;
const uint16_t AIR_TELEMETRY_PAYLOAD_LENGTH = 103;

const size_t AIR_TELEMETRY_PACKET_MAX_SIZE = 128;

uint8_t airTelemetryPacket[AIR_TELEMETRY_PACKET_MAX_SIZE];

uint16_t airTelemetrySequence = 0;

// Buzzer and LED
const uint8_t LED_PIN = 4;   
const uint8_t BUZZER_PIN = 5;   

const uint8_t LED_COUNT = 10;

Adafruit_NeoPixel statusLed(LED_COUNT, LED_PIN, NEO_GRB + NEO_KHZ800);

bool previousFcArmedForAlert = false;

enum BuzzerPattern {
    BUZZER_PATTERN_NONE,
    BUZZER_PATTERN_ARM,
    BUZZER_PATTERN_DISARM
};

enum BuzzerSource {
    BUZZER_SOURCE_NONE,
    BUZZER_SOURCE_MANUAL,
    BUZZER_SOURCE_ARM,
    BUZZER_SOURCE_DISARM,
    BUZZER_SOURCE_LANDED
};

BuzzerPattern buzzerPattern = BUZZER_PATTERN_NONE;

unsigned long buzzerPatternStartTime = 0;

bool previousFcArmed = false;

bool previousFcArmedInitialized = false; // do we know what the inifital armed state is?

// LED timing
bool statusLedState = false;

unsigned long lastStatusLedToggleTime = 0;

struct TelemetrySnapshot;

// CRSF telemtry parsing
// GPS
void parseCrsfGps(const uint8_t* payload, uint8_t payloadLength) {
    if (payloadLength < 15) {
        return;
    }

    fcLatitudeE7 = readInt32BE(payload + 0);

    fcLongitudeE7 = readInt32BE(payload + 4);

    fcGroundSpeedDeciKph = readUint16BE(payload + 8);

    fcGpsCourseCentideg = readUint16BE(payload + 10);

    uint16_t altitudeRaw = readUint16BE(payload + 12);

    fcGpsAltitudeM = (int32_t)altitudeRaw - 1000;

    fcSatelliteCount = payload[14];

    fcGpsValid = true;

    lastFcGpsTime = millis();
}

// Vario
void parseCrsfVario(const uint8_t* payload, uint8_t payloadLength) {
    if (payloadLength < 2) {
        return;
    }

    fcVerticalSpeedCms = readInt16BE(payload);

    fcVarioValid = true;

    lastFcVarioTime = millis();
}

// Battery
void parseCrsfBattery(const uint8_t* payload, uint8_t payloadLength) {
    if (payloadLength < 8) {
        return;
    }

    fcBatteryVoltageDeciV = readUint16BE(payload + 0);

    fcBatteryCurrentDeciA = readUint16BE(payload + 2);

    fcMahUsed = readUint24BE(payload + 4);

    fcBatteryPercent = payload[7];

    fcBatteryValid = true;

    lastFcBatteryTime = millis();
}

// Barometer
void parseCrsfBaro(const uint8_t* payload, uint8_t payloadLength) {
    if (payloadLength < 2) {
        return;
    }

    uint16_t packedAltitude = readUint16BE(payload);

    if ((packedAltitude & 0x8000) != 0) { // High bit = 1
        uint16_t altitudeM = packedAltitude & 0x7FFF;

        fcBaroAltitudeDm = (int32_t)altitudeM * 10; // M -> Dm
    }

    else { // High bit = 0 
        fcBaroAltitudeDm = (int32_t)packedAltitude - 10000; // Already Dm
    }

    fcBaroValid = true;

    lastFcBaroTime = millis();
}

// ESC RPM
void parseCrsfRpm(const uint8_t* payload, uint8_t payloadLength) {
    if (payloadLength < 4) {
        return;
    }

    uint8_t sourceId = payload[0];

    if (sourceId != 0) {
        return;
    }

    uint8_t rpmCount = (payloadLength - 1) / 3;

    for (uint8_t i = 0; i < 4; i++) {
        fcMotorRpm[i] = 0;
    }

    if (rpmCount > 4) {
        rpmCount = 4;
    }

    for (uint8_t i = 0; i < rpmCount; i++) {
        fcMotorRpm[i] = readInt24BE( payload + 1 + (i * 3)); // skip ID and index by 3
    }

    fcRpmValid = true;

    lastFcRpmTime = millis();
}

// Temperature
void parseCrsfTemperature(const uint8_t* payload, uint8_t payloadLength) {
    if (payloadLength < 3) {
        return;
    }

    uint8_t sourceId = payload[0];

    if (sourceId != 0) {
        return;
    }

    uint8_t temperatureCount = (payloadLength - 1) / 2;

    // Clear old values.
    for (uint8_t i = 0; i < 4; i++) {
        fcEscTemperatureDeciC[i] = 0;
    }

    if (temperatureCount > 4) {
        temperatureCount = 4;
    }

    fcEscTemperatureCount = temperatureCount;

    for (uint8_t i = 0;
        i < temperatureCount;
        i++) {

        fcEscTemperatureDeciC[i] = readInt16BE(payload + 1 + (i * 2));
    }

    fcTemperatureValid = true;

    lastFcTemperatureTime = millis();
}

// Attitude
void parseCrsfAttitude(const uint8_t* payload, uint8_t payloadLength) {
    if (payloadLength < 6) {
        return;
    }

    fcPitchRad10000 = readInt16BE(payload + 0);

    fcRollRad10000 = readInt16BE(payload + 2);

    fcYawRad10000 = readInt16BE(payload + 4);

    fcAttitudeValid = true;

    lastFcAttitudeTime = millis();
}

// Flight mode
void parseCrsfFlightMode(const uint8_t* payload, uint8_t payloadLength) {
    fcFailsafeActive = false;

    if (payloadLength >= 4) {
        if (payload[0] == '!' && payload[1] == 'F' && payload[2] == 'S' && payload[3] == '!') {
            fcFailsafeActive = true;
        }
    }

    fcFailsafeStatusValid = true;

    lastFcFailsafeTime = millis();
}

// ESP NOW
void onGroundPacketReceived(const esp_now_recv_info_t *info, const uint8_t *data, int length) {
    if (length != 51 || info == nullptr || memcmp(info->src_addr, rightMacAddress, 6) != 0) {
        return;
    }

    portENTER_CRITICAL(&groundPacketMux);

    memcpy(groundRxBuffer, data, 51);

    newGroundPacketAvailable = true;

    portEXIT_CRITICAL(&groundPacketMux);
}

// LE decoders
uint8_t readUint8LE(const uint8_t* buffer, uint8_t& index) {
    uint8_t value = buffer[index];
    index++;
    return value;
}

uint16_t readUint16LE(const uint8_t* buffer, uint8_t& index) {
    uint16_t value =
        buffer[index] |
        ((uint16_t)buffer[index + 1] << 8);

    index += 2;
    return value;
}

uint32_t readUint32LE(const uint8_t* buffer, uint8_t& index) {
    uint32_t value =
        ((uint32_t)buffer[index]) |
        ((uint32_t)buffer[index + 1] << 8) |
        ((uint32_t)buffer[index + 2] << 16) |
        ((uint32_t)buffer[index + 3] << 24);

    index += 4;
    return value;
}

// LE readers
uint16_t readUint16LE(const uint8_t* data) {
    return
        ((uint16_t)data[0]) |
        ((uint16_t)data[1] << 8);
}


uint32_t readUint32LE(const uint8_t* data) {
    return
        ((uint32_t)data[0]) |
        ((uint32_t)data[1] << 8) |
        ((uint32_t)data[2] << 16) |
        ((uint32_t)data[3] << 24);
}

float readFloat32LE(const uint8_t* buffer, uint8_t& index) {
    uint32_t bits = readUint32LE(buffer, index);

    float value;
    memcpy(&value, &bits, sizeof(float));

    return value;
}

// LE encoders
void writeUint8LE(uint8_t* buffer, uint8_t& index, uint8_t value) {
    buffer[index] = value;
    index++;
}

void writeUint16LE(uint8_t* buffer, uint8_t& index, uint16_t value) {
    buffer[index] = value & 0xFF;
    buffer[index + 1] = (value >> 8) & 0xFF;
    index += 2;
}

void writeUint32LE(uint8_t* buffer, uint8_t& index, uint32_t value) {
    buffer[index] = value & 0xFF;
    buffer[index + 1] = (value >> 8) & 0xFF;
    buffer[index + 2] = (value >> 16) & 0xFF;
    buffer[index + 3] = (value >> 24) & 0xFF;
    index += 4;
}

void writeFloat32LE(uint8_t* buffer, uint8_t& index, float value) {
    uint32_t bits;

    memcpy(&bits, &value, sizeof(float));

    writeUint32LE(buffer, index, bits);
}

uint16_t crc16CcittFalse(const uint8_t* data, size_t length) {
    uint16_t crc = 0xFFFF;

    for (size_t i = 0; i < length; i++) {
        crc ^= ((uint16_t)data[i] << 8);

        for (uint8_t bit = 0; bit < 8; bit++) {
            if (crc & 0x8000) {
                crc = (crc << 1) ^ 0x1021;
            } else {
                crc = crc << 1;
            }
        }
    }

    return crc;
}

uint8_t crsfCrc8(const uint8_t* data, uint8_t length) {
    uint8_t crc = 0;

    for (uint8_t i = 0; i < length; i++) {
        crc ^= data[i];

        for (uint8_t bit = 0; bit < 8; bit++) {
            if (crc & 0x80) {
                crc = (crc << 1) ^ 0xD5;
            } else {
                crc <<= 1;
            }
        }
    }

    return crc;
}

// BE encoders
void writeUint8BE(uint8_t* buffer, uint8_t& index, uint8_t value) {
    buffer[index] = value;
    index++;
}

void writeUint16BE(uint8_t* buffer, uint8_t& index, uint16_t value) {
    buffer[index] = (value >> 8) & 0xFF;
    buffer[index + 1] = value & 0xFF;
    index += 2;
}

void writeInt16BE(uint8_t* buffer, uint8_t& index, int16_t value) {
    uint16_t unsignedValue = (uint16_t)value;
    buffer[index] = (unsignedValue >> 8) & 0xFF;
    buffer[index + 1] = unsignedValue & 0xFF;
    index += 2;
}

void writeUint32BE(uint8_t* buffer, uint8_t& index, uint32_t value) {
    buffer[index] = (value >> 24) & 0xFF;
    buffer[index + 1] = (value >> 16) & 0xFF;
    buffer[index + 2] = (value >> 8) & 0xFF;
    buffer[index + 3] = value & 0xFF;
    index += 4;
}

void writeInt32BE(uint8_t* buffer, uint8_t& index, int32_t value) {
    uint32_t unsignedValue = (uint32_t)value;
    buffer[index] = (unsignedValue >> 24) & 0xFF;
    buffer[index + 1] = (unsignedValue >> 16) & 0xFF;
    buffer[index + 2] = (unsignedValue >> 8) & 0xFF;
    buffer[index + 3] = unsignedValue & 0xFF;
    index += 4;
}

// BE decoders
uint16_t readUint16BE(const uint8_t* data) {
    return
        ((uint16_t)data[0] << 8) |
        ((uint16_t)data[1]);
}

int16_t readInt16BE(const uint8_t* data) {

    return (int16_t)readUint16BE(data);
}

int32_t readInt32BE(const uint8_t* data) {
    uint32_t value =
        ((uint32_t)data[0] << 24) |
        ((uint32_t)data[1] << 16) |
        ((uint32_t)data[2] << 8) |
        ((uint32_t)data[3]);
    return (int32_t)value;
}

uint32_t readUint24BE(const uint8_t* data) {

    return
        ((uint32_t)data[0] << 16) |
        ((uint32_t)data[1] << 8) |
        ((uint32_t)data[2]);
}

int32_t readInt24BE(const uint8_t* data) {

    uint32_t value = readUint24BE(data);

    // If bit 23 is set, the number is negative.
    if (value & 0x00800000) {
        value |= 0xFF000000;
    }

    return (int32_t)value;
}


// Update Keyboard
void updateKeyboardControls() {

    keyboardRoll = CRSF_CENTER;
    keyboardPitch = CRSF_CENTER;
    keyboardYaw = CRSF_CENTER;
    keyboardThrottle = CRSF_CENTER;

    // Decode movement bits
    bool wHeld = (groundControlMask & (1U << 0)) != 0;

    bool sHeld = (groundControlMask & (1U << 1)) != 0;

    bool aHeld = (groundControlMask & (1U << 2)) != 0;

    bool dHeld = (groundControlMask & (1U << 3)) != 0;

    bool upHeld = (groundControlMask & (1U << 4)) != 0;

    bool downHeld = (groundControlMask & (1U << 5)) != 0;

    bool leftHeld = (groundControlMask & (1U << 6)) != 0;

    bool rightHeld = (groundControlMask & (1U << 7)) != 0;

    // PITCH
    if (wHeld && !sHeld) {
        keyboardPitch = CRSF_HIGH;
    }
    else if (sHeld && !wHeld) {
        keyboardPitch = CRSF_LOW;
    }

    // ROLL
    if (dHeld && !aHeld) {
        keyboardRoll = CRSF_HIGH;
    }
    else if (aHeld && !dHeld) {
        keyboardRoll = CRSF_LOW;
    }

    // THROTTLE
    if (upHeld && !downHeld) {
        keyboardThrottle = CRSF_HIGH;
    }
    else if (downHeld && !upHeld) {
        keyboardThrottle = CRSF_LOW;
    }

    // YAW
    if (rightHeld && !leftHeld) {
        keyboardYaw = CRSF_HIGH;
    }
    else if (leftHeld && !rightHeld) {
        keyboardYaw = CRSF_LOW;
    }
}

// Globes
// Palm Math
Vec3 getPalmDirection(float qw, float qx, float qy, float qz) {
    Vec3 palm;

    palm.x = -2.0f * (qx * qz + qw * qy);
    palm.y = 2.0f * (qw * qx - qy * qz);
    palm.z = 2.0f * (qx * qx + qy * qy) - 1.0f;

    return palm;
}

// Finger Math
Vec3 getFingerDirection(float qw, float qx, float qy, float qz) {
    Vec3 fingers;

    fingers.x = 2.0f * (qx * qy - qw * qz);
    fingers.y = 1.0f - 2.0f * (qx * qx + qz * qz);
    fingers.z = 2.0f * (qw * qx + qy * qz);
    return fingers;
}

Quat inverseQuaternion(Quat q) {
    Quat result;

    result.w = q.w;
    result.x = -q.x;
    result.y = -q.y;
    result.z = -q.z;

    return result;
}

Quat multiplyQuaternions(Quat a, Quat b) {
    Quat result;

    result.w = a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z;

    result.x = a.w * b.x + a.x * b.w +a.y * b.z - a.z * b.y;

    result.y = a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x;

    result.z = a.w * b.z + a.x * b.y - a.y * b.x +a.z * b.w;

    return result;
}

void updateGloveOrientation() {

    // Raw values
    Quat currentLeft = {leftQuatW, leftQuatX, leftQuatY, leftQuatZ};
    Quat currentRight = {rightQuatW, rightQuatX, rightQuatY, rightQuatZ};

    // Relative values to neutral 
    Quat leftRelative = multiplyQuaternions(inverseQuaternion(leftNeutralQuat), currentLeft);
    Quat rightRelative = multiplyQuaternions(inverseQuaternion(rightNeutralQuat), currentRight);

    // Directioms
    Vec3 leftPalmDirection = getPalmDirection(leftRelative.w, leftRelative.x, leftRelative.y, leftRelative.z);

    Vec3 leftFingersDirection = getFingerDirection(leftRelative.w, leftRelative.x, leftRelative.y, leftRelative.z);

    Vec3 rightPalmDirection = getPalmDirection(rightRelative.w, rightRelative.x, rightRelative.y, rightRelative.z);

    Vec3 rightFingersDirection = getFingerDirection(rightRelative.w, rightRelative.x, rightRelative.y, rightRelative.z);

    // LEFT PALM
    leftPalmRight = leftPalmDirection.x > DIRECTION_THRESHOLD;

    leftPalmLeft = leftPalmDirection.x < -DIRECTION_THRESHOLD;

    leftPalmUp = leftPalmDirection.y > DIRECTION_THRESHOLD;

    leftPalmDown = leftPalmDirection.y < -DIRECTION_THRESHOLD;

    leftPalmForward = leftPalmDirection.z < -DIRECTION_THRESHOLD;

    leftPalmBackward = leftPalmDirection.z > DIRECTION_THRESHOLD;


    // RIGHT PALM
    rightPalmRight = rightPalmDirection.x > DIRECTION_THRESHOLD;

    rightPalmLeft = rightPalmDirection.x < -DIRECTION_THRESHOLD;

    rightPalmUp = rightPalmDirection.y > DIRECTION_THRESHOLD;

    rightPalmDown = rightPalmDirection.y < -DIRECTION_THRESHOLD;

    rightPalmForward = rightPalmDirection.z < -DIRECTION_THRESHOLD;

    rightPalmBackward = rightPalmDirection.z > DIRECTION_THRESHOLD;

    // LEFT FINGERS
    leftFingersRight = leftFingersDirection.x > DIRECTION_THRESHOLD;

    leftFingersLeft = leftFingersDirection.x < -DIRECTION_THRESHOLD;
    
    leftFingersUp = leftFingersDirection.y > DIRECTION_THRESHOLD;

    leftFingersDown = leftFingersDirection.y < -DIRECTION_THRESHOLD;

    leftFingersForward = leftFingersDirection.z < -DIRECTION_THRESHOLD;

    leftFingersBackward = leftFingersDirection.z > DIRECTION_THRESHOLD;

    // RIGHT FINGERS
    rightFingersRight = rightFingersDirection.x > DIRECTION_THRESHOLD;

    rightFingersLeft = rightFingersDirection.x < -DIRECTION_THRESHOLD;

    rightFingersUp = rightFingersDirection.y > DIRECTION_THRESHOLD;

    rightFingersDown = rightFingersDirection.y < -DIRECTION_THRESHOLD;

    rightFingersForward = rightFingersDirection.z < -DIRECTION_THRESHOLD;

    rightFingersBackward = rightFingersDirection.z > DIRECTION_THRESHOLD;
}

void updateGloveCalibration() {
    bool armStateSafe = fcTelemetryValid && fcStatusValid && !fcArmed && !armSwitchCommand &&
        millis() - lastFcTelemetryTime <= FC_TELEMETRY_TIMEOUT &&
        millis() - lastFcStatusTime <= FC_STATUS_TIMEOUT;
    bool sourcesValid = groundLinkValid && leftGloveValid && leftImuValid && rightImuValid;
    if (!sourcesValid) {
        gloveOrientationCaptured = false;
        gloveOrientationCalibrated = false;
    }
    if (gloveOrientationCaptured && !gloveOrientationCalibrated && (!sourcesValid || !armStateSafe)) {
        gloveOrientationCaptured = false;
    }
    if (gloveCalibrationHeld && (!armStateSafe || !sourcesValid || armRequest)) {
        // Reject without disturbing existing controls/calibration on a new attempt.
        // An interrupted accepted capture, however, cannot later become ready.
        if (gloveCalibrationInProgress) {
            gloveOrientationCaptured = false;
            gloveOrientationCalibrated = false;
        }
        gloveCalibrationInProgress = false;
        gloveCalibrationRejected = true;
        return;
    }
    if (gloveCalibrationHeld && gloveCalibrationRejected) {
        return;
    }
    if (!gloveCalibrationHeld) {
        if (gloveCalibrationInProgress) {
            gloveOrientationCaptured = false;
            gloveOrientationCalibrated = false;
        }
        gloveCalibrationRejected = false;
        gloveCalibrationStartTime = 0;
        gloveCalibrationInProgress = false;
        gloveCalibrationTriggered = false;
    } else if (!gloveCalibrationInProgress && !gloveCalibrationTriggered) {
        gloveOrientationCalibrated = false;
        gloveOrientationCaptured = false;
        gloveCalibrationInProgress = true;
        gloveCalibrationStartTime = millis();
    } else if (gloveCalibrationInProgress && !gloveCalibrationTriggered &&
        millis() - gloveCalibrationStartTime >= GLOVE_CALIBRATION_TIME) {
        gloveCalibrationTriggered = true;
        gloveCalibrationInProgress = false;
        if (groundLinkValid && leftGloveValid && leftImuValid && rightImuValid) {
            leftNeutralQuat = {leftQuatW, leftQuatX, leftQuatY, leftQuatZ};
            rightNeutralQuat = {rightQuatW, rightQuatX, rightQuatY, rightQuatZ};
            gloveOrientationCaptured = true;
        }
    }

    if (gloveOrientationCaptured && gloveFlexCalibrated &&
        groundLinkValid && leftGloveValid && leftImuValid && rightImuValid) {
        gloveOrientationCalibrated = true;
    }
}

void updateGloveControlReadiness() {
    bool gloveDataValid = gloveOrientationCalibrated && gloveFlexCalibrated &&
        groundLinkValid && leftGloveValid && leftImuValid && rightImuValid;

    if (!gloveDataValid) {
        gloveControlDelayStarted = false;
        gloveControlsReady = false;
        gloveControlDelayStartTime = 0;
        gloveArmStartTime = 0;
        gloveArmTriggered = false;
        gloveArmGestureAccepted = false;
        gloveDisarmStartTime = 0;
        gloveDisarmTriggered = false;
        gloveDisarmGestureAccepted = false;
        gloveLandTriggered = false;
        gloveRthTriggered = false;
        return;
    }

    if (!gloveControlDelayStarted) {
        gloveControlDelayStarted = true;
        gloveControlDelayStartTime = millis();
        gloveControlsReady = false;
        return;
    }

    if (!gloveControlsReady &&
        millis() - gloveControlDelayStartTime >= GLOVE_CONTROL_DELAY) {
        gloveControlsReady = true;
    }
}

void updateGloveGestureCommands() {
    bool bothPalmsUp = leftPalmUp && rightPalmUp;
    bool bothPalmsDown = leftPalmDown && rightPalmDown;
    bool palmsFacingEachOther = leftPalmRight && rightPalmLeft;
    bool backsFacingEachOther = leftPalmLeft && rightPalmRight;

    if (leftFist && rightFist) {
        gloveArmStartTime = 0;
        gloveArmTriggered = false;
        gloveArmGestureAccepted = false;
        gloveDisarmStartTime = 0;
        gloveDisarmTriggered = false;
        gloveDisarmGestureAccepted = false;
        gloveLandTriggered = false;
        gloveRthTriggered = false;
        return;
    }

    if (bothPalmsUp) {
        if (gloveArmStartTime == 0) {
            gloveArmStartTime = millis();
        }

        if (!gloveArmTriggered && millis() - gloveArmStartTime >= 3000) {
            gloveArmTriggered = true;
            if (fcTelemetryValid && fcStatusValid && !fcArmed && !disarmRequest) {
                armSwitchCommand = true;
                gloveArmGestureAccepted = true;
            }
        }
    } else {
        gloveArmStartTime = 0;
        gloveArmTriggered = false;
        gloveArmGestureAccepted = false;
    }

    if (bothPalmsDown) {
        if (gloveDisarmStartTime == 0) {
            gloveDisarmStartTime = millis();
        }

        if (!gloveDisarmTriggered && millis() - gloveDisarmStartTime >= 3000) {
            gloveDisarmTriggered = true;
            if (!gloveCalibrationInProgress) {
                armSwitchCommand = false;
                gloveDisarmGestureAccepted = true;
            }
        }
    } else {
        gloveDisarmStartTime = 0;
        gloveDisarmTriggered = false;
        gloveDisarmGestureAccepted = false;
    }

    if (palmsFacingEachOther && !gloveLandTriggered) {
        gloveLandTriggered = true;
        // LAND is disabled until the INAV activation/cancellation path is verified.
    } else if (!palmsFacingEachOther) {
        gloveLandTriggered = false;
    }

    if (backsFacingEachOther && !gloveRthTriggered) {
        gloveRthTriggered = true;
        if (fcTelemetryValid && fcStatusValid && fcArmed && fcHomeDataValid) {
            rthCommand = true;
        }
    } else if (!backsFacingEachOther) {
        gloveRthTriggered = false;
    }
}

void updateGloveMovementOutputs() {
    gloveRoll = CRSF_CENTER;
    glovePitch = CRSF_CENTER;
    gloveYaw = CRSF_CENTER;
    gloveThrottle = CRSF_CENTER;

    if (!gloveControlsReady) {
        return;
    }

    bool bothPalmsForward = leftPalmForward && rightPalmForward;
    bool bothPalmsBackward = leftPalmBackward && rightPalmBackward;
    bool bothPalmsUp = leftPalmUp && rightPalmUp;
    bool bothPalmsDown = leftPalmDown && rightPalmDown;
    bool landedArmDisarmHold =
        (bothPalmsUp && !fcArmed) || bothPalmsDown ||
        (bothPalmsUp && gloveArmGestureAccepted) ||
        (bothPalmsDown && gloveDisarmGestureAccepted);

    if (leftFist && rightFist) {
        return;
    }

    if (landedArmDisarmHold) {
        return;
    }

    if (bothPalmsForward && leftHandOpen && rightHandOpen) {
        glovePitch = CRSF_HIGH;
    } else if (bothPalmsBackward && leftHandOpen && rightHandOpen) {
        glovePitch = CRSF_LOW;
    }

    if (leftFist && rightHandOpen && rightPalmForward) {
        gloveRoll = CRSF_HIGH;
    } else if (rightFist && leftHandOpen && leftPalmForward) {
        gloveRoll = CRSF_LOW;
    }

    if (leftFist && rightPalmLeft) {
        gloveYaw = CRSF_LOW;
    } else if (rightFist && leftPalmRight) {
        gloveYaw = CRSF_HIGH;
    }

    if (bothPalmsUp) {
        gloveThrottle = CRSF_HIGH;
    } else if (bothPalmsDown) {
        gloveThrottle = CRSF_LOW;
    }
}

bool setupEspNow() {
    espNowErrorFlags = 0;

    WiFi.mode(WIFI_STA);

    while (!WiFi.STA.started()) {
        delay(10);
    }

    esp_err_t channelResult = esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);

    if (channelResult != ESP_OK) {
        espNowErrorFlags |= ESPNOW_ERROR_CHANNEL;
        return false;
    }

    if (esp_now_init() != ESP_OK) {
        espNowErrorFlags |= ESPNOW_ERROR_INIT;
        return false;
    }

    esp_now_register_recv_cb(onGroundPacketReceived);

    esp_now_peer_info_t rightPeer = {};

    memcpy(rightPeer.peer_addr, rightMacAddress, 6);

    rightPeer.channel = ESPNOW_CHANNEL;
    rightPeer.ifidx = WIFI_IF_STA;
    rightPeer.encrypt = false;

    if (esp_now_add_peer(&rightPeer) != ESP_OK) {
        espNowErrorFlags |= ESPNOW_ERROR_PEER;
        return false;
    }

    return true;
}

void decodeCrsfChannels(const uint8_t* payload) {
    uint32_t bitBuffer = 0;
    uint8_t bitsInBuffer = 0;
    uint8_t payloadIndex = 0;

    for (uint8_t channel = 0; channel < 16; channel++) {

        while (bitsInBuffer < 11) {
            bitBuffer |= ((uint32_t)payload[payloadIndex]) << bitsInBuffer;

            payloadIndex++;
            bitsInBuffer += 8;
        }

        crsfChannels[channel] = bitBuffer & 0x07FF;

        bitBuffer >>= 11;
        bitsInBuffer -= 11;
    }
}

void readElrs() {

    while (ElrsSerial.available() > 0) {

        uint8_t incomingByte = ElrsSerial.read();

        if (crsfIndex == 0) {
            if (incomingByte == 0xC8) {
                crsfBuffer[0] = incomingByte;
                crsfIndex = 1;
            }
            continue;
        }

        if (crsfIndex == 1) {
            crsfBuffer[1] = incomingByte;

            if (incomingByte < 2 || incomingByte > 62) {
                crsfIndex = 0;
                continue;
            }
            crsfIndex = 2;
            continue;
        }

        crsfBuffer[crsfIndex] = incomingByte;
        crsfIndex++;

        uint8_t frameLength = crsfBuffer[1];
        uint8_t totalFrameSize = frameLength + 2;

        if (crsfIndex == totalFrameSize) {
            uint8_t receivedCrc = crsfBuffer[totalFrameSize - 1];

            uint8_t calculatedCrc = crsfCrc8(crsfBuffer + 2, frameLength - 1);

            if (receivedCrc == calculatedCrc) {
                uint8_t frameType = crsfBuffer[2];

                if (frameType == 0x16 && frameLength == 24){
                    decodeCrsfChannels(crsfBuffer + 3);
                    
                    // Update ELRS controls
                    elrsRoll = crsfChannels[0];

                    elrsPitch = crsfChannels[1];

                    elrsThrottle = crsfChannels[2];

                    elrsYaw = crsfChannels[3];

                    elrsValid = true;

                    lastElrsPacketTime = millis();
                }
            }
            crsfIndex = 0;
        }

        // Protection against malformed data
        else if (crsfIndex >= sizeof(crsfBuffer)) {
            crsfIndex = 0;
        }
    }

    // ELRS timeout
    if (elrsValid && millis() - lastElrsPacketTime >= 150) {
        elrsValid = false;

        elrsRoll = CRSF_CENTER;
        elrsPitch = CRSF_CENTER;
        elrsYaw = CRSF_CENTER;
        elrsThrottle = CRSF_CENTER;
    }
}

uint16_t clampCrsf(uint16_t value) {
    if (value < CRSF_MIN) {
        return CRSF_MIN;
    }

    if (value > CRSF_MAX) {
        return CRSF_MAX;
    }

    return value;
}

uint16_t crsfToPwm(uint16_t crsfValue) {
    crsfValue = clampCrsf(crsfValue);

    uint32_t pwm = ((uint32_t)(crsfValue - CRSF_MIN) * 1024) / (CRSF_MAX - CRSF_MIN);

    pwm += 988;

    return (uint16_t)pwm;
}

void snapshotExpectedRcForCheck() {
    for (uint8_t i = 0; i < 8; i++) {
        expectedRcForCheck[i] = crsfToPwm(fcChannels[i]);
    }
}

void sendMspRequest(uint16_t mspCommandID) {
    uint8_t frame[12];

    // CRSF sync
    frame[0] = 0xC8;

    // CRSF payload length not including length and sync 
    frame[1] = 10;

    // CRSF MSP request
    frame[2] = 0x7A;

    // Extended destination = Flight Controller(STM32)
    frame[3] = 0xC8;

    // Extended origin = CRSF receiver(ESP32)
    frame[4] = 0xEC;

    // 0101 0000 = Start chunk MSPv2 sequence 0 no error 
    frame[5] = 0x50;

    // No special MSPv2 flags
    frame[6] = 0x00;

    // MSP Command number -> LE
    frame[7] = mspCommandID & 0xFF;
    frame[8] = (mspCommandID >> 8) & 0xFF;

    // Request has no sent data
    frame[9] = 0x00;
    frame[10] = 0x00;

    // CRSF CRC8
    frame[11] = crsfCrc8(frame + 2, 9);

    FcSerial.write(frame, sizeof(frame));

    mspRequestPending = true;
    pendingMspCommandID = mspCommandID;
    mspRequestSentTime = millis();
}

void readFcCrsf() {
    while (FcSerial.available() > 0) {
        uint8_t incomingByte = FcSerial.read();

        // SYNC
        if (fcRxIndex == 0) {
            if (incomingByte == 0xC8) {
                fcRxBuffer[0] = incomingByte;
                fcRxIndex = 1;
            }
            continue;
        }

        // LENGTH
        if (fcRxIndex == 1) {
            fcRxBuffer[1] = incomingByte;
            if (incomingByte < 2 || incomingByte > 62) {
                fcRxIndex = 0;
                continue;
            }

            fcRxIndex = 2;

            continue;
        }

        // REST OF FRAME

        fcRxBuffer[fcRxIndex] = incomingByte;

        fcRxIndex++;

        uint8_t frameLength = fcRxBuffer[1];

        uint8_t totalFrameSize = frameLength + 2;

        if (fcRxIndex == totalFrameSize) {
            uint8_t receivedCrc = fcRxBuffer[totalFrameSize - 1];

            uint8_t calculatedCrc = crsfCrc8(fcRxBuffer + 2, frameLength - 1);

            if (receivedCrc == calculatedCrc) {

                fcTelemetryValid = true;
                lastFcTelemetryTime = millis();

                uint8_t frameType = fcRxBuffer[2];
                const uint8_t* payload = fcRxBuffer + 3;
                uint8_t payloadLength = frameLength - 2;

                switch (frameType) {
                    case 0x02:
                        parseCrsfGps(payload, payloadLength);
                        break;

                    case 0x07:
                        parseCrsfVario(payload, payloadLength);
                        break;

                    case 0x08:
                        parseCrsfBattery(payload, payloadLength);
                        break;

                    case 0x09:
                        parseCrsfBaro(payload, payloadLength);
                        break;

                    case 0x0C:
                        parseCrsfRpm(payload, payloadLength);
                        break;

                    case 0x0D:
                        parseCrsfTemperature(payload, payloadLength);
                        break;

                    case 0x1E:
                        parseCrsfAttitude(payload, payloadLength);
                        break;

                    case 0x21:
                        parseCrsfFlightMode(payload, payloadLength);
                        break;

                    case 0x7B:
                        handleMspResponse(fcRxBuffer, totalFrameSize);
                        break;

                    default:
                        break;
                }
            }
            fcRxIndex = 0;
        }

        else if (fcRxIndex >= sizeof(fcRxBuffer)) {
            fcRxIndex = 0;
        }
    }

    // General FC telemetry timeout
    if (fcTelemetryValid && millis() - lastFcTelemetryTime > FC_TELEMETRY_TIMEOUT) {
        fcTelemetryValid = false;
        // Cached readings remain unavailable until their own frames return.
        fcGpsValid = false;
        fcVarioValid = false;
        fcBatteryValid = false;
        fcBaroValid = false;
        fcRpmValid = false;
        fcTemperatureValid = false;
        fcAttitudeValid = false;
        fcFailsafeStatusValid = false;
    }
}

void handleMspResponse(const uint8_t* frame, uint8_t totalFrameSize) {
    // MSP status + MSPv2 header + CRC
    if (totalFrameSize < 12) {
        return;
    }

    // CRSF receiver address
    if (frame[3] != 0xEC) {
        return;
    }

    // FC origination
    if (frame[4] != 0xC8) {
        return;
    }

    uint8_t mspStatus = frame[5];

    bool mspError = (mspStatus & 0x80) != 0; // 10000000 & MSP status error check 

    bool mspNewFrame = (mspStatus & 0x10) != 0;

    uint8_t mspVersion = (mspStatus >> 5) & 0x03; // uses 00000011 to isolate version bits

    // Our three responses all fit in
    // a single CRSF MSP response frame.
    if (mspError || !mspNewFrame || mspVersion != 2) {
        return;
    }

    // frame[6] is MSPv2 flags
    uint16_t mspCommandID = ((uint16_t)frame[7]) | ((uint16_t)frame[8] << 8);

    uint16_t mspPayloadLength = ((uint16_t)frame[9]) | ((uint16_t)frame[10] << 8);

    uint16_t bytesAvailable = totalFrameSize - 12;

    if (mspPayloadLength > bytesAvailable) {
        return;
    }

    const uint8_t* mspPayload = frame + 11;

    if (mspCommandID == MSP2_INAV_STATUS_COMMAND) {
        parseMsp2InavStatus(mspPayload, mspPayloadLength);
    }

    else if (mspCommandID == MSP_NAV_STATUS_COMMAND) {
        parseMspNavStatus(mspPayload, mspPayloadLength);
    }

    else if (mspCommandID == MSP_RC_COMMAND) {
        parseMspRc(mspPayload, mspPayloadLength);
    }

    else if (mspCommandID == MSP_COMP_GPS_COMMAND) {
        parseMspCompGps(mspPayload, mspPayloadLength);
    }

    else if (mspCommandID == MSP_BOXIDS_COMMAND) {
        parseMspBoxIds(mspPayload, mspPayloadLength);
    }

    // Response arrived
    if (mspRequestPending && mspCommandID == pendingMspCommandID) {
        mspRequestPending = false;
    }
}

void parseMspRc(const uint8_t* payload, uint16_t payloadLength) {
    const uint8_t channelsChecked = 8;

    // Need at least CH1-CH8
    // 11 bit channels
    if (payloadLength < channelsChecked * 2) {
        return;
    }

    uint8_t wrongCount = 0;

    for (uint8_t i = 0; i < channelsChecked; i++) {

        uint16_t actualRc = readUint16LE(payload + (i * 2)); // index 2 at a time 

        int difference = (int)expectedRcForCheck[i] - (int)actualRc;

        if (difference < 0) {
            difference = -difference;
        }

        if (difference > RC_CHECK_TOLERANCE) {
            wrongCount++;
        }
    }

    uint8_t matchedCount = channelsChecked - wrongCount;

    // Rounded percentage
    fcRcAccuracyPercent = (matchedCount * 100 + channelsChecked / 2) / channelsChecked;

    fcRcCheckValid = true;
    lastFcRcCheckTime = millis();
}

void parseMspBoxIds(const uint8_t* payload, uint16_t payloadLength) {
    fcBoxIdsValid = false;
    fcAltHoldModeBitIndex = -1;

    // MSP_BOXIDS returns each active mode's permanent ID in the same order
    // used by the active-mode bitmask in MSP2_INAV_STATUS.
    const uint16_t modeCount = payloadLength < 64 ? payloadLength : 64;
    for (uint16_t i = 0; i < modeCount; i++) {
        if (payload[i] == INAV_BOX_NAV_ALTHOLD_PERMANENT_ID) {
            fcAltHoldModeBitIndex = (int8_t)i;
            fcBoxIdsValid = true;
            break;
        }
    }
}

void parseMsp2InavStatus(const uint8_t* payload, uint16_t payloadLength) {
    if (payloadLength < 22) {
        return;
    }

    // Bytes 0-1: FC cycle time
    fcCycleTimeUs = readUint16LE(payload + 0);

    // Bytes 2-3: I2C error counter
    fcI2cErrorCount = readUint16LE(payload + 2);

    // Bytes 4-5: sensor status bitmask
    fcSensorStatus = readUint16LE(payload + 4);

    // Bytes 6-7: average system load
    fcSystemLoadPercent = readUint16LE(payload + 6);

    // Byte 8:
    // upper 4 bits = battery profile
    // lower 4 bits = config profile
    uint8_t profileByte = payload[8];

    fcConfigProfile = profileByte & 0x0F;
    fcBatteryProfile = (profileByte >> 4) & 0x0F;

    // Bytes 9-12: full arming flags
    fcArmingFlags = readUint32LE(payload + 9);

    fcArmed = (fcArmingFlags & (1UL << 2)) != 0;
    fcArmStateMatchesCommand = (armSwitchCommand == fcArmed);

    // Bytes 13-20: full 60-bit box/mode bitmask
    fcActiveModeFlagsLow = readUint32LE(payload + 13);

    fcActiveModeFlagsHigh = readUint32LE(payload + 17);

    fcAltHoldActive = false;
    if (fcBoxIdsValid && fcAltHoldModeBitIndex >= 0) {
        if (fcAltHoldModeBitIndex < 32) {
            fcAltHoldActive = (fcActiveModeFlagsLow & (1UL << fcAltHoldModeBitIndex)) != 0;
        }
        else {
            fcAltHoldActive = (fcActiveModeFlagsHigh & (1UL << (fcAltHoldModeBitIndex - 32))) != 0;
        }
    }

    // Byte 21: mixer profile
    fcMixerProfile = payload[21];

    fcStatusValid = true;
    lastFcStatusTime = millis();
}

void parseMspNavStatus(const uint8_t* payload, uint16_t payloadLength) {
    if (payloadLength < 7) {
        return;
    }

    fcNavMode = payload[0];
    fcNavState = payload[1];
    fcNavError = payload[4];

    // RTH
    // MW_GPS_MODE_RTH = 2
    if (fcNavMode == 2) {
        fcRthActive = true;
    }
    else {
        fcRthActive = false;
    }

    // LANDING
    fcLandingActive = false;

    // MW_NAV_STATE_LAND_START = 8
    if (fcNavState == 8) {
        fcLandingActive = true;
    }

    // MW_NAV_STATE_LAND_IN_PROGRESS = 9
    else if (fcNavState == 9) {
        fcLandingActive = true;
    }

    // MW_NAV_STATE_LAND_SETTLE = 11
    else if (fcNavState == 11) {
        fcLandingActive = true;
    }

    // MW_NAV_STATE_LAND_START_DESCENT = 12
    else if (fcNavState == 12) {
        fcLandingActive = true;
    }

    // MW_NAV_STATE_EMERGENCY_LANDING = 14
    else if (fcNavState == 14) {
        fcLandingActive = true;
    }

    // LANDED
    // MW_NAV_STATE_LANDED = 10
    if (fcNavState == 10) {
        fcLanded = true;
    }
    else {
        fcLanded = false;
    }

    fcNavStatusValid = true;
    lastFcNavStatusTime = millis();
}

void parseMspCompGps(const uint8_t* payload, uint16_t payloadLength) {
    if (payloadLength < 5) {
        return;
    }

    fcDistanceToHomeM = readUint16LE(payload + 0);

    fcDirectionToHomeDeg = (int16_t)readUint16LE(payload + 2);

    fcGpsHeartbeat = payload[4] != 0;

    fcHomeDataValid = true;

    lastFcHomeDataTime = millis();
}

void updateMspRequests() {
    // Pending request timeout
    if (mspRequestPending) {
        if (millis() - mspRequestSentTime < MSP_RESPONSE_TIMEOUT) {
            return;
        }

        // No usable response arrived.
        mspRequestPending = false;
    }

    // Scheduler timing
    if (millis() - lastMspRequestTime < MSP_REQUEST_INTERVAL) {
        return;
    }

    lastMspRequestTime = millis();

    // SLOT 0
    // NAV STATUS
    if (mspRequestSlot == 0) {
        sendMspRequest(MSP_NAV_STATUS_COMMAND);
    }

    // SLOT 1
    // INAV STATUS
    else if (mspRequestSlot == 1) {
        sendMspRequest(MSP2_INAV_STATUS_COMMAND);
    }

    // SLOT 2
    // GPS status
    else if (mspRequestSlot == 2) {
        sendMspRequest(MSP_COMP_GPS_COMMAND);
    }

    // SLOT 3 - NAV STATUS again
    else if (mspRequestSlot == 3) {
        sendMspRequest(MSP_NAV_STATUS_COMMAND);
    }

    // SLOT 4 - RC verification
    else if (mspRequestSlot == 4) {
        if (primaryControlValid) {
            updateFcChannels();

            snapshotExpectedRcForCheck();

            sendMspRequest(MSP_RC_COMMAND);
        }
    }

    // SLOT 5 - Learn INAV's dynamic mode-bit order, then return to NAV STATUS.
    else if (mspRequestSlot == 5) {
        if (!fcBoxIdsValid) {
            sendMspRequest(MSP_BOXIDS_COMMAND);
        }
        else {
            sendMspRequest(MSP_NAV_STATUS_COMMAND);
        }
    }

    mspRequestSlot++;

    if (mspRequestSlot >= 6) {
        mspRequestSlot = 0;
    }
}

void updateFcStatusValidity() {
    // A different live sensor must not keep an old reading valid indefinitely.
    if (millis() - lastFcGpsTime > 2000) {
        fcGpsValid = false;
    }
    if (millis() - lastFcVarioTime > 2000) {
        fcVarioValid = false;
    }
    if (millis() - lastFcBatteryTime > 2000) {
        fcBatteryValid = false;
    }
    if (millis() - lastFcBaroTime > 2000) {
        fcBaroValid = false;
    }
    if (millis() - lastFcRpmTime > 2000) {
        fcRpmValid = false;
    }
    if (millis() - lastFcTemperatureTime > 2000) {
        fcTemperatureValid = false;
    }
    if (millis() - lastFcAttitudeTime > 2000) {
        fcAttitudeValid = false;
    }
    if (millis() - lastFcFailsafeTime > 2000) {
        fcFailsafeStatusValid = false;
    }
    // MSP2 INAV STATUS
    if (fcStatusValid && millis() - lastFcStatusTime >  FC_STATUS_TIMEOUT) {
        fcStatusValid = false;
        fcAltHoldActive = false;
        fcBoxIdsValid = false;
    }

    // MSP NAV STATUS
    if (fcNavStatusValid && millis() - lastFcNavStatusTime > FC_NAV_STATUS_TIMEOUT) {
        fcNavStatusValid = false;
    }

    // MSP RC check
    if (fcRcCheckValid && millis() - lastFcRcCheckTime > FC_RC_CHECK_TIMEOUT) {
        fcRcCheckValid = false;
    }

    // MSP COMP GPS
    if (fcHomeDataValid && millis() - lastFcHomeDataTime > FC_HOME_DATA_TIMEOUT) {
        fcHomeDataValid = false;
    }
}


void updateFcChannels() {
    for (uint8_t i = 0; i < 16; i++) {
        fcChannels[i] = CRSF_MIN;
    }

    // Main controls
    fcChannels[0] = clampCrsf(finalRoll);
    fcChannels[1] = clampCrsf(finalPitch);
    fcChannels[3] = clampCrsf(finalYaw);

    // CH5 - ARM / DISARM
    if (armSwitchCommand) {
        fcChannels[4] = CRSF_MAX;
    } else {
        fcChannels[4] = CRSF_MIN;
    }

    // CH6 - RTH    
    if (rthCommand) {
        fcChannels[5] = CRSF_MAX;
    } else {
        fcChannels[5] = CRSF_MIN;
    }

    // CH7 is reserved. No verified LAND actuator is enabled in this build.
    fcChannels[6] = CRSF_MIN;

    // CH8 - NAV ALTHOLD. INAV must have AUX 4 / CH8 assigned to NAV ALTHOLD.
    // Retain altitude hold while RTH is only requested, not yet confirmed.
    const bool rthConfirmed = rthCommand && fcNavStatusValid && fcRthActive;
    const bool altHoldRequested = armSwitchCommand && !rthConfirmed;
    fcChannels[7] = altHoldRequested ? CRSF_MAX : CRSF_MIN;

    // Armed feedback/controller loss latches FC failsafe in updatePrimaryControlValidity.
    // Never transmit a low-throttle substitution for an airborne controller failure.
    if (!armSwitchCommand || !fcStatusValid || !fcArmed) {
        fcChannels[2] = CRSF_MIN;
    }
    else if (rthConfirmed || (fcNavStatusValid && fcLandingActive)) {
        fcChannels[2] = CRSF_CENTER;
    }
    else if (fcAltHoldActive) {
        fcChannels[2] = clampCrsf(finalThrottle);
    }
    else {
        fcChannels[2] = CRSF_MIN;
    }
}


void packCrsfChannels(const uint16_t channels[16], uint8_t payload[22]) {
    memset(payload, 0, 22);

    uint32_t bitBuffer = 0;
    uint8_t bitsInBuffer = 0;
    uint8_t payloadIndex = 0;

    for (uint8_t channel = 0; channel < 16; channel++) {
        bitBuffer |= ((uint32_t)(channels[channel] & 0x07FF)) << bitsInBuffer;
        bitsInBuffer += 11;

        while (bitsInBuffer >= 8) {
            payload[payloadIndex] = bitBuffer & 0xFF;

            payloadIndex++;

            bitBuffer >>= 8;
            bitsInBuffer -= 8;
        }
    }
}

void buildFcCrsfFrame() {
    fcCrsfFrame[0] = 0xC8;

    // Type + payload + CRC
    fcCrsfFrame[1] = 24;

    // RC_CHANNELS_PACKED
    fcCrsfFrame[2] = 0x16;

    // Put the 22-byte packed channel data from byte 3
    packCrsfChannels(fcChannels, fcCrsfFrame + 3);

    // frame type + 22-byte payload
    fcCrsfFrame[25] = crsfCrc8(fcCrsfFrame + 2, 23);
}

void sendCrsfToFc() {
    updateFcChannels();
    buildFcCrsfFrame();

    FcSerial.write(fcCrsfFrame, sizeof(fcCrsfFrame));
}

void updatePrimaryControlValidity() {
    primaryControlValid = false;

    if (currentMode == MODE_KEYBOARD) {
        primaryControlValid = groundLinkValid && keyboardPacketValid;
    }

    else if (currentMode == MODE_GLOVE) {
        primaryControlValid = groundLinkValid && leftGloveValid && leftImuValid &&
            rightImuValid && gloveOrientationCalibrated && gloveFlexCalibrated &&
            gloveControlsReady;
    }

    else if (currentMode == MODE_ELRS) {
        primaryControlValid = elrsValid;
    }

    else {
        primaryControlValid = false;
    }
    if (!armSwitchCommand) {
        fcControlFault = false;
    } else if (!primaryControlValid || !fcTelemetryValid || !fcStatusValid ||
        (fcArmed && !fcAltHoldActive &&
            !(fcNavStatusValid && (fcRthActive || fcLandingActive)))) {
        // Do not resume an armed command automatically after a control/feedback outage.
        // The FC's configured failsafe owns the outcome; DROP is not RTH.
        fcControlFault = true;
    }
    primaryControlValid = primaryControlValid && !fcControlFault;
    if (primaryControlValid != previousPrimaryControlValid) {
        previousPrimaryControlValid = primaryControlValid;
    }
}

// Snapshot for Air --> Ground telemetry
struct TelemetrySnapshot {
    uint32_t timestampMs;

    // Control / link state
    uint8_t currentMode;

    bool primaryControlValid;
    bool groundLinkValid;

    bool keyboardPacketValid;
    bool leftGloveValid;
    bool leftImuValid;
    bool rightImuValid;
    bool gloveOrientationCalibrated;
    bool gloveFlexCalibrated;

    bool fcTelemetryValid;

    // Current commands
    bool armCommand;
    bool rthCommand;
    bool landCommand;

    // GPS - CRSF 0x02
    bool gpsValid;

    int32_t latitudeE7;
    int32_t longitudeE7;

    uint16_t groundSpeedDeciKph;
    uint16_t gpsCourseCentideg;

    int32_t gpsAltitudeM;

    uint8_t satelliteCount;

    // Vario - CRSF 0x07
    bool varioValid;

    int16_t verticalSpeedCms;

    // Battery - CRSF 0x08
    bool batteryValid;

    uint16_t batteryVoltageDeciV;
    uint16_t batteryCurrentDeciA;

    uint32_t mahUsed;

    uint8_t batteryPercent;

    // Barometer - CRSF 0x09
    bool baroValid;

    int32_t baroAltitudeDm;

    // RPM - CRSF 0x0C
    bool rpmValid;

    int32_t motorRpm[4];

    // Temperature - CRSF 0x0D
    bool temperatureValid;

    uint8_t escTemperatureCount;

    int16_t escTemperatureDeciC[4];

    // Attitude - CRSF 0x1E
    bool attitudeValid;

    int16_t pitchRad10000;
    int16_t rollRad10000;
    int16_t yawRad10000;

    // Failsafe - CRSF 0x21
    bool failsafeStatusValid;

    bool failsafeActive;

    // MSP2_INAV_STATUS
    bool statusValid;

    uint16_t cycleTimeUs;
    uint16_t i2cErrorCount;
    uint16_t sensorStatus;
    uint16_t systemLoadPercent;

    uint8_t configProfile;
    uint8_t batteryProfile;

    uint32_t armingFlags;

    uint32_t activeModeFlagsLow;
    uint32_t activeModeFlagsHigh;

    uint8_t mixerProfile;

    bool fcArmed;
    bool armStateMatchesCommand;

    // MSP_NAV_STATUS
    bool navStatusValid;

    uint8_t navMode;
    uint8_t navState;
    uint8_t navError;

    bool rthActive;
    bool landingActive;
    bool landed;

    // MSP_RC
    bool rcCheckValid;

    uint8_t rcAccuracyPercent;


    // -----------------------------
    // MSP_COMP_GPS
    // -----------------------------
    bool homeDataValid;

    uint16_t distanceToHomeM;
    int16_t directionToHomeDeg;
};

void captureTelemetrySnapshot(TelemetrySnapshot& snapshot) {

    snapshot.timestampMs = millis();

    // Control / link state
    snapshot.currentMode = currentMode;

    snapshot.primaryControlValid = primaryControlValid;

    snapshot.groundLinkValid = groundLinkValid;

    snapshot.keyboardPacketValid = keyboardPacketValid;

    snapshot.leftGloveValid = leftGloveValid;

    snapshot.leftImuValid = leftImuValid;

    snapshot.rightImuValid = rightImuValid;

    snapshot.gloveOrientationCalibrated = gloveOrientationCalibrated;
    snapshot.gloveFlexCalibrated = gloveFlexCalibrated;

    snapshot.fcTelemetryValid = fcTelemetryValid;

    // Commands
    snapshot.armCommand = armSwitchCommand;

    snapshot.rthCommand = rthCommand;

    snapshot.landCommand = landCommand;

    // GPS
    snapshot.gpsValid = fcGpsValid;

    snapshot.latitudeE7 = fcLatitudeE7;

    snapshot.longitudeE7 = fcLongitudeE7;

    snapshot.groundSpeedDeciKph = fcGroundSpeedDeciKph;

    snapshot.gpsCourseCentideg = fcGpsCourseCentideg;

    snapshot.gpsAltitudeM = fcGpsAltitudeM;

    snapshot.satelliteCount = fcSatelliteCount;

    // Vario
    snapshot.varioValid = fcVarioValid;

    snapshot.verticalSpeedCms = fcVerticalSpeedCms;

    // Battery
    snapshot.batteryValid = fcBatteryValid;

    snapshot.batteryVoltageDeciV = fcBatteryVoltageDeciV;

    snapshot.batteryCurrentDeciA = fcBatteryCurrentDeciA;

    snapshot.mahUsed = fcMahUsed;

    snapshot.batteryPercent = fcBatteryPercent;

    // Barometer
    snapshot.baroValid = fcBaroValid;

    snapshot.baroAltitudeDm = fcBaroAltitudeDm;

    // RPM
    snapshot.rpmValid = fcRpmValid;

    for (uint8_t i = 0; i < 4; i++) {
        snapshot.motorRpm[i] = fcMotorRpm[i];
    }

    // Temperature
    snapshot.temperatureValid = fcTemperatureValid;

    snapshot.escTemperatureCount = fcEscTemperatureCount;

    for (uint8_t i = 0; i < 4; i++) {
        snapshot.escTemperatureDeciC[i] = fcEscTemperatureDeciC[i];
    }

    // Attitude
    snapshot.attitudeValid = fcAttitudeValid;

    snapshot.pitchRad10000 = fcPitchRad10000;

    snapshot.rollRad10000 = fcRollRad10000;

    snapshot.yawRad10000 = fcYawRad10000;

    // Failsafe
    snapshot.failsafeStatusValid = fcFailsafeStatusValid;

    snapshot.failsafeActive = fcFailsafeActive;

    // MSP2_INAV_STATUS
    snapshot.statusValid = fcStatusValid;

    snapshot.cycleTimeUs = fcCycleTimeUs;

    snapshot.i2cErrorCount = fcI2cErrorCount;

    snapshot.sensorStatus = fcSensorStatus;

    snapshot.systemLoadPercent = fcSystemLoadPercent;

    snapshot.configProfile = fcConfigProfile;

    snapshot.batteryProfile = fcBatteryProfile;

    snapshot.armingFlags = fcArmingFlags;

    snapshot.activeModeFlagsLow = fcActiveModeFlagsLow;

    snapshot.activeModeFlagsHigh = fcActiveModeFlagsHigh;

    snapshot.mixerProfile = fcMixerProfile;

    snapshot.fcArmed = fcArmed;

    snapshot.armStateMatchesCommand = fcArmStateMatchesCommand;

    // MSP_NAV_STATUS
    snapshot.navStatusValid = fcNavStatusValid;

    snapshot.navMode = fcNavMode;

    snapshot.navState = fcNavState;

    snapshot.navError = fcNavError;

    snapshot.rthActive = fcRthActive;

    snapshot.landingActive = fcLandingActive;

    snapshot.landed = fcLanded;

    // MSP_RC
    snapshot.rcCheckValid = fcRcCheckValid;

    snapshot.rcAccuracyPercent = fcRcAccuracyPercent;

    // MSP_COMP_GPS
    snapshot.homeDataValid = fcHomeDataValid;

    snapshot.distanceToHomeM = fcDistanceToHomeM;

    snapshot.directionToHomeDeg = fcDirectionToHomeDeg;
}

uint16_t buildValidityFlags(const TelemetrySnapshot& snapshot) {
    uint16_t flags = 0;

    // Bit 0 - FC telemetry link
    if (snapshot.fcTelemetryValid) {
        flags |= (1U << 0);
    }

    // Bit 1 - GPS
    if (snapshot.gpsValid) {
        flags |= (1U << 1);
    }

    // Bit 2 - Vario
    if (snapshot.varioValid) {
        flags |= (1U << 2);
    }

    // Bit 3 - Battery
    if (snapshot.batteryValid) {
        flags |= (1U << 3);
    }

    // Bit 4 - Barometer
    if (snapshot.baroValid) {
        flags |= (1U << 4);
    }

    // Bit 5 - RPM
    if (snapshot.rpmValid) {
        flags |= (1U << 5);
    }

    // Bit 6 - Temperature
    if (snapshot.temperatureValid) {
        flags |= (1U << 6);
    }

    // Bit 7 - Attitude
    if (snapshot.attitudeValid) {
        flags |= (1U << 7);
    }

    // Bit 8 - Failsafe status
    if (snapshot.failsafeStatusValid) {
        flags |= (1U << 8);
    }

    // Bit 9 - MSP2_INAV_STATUS
    if (snapshot.statusValid) {
        flags |= (1U << 9);
    }

    // Bit 10 - MSP_NAV_STATUS
    if (snapshot.navStatusValid) {
        flags |= (1U << 10);
    }

    // Bit 11 - MSP_RC check
    if (snapshot.rcCheckValid) {
        flags |= (1U << 11);
    }

    // Bit 12 - Home distance / direction
    if (snapshot.homeDataValid) {
        flags |= (1U << 12);
    }

    // Bit 13 - Both gloves completed flex calibration
    if (snapshot.gloveFlexCalibrated) {
        flags |= (1U << 13);
    }
    return flags;
}

uint16_t buildStateFlags(const TelemetrySnapshot& snapshot) {
    uint16_t flags = 0;

    // Bit 0 - Primary control valid
    if (snapshot.primaryControlValid) {
        flags |= (1U << 0);
    }

    // Bit 1 - Ground link valid
    if (snapshot.groundLinkValid) {
        flags |= (1U << 1);
    }

    // Bit 2 - Keyboard packet valid
    if (snapshot.keyboardPacketValid) {
        flags |= (1U << 2);
    }

    // Bit 3 - Left glove valid
    if (snapshot.leftGloveValid) {
        flags |= (1U << 3);
    }

    // Bit 4 - Left IMU valid
    if (snapshot.leftImuValid) {
        flags |= (1U << 4);
    }

    // Bit 5 - Right IMU valid
    if (snapshot.rightImuValid) {
        flags |= (1U << 5);
    }

    // Bit 6 - Glove orientation calibrated
    if (snapshot.gloveOrientationCalibrated) {
        flags |= (1U << 6);
    }

    // Bit 7 - FC failsafe active
    if (snapshot.failsafeActive) {
        flags |= (1U << 7);
    }

    // Bit 8 - ARM commanded
    if (snapshot.armCommand) {
        flags |= (1U << 8);
    }

    // Bit 9 - RTH commanded
    if (snapshot.rthCommand) {
        flags |= (1U << 9);
    }

    // Bit 10 - LAND commanded
    if (snapshot.landCommand) {
        flags |= (1U << 10);
    }

    // Bit 11 - FC actually armed
    if (snapshot.fcArmed) {
        flags |= (1U << 11);
    }

    // Bit 12 - FC arm state matches our command
    if (snapshot.armStateMatchesCommand) {
        flags |= (1U << 12);
    }

    // Bit 13 - RTH actually active
    if (snapshot.rthActive) {
        flags |= (1U << 13);
    }

    // Bit 14 - Landing actually active
    if (snapshot.landingActive) {
        flags |= (1U << 14);
    }

    // Bit 15 - FC reports landed
    if (snapshot.landed) {
        flags |= (1U << 15);
    }
    return flags;
}

uint8_t buildAirTelemetryPacket(const TelemetrySnapshot& snapshot) {
    uint8_t index = 0;

    // HEADER
    writeUint8BE(airTelemetryPacket, index, 0xA5);

    writeUint8BE(airTelemetryPacket, index, 0x5A);

    writeUint8BE(airTelemetryPacket, index, AIR_TELEMETRY_VERSION);

    writeUint8BE(airTelemetryPacket, index, AIR_TELEMETRY_TYPE);

    writeUint16BE(airTelemetryPacket, index, AIR_TELEMETRY_PAYLOAD_LENGTH);

    // SEQUENCE
    writeUint16BE(airTelemetryPacket, index, airTelemetrySequence);

    // PAYLOAD
    // AIR TIMESTAMP
    writeUint32BE(airTelemetryPacket, index, snapshot.timestampMs);

    // CURRENT CONTROL MODE
    writeUint8BE(airTelemetryPacket, index, snapshot.currentMode);

    // VALIDITY FLAGS
    uint16_t validityFlags = buildValidityFlags(snapshot);

    writeUint16BE(airTelemetryPacket, index, validityFlags);

    // STATE FLAGS
    uint16_t stateFlags = buildStateFlags(snapshot);

    writeUint16BE(airTelemetryPacket, index, stateFlags);

    // GPS - CRSF 0x0
    writeInt32BE(airTelemetryPacket, index, snapshot.latitudeE7);

    writeInt32BE(airTelemetryPacket, index, snapshot.longitudeE7);

    writeUint16BE(airTelemetryPacket, index, snapshot.groundSpeedDeciKph);

    writeUint16BE(airTelemetryPacket, index, snapshot.gpsCourseCentideg);

    writeInt32BE(airTelemetryPacket, index, snapshot.gpsAltitudeM);

    writeUint8BE(airTelemetryPacket, index, snapshot.satelliteCount);

    // VARIO - CRSF 0x07
    writeInt16BE(airTelemetryPacket, index, snapshot.verticalSpeedCms);

    // BATTERY - CRSF 0x08
    writeUint16BE(airTelemetryPacket, index, snapshot.batteryVoltageDeciV);

    writeUint16BE(airTelemetryPacket, index, snapshot.batteryCurrentDeciA);

    writeUint32BE(airTelemetryPacket, index, snapshot.mahUsed);

    writeUint8BE(airTelemetryPacket, index, snapshot.batteryPercent);

    // BAROMETER - CRSF 0x09
    writeInt32BE(
        airTelemetryPacket,
        index,
        snapshot.baroAltitudeDm
    );

    // MOTOR RPM - CRSF 0x0C
    for (uint8_t i = 0; i < 4; i++) {
        writeInt32BE(airTelemetryPacket, index, snapshot.motorRpm[i]);
    }

    // ESC TEMPERATURE - CRSF 0x0D
    writeUint8BE(airTelemetryPacket, index, snapshot.escTemperatureCount);

    for (uint8_t i = 0; i < 4; i++) {
        writeInt16BE(airTelemetryPacket, index, snapshot.escTemperatureDeciC[i]);
    }

    // ATTITUDE - CRSF 0x1E
    writeInt16BE(airTelemetryPacket, index, snapshot.pitchRad10000);

    writeInt16BE(airTelemetryPacket, index, snapshot.rollRad10000);

    writeInt16BE(airTelemetryPacket, index, snapshot.yawRad10000);

    // MSP2_INAV_STATUS
    writeUint16BE(airTelemetryPacket, index, snapshot.cycleTimeUs);

    writeUint16BE(airTelemetryPacket, index, snapshot.i2cErrorCount);

    writeUint16BE(airTelemetryPacket, index, snapshot.sensorStatus);

    writeUint16BE(airTelemetryPacket, index, snapshot.systemLoadPercent);

    writeUint8BE(airTelemetryPacket, index, snapshot.configProfile);

    writeUint8BE(airTelemetryPacket, index, snapshot.batteryProfile);

    writeUint32BE(airTelemetryPacket, index, snapshot.armingFlags);

    writeUint32BE(airTelemetryPacket, index, snapshot.activeModeFlagsLow);

    writeUint32BE(airTelemetryPacket, index, snapshot.activeModeFlagsHigh);

    writeUint8BE(airTelemetryPacket, index, snapshot.mixerProfile);

    // MSP_NAV_STATUS
    writeUint8BE(airTelemetryPacket, index, snapshot.navMode);

    writeUint8BE(airTelemetryPacket, index, snapshot.navState);

    writeUint8BE(airTelemetryPacket, index, snapshot.navError);

    // MSP_RC
    writeUint8BE(airTelemetryPacket, index, snapshot.rcAccuracyPercent);

    // MSP_COMP_GPS
    writeUint16BE(airTelemetryPacket, index, snapshot.distanceToHomeM);
    writeInt16BE(airTelemetryPacket, index, snapshot.directionToHomeDeg);

    // CRC16
    uint16_t crc = crc16CcittFalse( airTelemetryPacket + 2, index - 2);

    writeUint16BE(airTelemetryPacket, index, crc);

    // ADVANCE SEQUENCE
    airTelemetrySequence++;
    return index;
}

void sendAirTelemetryToRight() {
    if (!espNowReady) {
        return;
    }

    TelemetrySnapshot snapshot;

    captureTelemetrySnapshot(snapshot);

    uint8_t packetLength = buildAirTelemetryPacket(snapshot);

    esp_now_send(rightMacAddress, airTelemetryPacket, packetLength);
}

BuzzerSource currentBuzzerSource = BUZZER_SOURCE_NONE;

bool buzzerIsOn = false;

// Buzzer and LED
void setBuzzer(bool buzzerOn, BuzzerSource source) {
    buzzerIsOn = buzzerOn;

    if (buzzerOn) {
        currentBuzzerSource = source;
        digitalWrite(BUZZER_PIN, HIGH);
    }

    else {
        currentBuzzerSource = BUZZER_SOURCE_NONE;
        digitalWrite(BUZZER_PIN, LOW);
    }
}

void checkArmDisarmChange() {
    if (!fcStatusValid) {
        return;
    }

    // First valid FC state.
    if (!previousFcArmedInitialized) {
        previousFcArmed = fcArmed;

        previousFcArmedInitialized = true;
        return;
    }

    // No change
    if (fcArmed == previousFcArmed) {
        return;
    }

    previousFcArmed = fcArmed;

    buzzerPatternStartTime = millis();

    if (fcArmed) {
        buzzerPattern = BUZZER_PATTERN_ARM;
    }

    else {
        buzzerPattern = BUZZER_PATTERN_DISARM;
    }
}

bool updateArmDisarmBuzzer() {
    if (buzzerPattern == BUZZER_PATTERN_NONE) {
        return false;
    }

    unsigned long elapsed = millis() - buzzerPatternStartTime;

    // ARM(4 quick beeps)
    if (buzzerPattern == BUZZER_PATTERN_ARM) {
        if (elapsed < 150) {
            setBuzzer(true, BUZZER_SOURCE_ARM);
        }

        else if (elapsed < 300) {
            setBuzzer(false, BUZZER_SOURCE_NONE);
        }

        else if (elapsed < 450) {
            setBuzzer(true, BUZZER_SOURCE_ARM);
        }

        else if (elapsed < 600) {
            setBuzzer(false, BUZZER_SOURCE_NONE);
        }

        else if (elapsed < 750) {
            setBuzzer(true, BUZZER_SOURCE_ARM);
        }

        else if (elapsed < 900) {
            setBuzzer(false, BUZZER_SOURCE_NONE);
        }

        else if (elapsed < 1050) {
            setBuzzer(true, BUZZER_SOURCE_ARM);
        }

        else {
            setBuzzer(false, BUZZER_SOURCE_NONE);

            buzzerPattern = BUZZER_PATTERN_NONE;
        }

        return true;
    }

    // DISARM(One longbeep)
    if (buzzerPattern == BUZZER_PATTERN_DISARM) {
        if (elapsed < 1500) {
            setBuzzer(true, BUZZER_SOURCE_DISARM);
        }

        else {
            setBuzzer(false, BUZZER_SOURCE_NONE);

            buzzerPattern = BUZZER_PATTERN_NONE;
        }
        return true;
    }

    return false;
}

bool updateManualBuzzer() {
    if (!manualBuzzerEnabled) {
        return false;
    }

    unsigned long phase = millis() % 1000;

    if (phase < 500) {
        setBuzzer(true, BUZZER_SOURCE_MANUAL);
        return true;
    }

    setBuzzer(false, BUZZER_SOURCE_NONE);

    return false;
}

bool landedBatteryBuzzerShouldRun() {
    if (!fcNavStatusValid) {
        return false;
    }

    if (!fcBatteryValid) {
        return false;
    }

    if (!fcLanded) {
        return false;
    }

    if (fcBatteryPercent < 30) {
        return false;
    }

    return true;
}

void updateLandedBuzzer() {
    if (!landedBatteryBuzzerShouldRun()) {
        setBuzzer(false, BUZZER_SOURCE_NONE);
        return;
    }

    unsigned long phase = millis() % 1000;

    if (phase < 500) {
        setBuzzer(true, BUZZER_SOURCE_LANDED);
    }

    else {
        setBuzzer(false, BUZZER_SOURCE_NONE);
    }
}

bool manualBuzzerCurrentlyBeeping = false;

void updateBuzzer() {
    checkArmDisarmChange();

    // Priority 1:
    // ARM / DISARM
    if (updateArmDisarmBuzzer()) {
        return;
    }

    // Priority 2:
    // Manual B
    if (manualBuzzerEnabled) {
        updateManualBuzzer();
        return;
    }

    // Priority 3:
    // Landed + >= 30%
    if (landedBatteryBuzzerShouldRun()) {
        updateLandedBuzzer();
        return;
    }

    // Nothing
    setBuzzer(false, BUZZER_SOURCE_NONE);
}

// Green cascade
void showArmCascade(unsigned long elapsed) {
    // 150 ms ON
    // 150 ms OFF
    unsigned long phase = elapsed % 300;

    // Silent half of cycle
    if (phase >= 150) {
        statusLed.clear();

        statusLed.show();

        return;
    }

    // LED 0 -> LED_COUNT - 1
    uint8_t activePixel = (phase * LED_COUNT) / 150;

    if (activePixel >= LED_COUNT) {
        activePixel = LED_COUNT - 1;
    }

    statusLed.clear();

    // Bright head
    statusLed.setPixelColor(activePixel, statusLed.Color(0, 255, 0));

    // Trail pixel
    if (activePixel >= 1) {
        statusLed.setPixelColor(activePixel - 1, statusLed.Color(0, 100, 0));
    }

    // Fainter trail
    if (activePixel >= 2) {
        statusLed.setPixelColor(activePixel - 2, statusLed.Color(0, 30, 0));
    }
    statusLed.show();
}

void showDisarmLed() {
    statusLed.fill(statusLed.Color(255, 0, 0));
    statusLed.show();
}

void showBlueLed() {
    statusLed.fill(statusLed.Color(0, 0, 255));
    statusLed.show();
}

void updateStatusLed() {
    static unsigned long lastLedUpdateTime = 0;

    unsigned long now = millis();

    if (now - lastLedUpdateTime < 10) {
        return;
    }

    lastLedUpdateTime = now;
    // ARM
    // Green outward cascade
    if (buzzerPattern == BUZZER_PATTERN_ARM) {
        unsigned long elapsed = millis() - buzzerPatternStartTime;

        showArmCascade(elapsed);

        return;
    }

    // DISARM
    // Red while beep is ON
    if (buzzerIsOn && currentBuzzerSource == BUZZER_SOURCE_DISARM) {
        showDisarmLed();
        return;
    }

    // MANUAL B
    // Blue synchronized with beep
    if (buzzerIsOn && currentBuzzerSource == BUZZER_SOURCE_MANUAL) {
        showBlueLed();
        return;
    }

    // LANDED
    // Same blue synchronized flash
    if (buzzerIsOn && currentBuzzerSource == BUZZER_SOURCE_LANDED) {
        showBlueLed();
        return;
    }

    // Nothing
    statusLed.clear();

    statusLed.show();
}

void setup() {
    // ESP NOW
    Serial.begin(115200);
    espNowReady = setupEspNow();

    // ELRS UART
    ElrsSerial.begin(420000, SERIAL_8N1, ELRS_RX_PIN, ELRS_TX_PIN);

    // STM32 UART
    FcSerial.begin(420000, SERIAL_8N1, FC_RX_PIN, FC_TX_PIN);

    // Buzzer and LED
    pinMode(BUZZER_PIN, OUTPUT);

    setBuzzer(false, BUZZER_SOURCE_NONE);

    statusLed.begin();

    statusLed.clear();

    statusLed.show();
}

void loop() {

    // Read ELRS data
    readElrs();

    // Read FC CRSF telemtry data
    readFcCrsf();

    // Update telemtry and MSP status validity
    updateFcStatusValidity();

    // Occasionally ask INAV for status and RC check
    updateMspRequests();

    bool haveGroundPacketToParse = false;

    portENTER_CRITICAL(&groundPacketMux);

    if (newGroundPacketAvailable) {

        memcpy(groundPacketBuffer, groundRxBuffer, 51);

        newGroundPacketAvailable = false;

        haveGroundPacketToParse = true;
    }

    portEXIT_CRITICAL(&groundPacketMux);

    if (haveGroundPacketToParse) {
        uint8_t index = 2;

        // Header
        uint8_t newGroundProtocolVersion = readUint8LE(groundPacketBuffer, index);
        uint8_t newGroundMessageType = readUint8LE(groundPacketBuffer, index);
        uint16_t newGroundPayloadLength = readUint16LE(groundPacketBuffer, index);
        uint16_t newGroundSequenceNumber = readUint16LE(groundPacketBuffer, index);

        // Payload
        uint32_t newGroundTimestampMs = readUint32LE(groundPacketBuffer, index);
        uint16_t newGroundControlMask = readUint16LE(groundPacketBuffer, index);

        // Left glove
        float newLeftQuatW = readFloat32LE(groundPacketBuffer, index);
        float newLeftQuatX = readFloat32LE(groundPacketBuffer, index);
        float newLeftQuatY = readFloat32LE(groundPacketBuffer, index);
        float newLeftQuatZ = readFloat32LE(groundPacketBuffer, index);

        uint8_t newLeftFlexFlags = readUint8LE(groundPacketBuffer, index);

        // Right glove
        float newRightQuatW = readFloat32LE(groundPacketBuffer, index);
        float newRightQuatX = readFloat32LE(groundPacketBuffer, index);
        float newRightQuatY = readFloat32LE(groundPacketBuffer, index);
        float newRightQuatZ = readFloat32LE(groundPacketBuffer, index);

        uint8_t newRightFlexFlags = readUint8LE(groundPacketBuffer, index);

        // Status
        uint8_t newStatusFlags = readUint8LE(groundPacketBuffer, index);

        // Sent CRC
        uint16_t newGroundReceivedCrc = readUint16LE(groundPacketBuffer, index);

        // Packet Validity
        uint16_t calculatedCrc = crc16CcittFalse(groundPacketBuffer + 2, 47);
        bool crcValid = calculatedCrc == newGroundReceivedCrc;
        bool syncValid = groundPacketBuffer[0] == 0xA5 && groundPacketBuffer[1] == 0x5A;
        bool headerValid = syncValid && newGroundProtocolVersion == 1 && newGroundMessageType == 0x41 && newGroundPayloadLength == 41;
  
        bool sequenceValid = true;

        if (headerValid && crcValid && haveLastGroundSequenceNumber) {
            uint16_t difference = newGroundSequenceNumber - lastGroundSequenceNumber;

            if (difference == 0) {
                sequenceValid = false;

            } else if (difference >= 0x8000) {
                sequenceValid = false;

            } else if (difference > 1) {
                groundSkippedPackets += difference - 1;
            }
        }
        if (headerValid && crcValid && sequenceValid) {

            groundProtocolVersion = newGroundProtocolVersion;

            groundMessageType = newGroundMessageType;

            groundPayloadLength = newGroundPayloadLength;

            groundSequenceNumber = newGroundSequenceNumber;

            lastGroundSequenceNumber = newGroundSequenceNumber;

            haveLastGroundSequenceNumber = true;

            groundTimestampMs = newGroundTimestampMs;

            groundReceivedCrc = newGroundReceivedCrc;

            groundControlMask = newGroundControlMask;

            // Left quaternion
            leftQuatW = newLeftQuatW;
            leftQuatX = newLeftQuatX;
            leftQuatY = newLeftQuatY;
            leftQuatZ = newLeftQuatZ;

            // Left flex
            leftThumbBent = (newLeftFlexFlags & (1U << 0)) != 0;
            leftIndexBent = (newLeftFlexFlags & (1U << 1)) != 0;
            /*
            leftRingBent =  
            LeftMiddleBent = 
            LeftPinkyBent=
            */
            leftImuValid = (newLeftFlexFlags & (1U << 7)) != 0;

            leftFist = leftThumbBent && leftIndexBent; // edit for rest fingers later on
            leftHandOpen = !leftThumbBent && !leftIndexBent; 


            // Right quaternion
            rightQuatW = newRightQuatW;
            rightQuatX = newRightQuatX;
            rightQuatY = newRightQuatY;
            rightQuatZ = newRightQuatZ;

            // Right flex
            rightThumbBent = (newRightFlexFlags & (1U << 0)) != 0;
            rightIndexBent = (newRightFlexFlags & (1U << 1)) != 0;
            /*
            RightRingBent =  
            RightMiddleBent = 
            RightPinkyBent =
            */
            rightImuValid = (newRightFlexFlags & (1U << 7)) != 0;

            rightFist = rightThumbBent && rightIndexBent; // Edit later on 
            rightHandOpen = !rightThumbBent && !rightIndexBent;

            // Status flags
            keyboardPacketValid = (newStatusFlags & (1U << 0)) != 0;

            leftGloveValid = (newStatusFlags & (1U << 1)) != 0;

            gloveFlexCalibrated = (newStatusFlags & (1U << 2)) != 0;

            groundLinkValid = true;

            lastGroundPacketTime = millis();

            // Commands
            rthRequest = (groundControlMask & (1U << 8)) != 0;
            landRequest = (groundControlMask & (1U << 9)) != 0;
            keyboardBuzzerState = (groundControlMask & (1U << 10)) != 0;

            // Mode requests
            keyboardModeRequest = (groundControlMask & (1U << 11)) != 0;
            gloveModeRequest = (groundControlMask & (1U << 12)) != 0;
            elrsModeRequest = (groundControlMask & (1U << 13)) != 0;

            uint8_t modeRequests = keyboardModeRequest + gloveModeRequest + elrsModeRequest;
            if (modeRequests == 3) {
                gloveCalibrationHeld = true;

                keyboardModeRequest = false;
                gloveModeRequest = false;
                elrsModeRequest = false;
            }

            else {
                gloveCalibrationHeld = false;
                if (modeRequests == 2) {
                    keyboardModeRequest = false;
                    gloveModeRequest = false;
                    elrsModeRequest = false;
                }
            }
            
            // ARM / DISARM
            armRequest = (groundControlMask & (1U << 14)) != 0;
            disarmRequest = (groundControlMask & (1U << 15)) != 0;

            groundPacketsSinceTelemetry++;

            if (groundPacketsSinceTelemetry >= 5) {
                groundPacketsSinceTelemetry = 0;
                telemetrySendScheduled = true;
                telemetrySendTargetUs = micros() + 4000;
            }
        }
    }

    if (groundLinkValid && millis() - lastGroundPacketTime >= 150) {
        groundLinkValid = false;

        haveLastGroundSequenceNumber = false;

        groundControlMask = 0;

        keyboardPacketValid = false;
        leftGloveValid = false;
        leftImuValid = false;
        rightImuValid = false;
        gloveFlexCalibrated = false;

        gloveCalibrationHeld = false;
        armRequest = disarmRequest = rthRequest = landRequest = false;

        keyboardModeRequest = false;
        gloveModeRequest = false;
        elrsModeRequest = false;
    }

    // Calibration
    updateGloveCalibration();

    if (gloveOrientationCalibrated && !gloveCalibrationInProgress && groundLinkValid && leftGloveValid && leftImuValid && rightImuValid) {
        updateGloveOrientation();
    }

    updateGloveControlReadiness();

    // Command detection
    if (armRequest && !previousArmRequest && !disarmRequest && !gloveCalibrationInProgress &&
        fcTelemetryValid && fcStatusValid && !fcArmed) {
        armSwitchCommand = true;
    }

    if (disarmRequest) {
        armSwitchCommand = false;
    }

    if (rthRequest && !previousRthRequest && !disarmRequest &&
        fcTelemetryValid && fcStatusValid && fcArmed && fcHomeDataValid) {
        rthCommand = true;
    }

    // Never let an unsupported LAND request change throttle or altitude hold.
    landCommand = false;

    previousArmRequest = armRequest;
    previousDisarmRequest = disarmRequest;
    previousRthRequest = rthRequest;
    previousLandRequest = landRequest;

    // Mode change detection

    requestedMode = MODE_NONE;
    const uint8_t modeRequestCount = keyboardModeRequest + gloveModeRequest + elrsModeRequest;

    if (modeRequestCount == 1 && keyboardModeRequest && !previousKeyboardModeRequest) {
        requestedMode = MODE_KEYBOARD;
    }

    if (modeRequestCount == 1 && gloveModeRequest && !previousGloveModeRequest) {
        requestedMode = MODE_GLOVE;
    }

    if (modeRequestCount == 1 && elrsModeRequest && !previousElrsModeRequest) {
        requestedMode = MODE_ELRS;
    }

    previousKeyboardModeRequest = keyboardModeRequest;
    previousGloveModeRequest = gloveModeRequest;
    previousElrsModeRequest = elrsModeRequest;

    if (groundLinkValid && keyboardPacketValid) {
        updateKeyboardControls();

    } else {
        keyboardRoll = CRSF_CENTER;
        keyboardPitch = CRSF_CENTER;
        keyboardYaw = CRSF_CENTER;
        keyboardThrottle = CRSF_CENTER;
    }

    // Process pending request 
    if (requestedMode != MODE_NONE) {
        if (requestedMode != currentMode) {
            // A gesture hold cannot continue across a different control mode.
            gloveArmStartTime = gloveDisarmStartTime = 0;
            gloveArmTriggered = gloveDisarmTriggered = false;
            gloveArmGestureAccepted = gloveDisarmGestureAccepted = false;
            gloveLandTriggered = gloveRthTriggered = false;
            gloveBuzzerHoldStartTime = 0;
            gloveBuzzerHoldTriggered = false;
        }
        currentMode = requestedMode;
        requestedMode = MODE_NONE;
    }

    // Mode selection and control assignment
    // Keyboard mode
    if (currentMode == MODE_KEYBOARD) {

        manualBuzzerEnabled = keyboardBuzzerState;

        if (groundLinkValid && keyboardPacketValid) {
            finalRoll = keyboardRoll;
            finalPitch = keyboardPitch;
            finalYaw = keyboardYaw;
            finalThrottle = keyboardThrottle;
        }

        else {
            finalRoll = CRSF_CENTER;
            finalPitch = CRSF_CENTER;
            finalYaw = CRSF_CENTER;
            finalThrottle = CRSF_CENTER;
        }
    }
    
    // Glove mode
    else if (currentMode == MODE_GLOVE) {

        if (gloveControlsReady) {
            updateGloveGestureCommands();
            updateGloveMovementOutputs();

            bool gloveBuzzerGesture = leftThumbBent && !leftIndexBent && rightThumbBent && !rightIndexBent;

            if (gloveBuzzerGesture) {
                if (gloveBuzzerHoldStartTime == 0) {
                    gloveBuzzerHoldStartTime = millis();
                }

                if (!gloveBuzzerHoldTriggered &&
                    millis() - gloveBuzzerHoldStartTime >= 1000) {
                    gloveBuzzerHoldTriggered = true;
                    manualBuzzerEnabled = !manualBuzzerEnabled;
                }
            } else {
                gloveBuzzerHoldStartTime = 0;
                gloveBuzzerHoldTriggered = false;
            }

            finalRoll = gloveRoll;
            finalPitch = glovePitch;
            finalYaw = gloveYaw;
            finalThrottle = gloveThrottle;
        } else {
            finalRoll = CRSF_CENTER;
            finalPitch = CRSF_CENTER;
            finalYaw = CRSF_CENTER;
            finalThrottle = CRSF_CENTER;
        }
    }

    // ELRS mode
    else if (currentMode == MODE_ELRS) {

        if (elrsValid) {
            finalRoll = elrsRoll;
            finalPitch = elrsPitch;
            finalYaw = elrsYaw;
            finalThrottle = elrsThrottle;
        }

        else {
            finalRoll = CRSF_CENTER;
            finalPitch = CRSF_CENTER;
            finalYaw = CRSF_CENTER;
            finalThrottle = CRSF_CENTER;
        }
    }
    // Deliberate DISARM must remain possible when navigation feedback is unavailable.
    if (disarmRequest) {
        armSwitchCommand = false;
    }
    if (!armSwitchCommand) {
        rthCommand = false;
        landCommand = false;
    }
    updatePrimaryControlValidity();

    // Buzzer and LED
    updateBuzzer();
    updateStatusLed();

    if (millis() - lastFcSendTime >= FC_SEND_INTERVAL) {
        lastFcSendTime = millis();

        if (primaryControlValid || (!armSwitchCommand &&
            (disarmRequest || (currentMode == MODE_GLOVE && gloveDisarmGestureAccepted)))) {
            sendCrsfToFc();
        }
    }

    if (telemetrySendScheduled) {
        if ((int32_t)(micros() - telemetrySendTargetUs) >= 0) {
            telemetrySendScheduled = false;

            sendAirTelemetryToRight();
        }
    }
}
