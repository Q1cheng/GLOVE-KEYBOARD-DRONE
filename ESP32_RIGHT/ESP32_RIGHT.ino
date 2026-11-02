#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

//KEYBOARD MODE

// Packet
uint8_t packetBuffer[16];
uint8_t packetIndex = 0;
uint32_t skippedPackets = 0;

// Packet validity
bool keyboardPacketValid = false;
bool haveLastSequenceNumber = false;
uint16_t lastSequenceNumber = 0;
unsigned long lastValidPacketTime = 0;

// Packet fields
uint8_t protocolVersion = 0;
uint8_t messageType = 0;
uint16_t payloadLength = 0;
uint16_t sequenceNumber = 0;
uint32_t timestampMs = 0;
uint16_t keyMask = 0;
uint16_t newKeyMask = 0;
uint16_t receivedCrc = 0;
uint16_t groundControlMask = 0;

// Mode triggers
bool keyboardModeTriggered = false;
bool gloveModeTriggered = false;
bool elrsModeTriggered = false; 

// Hold timers
unsigned long armStartTime = 0;
unsigned long disarmStartTime = 0;
unsigned long landStartTime = 0;
unsigned long rthStartTime = 0;
unsigned long KeyboardModeHoldStartTime = 0;
unsigned long GloveModeHoldStartTime = 0;
unsigned long ElrsModeHoldStartTime = 0;
unsigned long BuzzerHoldStartTime = 0;

// Command triggers
bool armTriggered = false;
bool armBlockedUntilRelease = false;
bool disarmTriggered = false;
bool landTriggered = false;
bool rthTriggered = false;
bool buzzerHoldTriggered = false;

// Buzzer state
bool buzzerEnabled = false;

// GLOVE MODE
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BNO055.h>
#include <utility/imumaths.h>

// Flex pins
const uint8_t FLEX1_PIN = 4;
const uint8_t FLEX2_PIN = 5;

/*
const uint8_t FLEX3_PIN = 6;
const uint8_t FLEX4_PIN = 7;
const uint8_t FLEX5_PIN = 1;
*/

// Flex sensor values
uint16_t Flex1Raw = 0;
uint16_t Flex2Raw = 0;

/*
uint16_t Flex3Raw = 0;
uint16_t Flex4Raw = 0;
uint16_t Flex5Raw = 0;
*/

// Right flex sensor bent state
bool rightFlex1Bent = false;
bool rightFlex2Bent = false;

/*
bool rightFlex3Bent = false;
bool rightFlex4Bent = false;
bool rightFlex5Bent = false;
*/
uint16_t rightFlex1Threshold = 0; // TBD
uint16_t rightFlex2Threshold = 0;
uint16_t rightFlex1Hysteresis = 20;
uint16_t rightFlex2Hysteresis = 20;
bool rightFlex1ClosedIsLower = true;
bool rightFlex2ClosedIsLower = true;

/*
uint16_t rightFlex3Threshold = 0;
uint16_t rightFlex4Threshold = 0;
uint16_t rightFlex5Threshold = 0;
*/

// Right IMU
const uint8_t IMU_SDA = 8;
const uint8_t IMU_SCL = 9;

float rightQuatW = 1.0f;
float rightQuatX = 0.0f;
float rightQuatY = 0.0f;
float rightQuatZ = 0.0f;

bool rightImuValid = false;

Adafruit_BNO055 rightImu = Adafruit_BNO055(1, 0x28, &Wire);

// Left glove
HardwareSerial LeftGloveSerial(1);

// Left glove UART
const uint8_t LEFT_UART_TX_PIN = 17;
const uint8_t LEFT_UART_RX_PIN = 18;

// Left glove packet
const uint8_t LEFT_PACKET_SIZE = 32;
const uint16_t LEFT_PAYLOAD_LENGTH = 22;
uint8_t leftPacketBuffer[LEFT_PACKET_SIZE];
uint8_t leftPacketIndex = 0;

uint8_t leftProtocolVersion = 0;
uint8_t leftMessageType = 0;
uint16_t leftPayloadLength = 0;
uint16_t leftSequenceNumber = 0;
uint16_t lastLeftSequenceNumber = 0;
uint32_t leftTimestampMs = 0;

float leftQuatW = 1.0f;
float leftQuatX = 0.0f;
float leftQuatY = 0.0f;
float leftQuatZ = 0.0f;

bool leftImuValid = false;

uint8_t leftFlexFlags = 0;
bool leftFlex1Bent = false;
bool leftFlex2Bent = false;

/*
bool leftFlex3Bent = false;
bool leftFlex4Bent = false;
bool leftFlex5Bent = false;
*/

uint16_t leftReceivedCrc = 0;

uint32_t leftSkippedPackets = 0;
bool haveLastLeftSequenceNumber = false;
bool leftGloveValid = false;

unsigned long lastLeftPacketTime = 0;
unsigned long lastSensorReadTime = 0;

bool gloveCalibrationHeld = false;

// Right keeps the shared 5 + 5 + 5 second schedule.
const uint8_t CALIBRATION_START = 0xC1;
const uint8_t CALIBRATION_OPEN = 0xC2;
const uint8_t CALIBRATION_CLOSED = 0xC3;
const uint16_t FLEX_MIN_ENDPOINT_DELTA = 20;
unsigned long calibrationStartTime = 0;
bool calibrationActive = false;
bool calibrationChordPreviouslyHeld = false;
bool openMarkerSent = false;
bool closedMarkerSent = false;
bool calibrationSuccessful = false;
bool rightOpenCaptured = false;
bool rightFlexCalibrationComplete = false;
bool leftOpenCaptured = false;
bool leftFlexCalibrationComplete = false;
bool leftCalibrationStarted = false;
bool leftStartAckInTime = false;
bool leftOpenAckInTime = false;
bool leftClosedAckInTime = false;
uint8_t calibrationRunId = 0;
uint8_t lastReportedLeftCalibrationRunId = 0;
bool calibrationStartPending = false;
unsigned long calibrationChordStartTime = 0;
bool calibrationChordRejected = false;
bool haveArmTelemetry = false;
bool reportedDisarmed = false;
uint16_t lastArmTelemetrySequence = 0;
unsigned long lastArmTelemetryTime = 0;
// Same freshness interval as Air's FC telemetry link timeout.
const unsigned long ARM_TELEMETRY_TIMEOUT = 500;
unsigned long lastStartCommandTime = 0;
unsigned long lastOpenCommandTime = 0;
unsigned long lastClosedCommandTime = 0;

uint16_t rightFlex1Open = 0;
uint16_t rightFlex2Open = 0;
uint16_t rightFlex1Closed = 0;
uint16_t rightFlex2Closed = 0;

// GROUND -> AIR PACKET
// ESP NOW
const uint8_t ESPNOW_CHANNEL = 6;

// espErrorFlags
bool espNowReady = false;
uint8_t espNowErrorFlags = 0;

const uint8_t ESPNOW_ERROR_CHANNEL = 1 << 0;
const uint8_t ESPNOW_ERROR_INIT = 1 << 1;
const uint8_t ESPNOW_ERROR_PEER = 1 << 2;

// Ground Packet
const uint8_t GROUND_PACKET_SIZE = 51;

uint8_t airMacAddress[6] = {0xDC, 0xB4, 0xD9, 0x13, 0x60, 0x88};

const uint8_t GROUND_PROTOCOL_VERSION = 1;
const uint8_t MESSAGE_GROUND_CONTROL = 0x41;
const uint16_t GROUND_PAYLOAD_LENGTH = 41;

uint8_t groundPacketBuffer[GROUND_PACKET_SIZE];

uint16_t groundSequenceNumber = 0;

unsigned long lastGroundSendTime = 0;

// Air -> Right telemetry packet
const uint8_t AIR_TELEMETRY_VERSION = 1;
const uint8_t AIR_TELEMETRY_TYPE = 0x51;

const uint16_t AIR_TELEMETRY_PAYLOAD_LENGTH = 103;
const uint8_t AIR_TELEMETRY_PACKET_LENGTH = 113;

// Raw recieved
uint8_t airTelemetryRxBuffer[AIR_TELEMETRY_PACKET_LENGTH];

// Memory copied telemetry packet
uint8_t airTelemetryPacketBuffer[AIR_TELEMETRY_PACKET_LENGTH];

volatile bool newAirTelemetryPacketAvailable = false;
bool haveTelemetryPacket = false;

portMUX_TYPE airTelemetryMux = portMUX_INITIALIZER_UNLOCKED;

// ESP NOW
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

    esp_now_register_recv_cb(onAirPacketReceived);

    esp_now_peer_info_t airPeer = {};

    memcpy(airPeer.peer_addr, airMacAddress, 6);

    airPeer.channel = ESPNOW_CHANNEL;
    airPeer.ifidx = WIFI_IF_STA;
    airPeer.encrypt = false;

    if (esp_now_add_peer(&airPeer) != ESP_OK) {
        espNowErrorFlags |= ESPNOW_ERROR_PEER;
        return false;
    }
    return true;
}

bool readRightQuaternion() {
    // Check the I2C transaction before using BNO055 quaternion registers.
    Wire.beginTransmission(0x28);
    Wire.write(0x20);
    if (Wire.endTransmission(false) != 0) {
        return false;
    }
    if (Wire.requestFrom((uint8_t)0x28, (uint8_t)8) != 8) {
        while (Wire.available()) {
            Wire.read();
        }
        return false;
    }
    float values[4];
    float normSquared = 0;
    for (uint8_t i = 0; i < 4; i++) {
        uint16_t raw = Wire.read();
        raw |= (uint16_t)Wire.read() << 8;
        values[i] = (int16_t)raw / 16384.0f;
        normSquared += values[i] * values[i];
    }
    if (normSquared < 0.8f || normSquared > 1.2f) {
        return false;
    }
    rightQuatW = values[0];
    rightQuatX = values[1];
    rightQuatY = values[2];
    rightQuatZ = values[3];
    return true;
}

void setup() {
    Serial.begin(115200);
    delay(1500);

    analogReadResolution(12);

    analogSetPinAttenuation(FLEX1_PIN, ADC_11db);
    analogSetPinAttenuation(FLEX2_PIN, ADC_11db);

    /*
    analogSetPinAttenuation(FLEX3_PIN, ADC_ATTEN_DB_11);
    analogSetPinAttenuation(FLEX4_PIN, ADC_ATTEN_DB_11);
    analogSetPinAttenuation(FLEX5_PIN, ADC_ATTEN_DB_11);
    */

    Wire.begin(IMU_SDA, IMU_SCL);
    Wire.setClock(100000);
    Wire.setTimeOut(10);
    delay(1000);

    rightImuValid = rightImu.begin();

    // Left glove serial
    LeftGloveSerial.begin(115200, SERIAL_8N1, LEFT_UART_RX_PIN, LEFT_UART_TX_PIN);

    // ESP NOW
    espNowReady = setupEspNow();
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


bool isFlexBent(uint16_t flexRaw, uint16_t threshold) {
    return flexRaw < threshold;
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

bool updateFlexBentState(
    uint16_t raw,
    uint16_t threshold,
    uint16_t hysteresis,
    bool closedIsLower,
    bool currentlyBent
) {
    if (closedIsLower) {
        if (!currentlyBent && raw + hysteresis < threshold) {
            return true;
        }
        if (currentlyBent && raw > threshold + hysteresis) {
            return false;
        }
    } else {
        if (!currentlyBent && raw > threshold + hysteresis) {
            return true;
        }
        if (currentlyBent && raw + hysteresis < threshold) {
            return false;
        }
    }
    return currentlyBent;
}

uint16_t readRightFlexSnapshot(uint8_t pin) {
    uint32_t sum = 0;
    for (uint8_t sample = 0; sample < 8; sample++) {
        sum += analogRead(pin);
    }
    return sum / 8;
}

bool calibrationArmStateSafe() {
    return haveArmTelemetry && reportedDisarmed &&
        millis() - lastArmTelemetryTime < ARM_TELEMETRY_TIMEOUT;
}

void startFlexCalibration() {
    if (!calibrationArmStateSafe()) {
        return;
    }
    calibrationStartTime = millis();
    calibrationRunId = lastReportedLeftCalibrationRunId + 1;
    calibrationActive = true;
    calibrationStartPending = false;
    openMarkerSent = false;
    closedMarkerSent = false;
    lastStartCommandTime = 0;
    lastOpenCommandTime = 0;
    lastClosedCommandTime = 0;
    leftCalibrationStarted = false;
    leftStartAckInTime = false;
    leftOpenAckInTime = false;
    leftClosedAckInTime = false;
    rightOpenCaptured = false;
    leftOpenCaptured = false;
    rightFlexCalibrationComplete = false;
    leftFlexCalibrationComplete = false;
    calibrationSuccessful = false;
    rightFlex1Bent = false;
    rightFlex2Bent = false;
}

void sendCalibrationCommand(uint8_t marker) {
    uint8_t command[6] = {0xA5, 0x5A, marker, calibrationRunId, 0, 0};
    uint16_t crc = crc16CcittFalse(command, 4);
    command[4] = crc & 0xFF;
    command[5] = crc >> 8;
    LeftGloveSerial.write(command, sizeof(command));
}

bool calculateRightFlexThresholds() {
    uint16_t delta1 = abs((int)rightFlex1Closed - (int)rightFlex1Open);
    uint16_t delta2 = abs((int)rightFlex2Closed - (int)rightFlex2Open);
    if (delta1 < FLEX_MIN_ENDPOINT_DELTA || delta2 < FLEX_MIN_ENDPOINT_DELTA) {
        return false;
    }
    rightFlex1Threshold = ((uint32_t)rightFlex1Open + rightFlex1Closed) / 2;
    rightFlex2Threshold = ((uint32_t)rightFlex2Open + rightFlex2Closed) / 2;
    rightFlex1Hysteresis = max((uint16_t)5, (uint16_t)(delta1 / 10));
    rightFlex2Hysteresis = max((uint16_t)5, (uint16_t)(delta2 / 10));
    rightFlex1ClosedIsLower = rightFlex1Closed < rightFlex1Open;
    rightFlex2ClosedIsLower = rightFlex2Closed < rightFlex2Open;
    return true;
}

void updateFlexCalibration() {
    if (!calibrationActive) {
        return;
    }

    if (!calibrationArmStateSafe() || !keyboardPacketValid ||
        !leftGloveValid || !leftImuValid || !rightImuValid) {
        calibrationActive = false;
        calibrationSuccessful = false;
        rightFlexCalibrationComplete = false;
        return;
    }

    unsigned long elapsed = millis() - calibrationStartTime;

    if (!leftCalibrationStarted && elapsed < 10000 &&
        (lastStartCommandTime == 0 || millis() - lastStartCommandTime >= 50)) {
        sendCalibrationCommand(CALIBRATION_START);
        lastStartCommandTime = millis();
    }

    if (elapsed >= 8000 && !openMarkerSent) {
        openMarkerSent = true;
        if (rightImuValid && leftGloveValid && leftImuValid) {
            rightImuValid = readRightQuaternion();
            if (!rightImuValid) {
                rightFlexCalibrationComplete = false;
                return;
            }
            rightFlex1Open = readRightFlexSnapshot(FLEX1_PIN);
            rightFlex2Open = readRightFlexSnapshot(FLEX2_PIN);
            rightOpenCaptured = true;
        }
    }

    if (elapsed >= 8000 && elapsed < 10000 && !leftOpenCaptured &&
        (lastOpenCommandTime == 0 || millis() - lastOpenCommandTime >= 50)) {
        sendCalibrationCommand(CALIBRATION_OPEN);
        lastOpenCommandTime = millis();
    }

    if (elapsed >= 13000 && !closedMarkerSent) {
        closedMarkerSent = true;
        rightFlex1Closed = readRightFlexSnapshot(FLEX1_PIN);
        rightFlex2Closed = readRightFlexSnapshot(FLEX2_PIN);
        rightFlexCalibrationComplete = rightOpenCaptured && calculateRightFlexThresholds();
    }

    if (elapsed >= 13000 && elapsed < 15500 && !leftFlexCalibrationComplete &&
        (lastClosedCommandTime == 0 || millis() - lastClosedCommandTime >= 50)) {
        sendCalibrationCommand(CALIBRATION_CLOSED);
        lastClosedCommandTime = millis();
    }

    if (elapsed >= 15500) {
        calibrationActive = false;
        calibrationSuccessful = rightFlexCalibrationComplete &&
            leftCalibrationStarted && leftOpenCaptured && leftFlexCalibrationComplete &&
            leftStartAckInTime && leftOpenAckInTime && leftClosedAckInTime &&
            leftGloveValid && leftImuValid && rightImuValid;
    }
}
// Air Packet
void buildGroundPacket() {
    uint8_t index = 0;

    // Sync
    writeUint8LE(groundPacketBuffer, index, 0xA5);
    writeUint8LE(groundPacketBuffer, index, 0x5A);

    // Header
    writeUint8LE(groundPacketBuffer, index, GROUND_PROTOCOL_VERSION);
    writeUint8LE(groundPacketBuffer, index, MESSAGE_GROUND_CONTROL);

    writeUint16LE(groundPacketBuffer, index, GROUND_PAYLOAD_LENGTH);
    writeUint16LE(groundPacketBuffer, index, groundSequenceNumber);

    // Timestamp
    writeUint32LE(groundPacketBuffer, index, millis());

    // Control mask
    writeUint16LE(groundPacketBuffer, index, groundControlMask);

    // LEFT quaternion
    writeFloat32LE(groundPacketBuffer, index, leftQuatW);
    writeFloat32LE(groundPacketBuffer, index, leftQuatX);
    writeFloat32LE(groundPacketBuffer, index, leftQuatY);
    writeFloat32LE(groundPacketBuffer, index, leftQuatZ);

    // LEFT flex flags
    writeUint8LE(groundPacketBuffer, index, leftFlexFlags);

    // RIGHT quaternion
    writeFloat32LE(groundPacketBuffer, index, rightQuatW);
    writeFloat32LE(groundPacketBuffer, index, rightQuatX);
    writeFloat32LE(groundPacketBuffer, index, rightQuatY);
    writeFloat32LE(groundPacketBuffer, index, rightQuatZ);

    // RIGHT flex flags
    uint8_t rightFlexFlags = 0;

    if (rightFlex1Bent) {
        rightFlexFlags |= (1U << 0);
    }

    if (rightFlex2Bent) {
        rightFlexFlags |= (1U << 1);
    }

    if (rightImuValid) {
        rightFlexFlags |= (1U << 7);
    }

    writeUint8LE(groundPacketBuffer, index, rightFlexFlags);

      // Status flags
    uint8_t statusFlags = 0;

    if (keyboardPacketValid) {
        statusFlags |= (1U << 0);
    }

    if (leftGloveValid) {
        statusFlags |= (1U << 1);
    }

    if (calibrationSuccessful && leftGloveValid && leftFlexCalibrationComplete) {
        statusFlags |= (1U << 2);
    }

    writeUint8LE(groundPacketBuffer, index, statusFlags);

    uint16_t crc = crc16CcittFalse(groundPacketBuffer + 2, index - 2);

    writeUint16LE(groundPacketBuffer, index, crc);
}

void onAirPacketReceived(const esp_now_recv_info_t* info, const uint8_t* data, int length) {
    if (length != AIR_TELEMETRY_PACKET_LENGTH || info == nullptr || memcmp(info->src_addr, airMacAddress, 6) != 0) {
        return;
    }

    portENTER_CRITICAL(&airTelemetryMux);

    memcpy(airTelemetryRxBuffer, data, AIR_TELEMETRY_PACKET_LENGTH);

    newAirTelemetryPacketAvailable = true;

    portEXIT_CRITICAL(&airTelemetryMux);
}

bool validateAirTelemetryPacket(const uint8_t* packet) {
    // Sync
    if (packet[0] != 0xA5 || packet[1] != 0x5A) {
        return false;
    }

    // Version
    if (packet[2] != AIR_TELEMETRY_VERSION) {
        return false;
    }

    // Message type
    if (packet[3] != AIR_TELEMETRY_TYPE) {
        return false;
    }

    // Payload length
    uint16_t payloadLength = ((uint16_t)packet[4] << 8) | packet[5];

    if (payloadLength != AIR_TELEMETRY_PAYLOAD_LENGTH) {
        return false;
    }

    // CRC over bytes 2-110
    uint16_t receivedCrc = ((uint16_t)packet[111] << 8) | packet[112];

    uint16_t calculatedCrc = crc16CcittFalse(packet + 2, 109);

    if (receivedCrc != calculatedCrc) {
        return false;
    }
    return true;
}

void handleAirTelemetry() {
    bool haveTelemetryPacket = false;

    portENTER_CRITICAL(&airTelemetryMux);

    if (newAirTelemetryPacketAvailable) {
        memcpy(airTelemetryPacketBuffer, airTelemetryRxBuffer, AIR_TELEMETRY_PACKET_LENGTH);

        newAirTelemetryPacketAvailable = false;

        haveTelemetryPacket = true;
    }

    portEXIT_CRITICAL(&airTelemetryMux);

    if (!haveTelemetryPacket) {
        return;
    }

    if (!validateAirTelemetryPacket(airTelemetryPacketBuffer)) {
        return;
    }

    uint16_t sequence = ((uint16_t)airTelemetryPacketBuffer[6] << 8) | airTelemetryPacketBuffer[7];
    uint16_t difference = sequence - lastArmTelemetrySequence;
    if (haveArmTelemetry && millis() - lastArmTelemetryTime >= ARM_TELEMETRY_TIMEOUT) {
        // Rebase after an Air restart; require a second advancing packet before calibration.
        reportedDisarmed = false;
        lastArmTelemetrySequence = sequence;
        lastArmTelemetryTime = millis();
    } else if (!haveArmTelemetry || (difference != 0 && difference < 0x8000)) {
        uint16_t validity = ((uint16_t)airTelemetryPacketBuffer[13] << 8) | airTelemetryPacketBuffer[14];
        uint16_t state = ((uint16_t)airTelemetryPacketBuffer[15] << 8) | airTelemetryPacketBuffer[16];
        reportedDisarmed = (validity & ((1U << 0) | (1U << 9))) == ((1U << 0) | (1U << 9)) &&
            !(state & ((1U << 11) | (1U << 8)));
        haveArmTelemetry = true;
        lastArmTelemetrySequence = sequence;
        lastArmTelemetryTime = millis();
    }
    Serial.write(airTelemetryPacketBuffer, AIR_TELEMETRY_PACKET_LENGTH);
}

void loop() {
    while (Serial.available() > 0) {
        uint8_t incomingByte = Serial.read();

        if (packetIndex == 0) {
            if (incomingByte == 0xA5) {
                packetBuffer[0] = incomingByte;
                packetIndex = 1;
            }
            continue;
        }

        if (packetIndex == 1) {
            if (incomingByte == 0x5A) {
                packetBuffer[1] = incomingByte;
                packetIndex = 2;
            } else if (incomingByte == 0xA5) {
                packetBuffer[0] = incomingByte;
                packetIndex = 1;
            } else {
                packetIndex = 0;
            }
            continue;
        }

        packetBuffer[packetIndex] = incomingByte;
        packetIndex++;

        if (packetIndex == 16) {

            uint8_t parseIndex = 2;

            protocolVersion = readUint8LE(packetBuffer, parseIndex);

            messageType = readUint8LE(packetBuffer, parseIndex);

            payloadLength = readUint16LE(packetBuffer, parseIndex);

            sequenceNumber = readUint16LE(packetBuffer, parseIndex);

            timestampMs = readUint32LE(packetBuffer, parseIndex);

            newKeyMask = readUint16LE(packetBuffer, parseIndex);

            receivedCrc = readUint16LE(packetBuffer, parseIndex);

            uint16_t calculatedCrc = crc16CcittFalse(packetBuffer + 2, 12);

            bool headerValid = protocolVersion == 1 && messageType == 0x21 && payloadLength == 6;

            bool crcValid = calculatedCrc == receivedCrc;

            bool sequenceValid = true;


            if (headerValid && crcValid && haveLastSequenceNumber) {
                uint16_t difference = sequenceNumber - lastSequenceNumber;

                if (difference == 0) {
                    sequenceValid = false;
                }
                else if (difference >= 0x8000) {
                    sequenceValid = false;
                }
                else if (difference > 1) {
                    skippedPackets += difference - 1;
                }
            }

            if (headerValid && crcValid && sequenceValid) {
                keyboardPacketValid = true;
                lastSequenceNumber = sequenceNumber;
                keyMask = newKeyMask;
                haveLastSequenceNumber = true;
                lastValidPacketTime = millis();

                // A conflicting ARM must be released, never queued behind DISARM.
                if (!(keyMask & (1U << 14))) {
                    armBlockedUntilRelease = false;
                } else if ((keyMask & (1U << 15)) || calibrationActive) {
                    armBlockedUntilRelease = true;
                }
                // ARM
                if ((keyMask & (1U << 14)) && !armBlockedUntilRelease) {
                    if (armStartTime == 0) {
                        armStartTime = millis();
                    }

                    if (!armTriggered && millis() - armStartTime >= 3000) {
                        armTriggered = true;
                    }
                } else {
                    armStartTime = 0;
                    armTriggered = false;
                }

                // DISARM
                if (keyMask & (1U << 15)) {
                    if (disarmStartTime == 0) {
                        disarmStartTime = millis();
                    }

                    if (!disarmTriggered && millis() - disarmStartTime >= 3000) {
                        disarmTriggered = true;
                    }
                } else {
                    disarmStartTime = 0;
                    disarmTriggered = false;
                }

                // LAND
                if (keyMask & (1U << 9)) {
                    if (landStartTime == 0) {
                        landStartTime = millis();
                    }

                    if (!landTriggered && millis() - landStartTime >= 3000) {
                        landTriggered = true;
                    }
                } else {
                    landStartTime = 0;
                    landTriggered = false;
                }

                // RTH
                if (keyMask & (1U << 8)) {
                    if (rthStartTime == 0) {
                        rthStartTime = millis();
                    }

                    if (!rthTriggered && millis() - rthStartTime >= 5000) {
                        rthTriggered = true;
                    }
                } else {
                    rthStartTime = 0;
                    rthTriggered = false;
                }

                // Buzzer
                if (keyMask & (1U << 10)) {
                    if (BuzzerHoldStartTime == 0) {
                        BuzzerHoldStartTime = millis();
                    }

                    if (!buzzerHoldTriggered && millis() - BuzzerHoldStartTime >= 1000) {
                        buzzerHoldTriggered = true;
                        buzzerEnabled = !buzzerEnabled;
                    }
                } else {
                    BuzzerHoldStartTime = 0;
                    buzzerHoldTriggered = false;
                }

                // Mode keys
                bool keyboardModeHeld = (keyMask & (1U << 11)) != 0;
                bool gloveModeHeld = (keyMask & (1U << 12)) != 0;
                bool elrsModeHeld = (keyMask & (1U << 13)) != 0;

                uint8_t modeKeysHeld = keyboardModeHeld + gloveModeHeld + elrsModeHeld;

                if (modeKeysHeld == 3) {

                    gloveCalibrationHeld = true;

                    KeyboardModeHoldStartTime = 0;
                    GloveModeHoldStartTime = 0;
                    ElrsModeHoldStartTime = 0;

                    keyboardModeTriggered = false;
                    gloveModeTriggered = false;
                    elrsModeTriggered = false;
                }

                else {
                    gloveCalibrationHeld = false;
                }

                if (!gloveCalibrationHeld) {
                    calibrationStartPending = false;
                    calibrationChordRejected = false;
                } else if (!calibrationChordPreviouslyHeld && !calibrationActive) {
                    calibrationChordStartTime = millis();
                    calibrationStartPending = true;
                }
                if (calibrationStartPending && (!calibrationArmStateSafe() ||
                    !leftGloveValid || !leftImuValid || !rightImuValid || (keyMask & (1U << 14)))) {
                    calibrationChordRejected = true;
                    calibrationStartPending = false;
                }
                if (calibrationStartPending && !calibrationChordRejected && !calibrationActive &&
                    millis() - calibrationChordStartTime >= 3000) {
                    startFlexCalibration();
                }
                calibrationChordPreviouslyHeld = gloveCalibrationHeld;

                if (modeKeysHeld == 1) {
                    // Keyboard mode
                    if (keyboardModeHeld) {
                        GloveModeHoldStartTime = 0;
                        gloveModeTriggered = false;
                        ElrsModeHoldStartTime = 0;
                        elrsModeTriggered = false;

                        if (KeyboardModeHoldStartTime == 0) {
                            KeyboardModeHoldStartTime = millis();
                        }

                        if (!keyboardModeTriggered && millis() - KeyboardModeHoldStartTime >= 3000) {
                            keyboardModeTriggered = true;
                        }
                    }

                    // Glove mode
                    else if (gloveModeHeld) {
                        KeyboardModeHoldStartTime = 0;
                        keyboardModeTriggered = false;
                        ElrsModeHoldStartTime = 0;
                        elrsModeTriggered = false;

                        if (GloveModeHoldStartTime == 0) {
                            GloveModeHoldStartTime = millis();
                        }

                        if (!gloveModeTriggered &&
                            millis() - GloveModeHoldStartTime >= 3000) {
                            gloveModeTriggered = true;
                        }
                    }

                    // ELRS mode
                    else if (elrsModeHeld) {
                        KeyboardModeHoldStartTime = 0;
                        keyboardModeTriggered = false;
                        GloveModeHoldStartTime = 0;
                        gloveModeTriggered = false;

                        if (ElrsModeHoldStartTime == 0) {
                            ElrsModeHoldStartTime = millis();
                        }

                        if (!elrsModeTriggered && millis() - ElrsModeHoldStartTime >= 3000) {
                            elrsModeTriggered = true;
                        }
                    }
                } 
                else if (modeKeysHeld != 3) {
                    KeyboardModeHoldStartTime = 0;
                    GloveModeHoldStartTime = 0;
                    ElrsModeHoldStartTime = 0;

                    keyboardModeTriggered = false;
                    gloveModeTriggered = false;
                    elrsModeTriggered = false;
                }  
            }
            packetIndex = 0; 
        }
    }

    while (LeftGloveSerial.available() > 0) {
        uint8_t incomingByte = LeftGloveSerial.read();

        if (leftPacketIndex == 0) {
            if (incomingByte == 0xA5) {
                leftPacketBuffer[0] = incomingByte;
                leftPacketIndex = 1;
            }
            continue;
        }

        if (leftPacketIndex == 1) {
            if (incomingByte == 0x5A) {
                leftPacketBuffer[1] = incomingByte;
                leftPacketIndex = 2;
            } else if (incomingByte == 0xA5) {
                leftPacketBuffer[0] = incomingByte;
                leftPacketIndex = 1;
            } else {
                leftPacketIndex = 0;
            }
            continue;
        }

        leftPacketBuffer[leftPacketIndex] = incomingByte;
        leftPacketIndex++;

        if (leftPacketIndex == LEFT_PACKET_SIZE) {
            uint8_t index = 2;

            // Header
            leftProtocolVersion = readUint8LE(leftPacketBuffer, index);

            leftMessageType = readUint8LE(leftPacketBuffer, index);

            leftPayloadLength = readUint16LE(leftPacketBuffer, index);

            leftSequenceNumber = readUint16LE(leftPacketBuffer, index);

            leftTimestampMs = readUint32LE(leftPacketBuffer, index);

            // Left Quaternion
            float newLeftQuatW = readFloat32LE(leftPacketBuffer, index);

            float newLeftQuatX = readFloat32LE(leftPacketBuffer, index);

            float newLeftQuatY = readFloat32LE(leftPacketBuffer, index);

            float newLeftQuatZ = readFloat32LE(leftPacketBuffer, index);

            uint8_t newLeftFlexFlags = readUint8LE(leftPacketBuffer, index);

            uint8_t newLeftCalibrationRunId = readUint8LE(leftPacketBuffer, index);

            leftReceivedCrc = readUint16LE(leftPacketBuffer, index);

            uint16_t leftCalculatedCrc = crc16CcittFalse(
                leftPacketBuffer + 2,
                LEFT_PACKET_SIZE - 4
            );

            bool leftHeaderValid = leftProtocolVersion == 1 &&
                leftMessageType == 0x31 &&
                leftPayloadLength == LEFT_PAYLOAD_LENGTH;

            bool leftCrcValid = leftCalculatedCrc == leftReceivedCrc;

            bool leftSequenceValid = true;

            if (leftHeaderValid && leftCrcValid && haveLastLeftSequenceNumber) {
                uint16_t difference = leftSequenceNumber - lastLeftSequenceNumber;

                if (difference == 0) {
                    leftSequenceValid = false;
                } else if (difference >= 0x8000) {
                    leftSequenceValid = false;
                } else if (difference > 1) {
                    leftSkippedPackets += difference - 1;
                }
            }

            if (leftHeaderValid && leftCrcValid && leftSequenceValid) {
                lastLeftSequenceNumber = leftSequenceNumber;
                lastLeftPacketTime = millis();
                haveLastLeftSequenceNumber = true;
                leftGloveValid = true;

                leftQuatW = newLeftQuatW;
                leftQuatX = newLeftQuatX;
                leftQuatY = newLeftQuatY;
                leftQuatZ = newLeftQuatZ;

                leftFlexFlags = newLeftFlexFlags;

                leftFlex1Bent = (leftFlexFlags & (1U << 0)) != 0;

                leftFlex2Bent = (leftFlexFlags & (1U << 1)) != 0;

                /*
                leftFlex3Bent = (leftFlexFlags & (1U << 2)) != 0;

                leftFlex4Bent = (leftFlexFlags & (1U << 3)) != 0;

                leftFlex5Bent = (leftFlexFlags & (1U << 4)) != 0;
                */

                leftImuValid = (leftFlexFlags & (1U << 7)) != 0;

                lastReportedLeftCalibrationRunId = newLeftCalibrationRunId;

                bool currentCalibrationRun = newLeftCalibrationRunId == calibrationRunId;
                leftCalibrationStarted = currentCalibrationRun &&
                    (newLeftFlexFlags & (1U << 4)) != 0;
                leftOpenCaptured = leftCalibrationStarted &&
                    (newLeftFlexFlags & (1U << 5)) != 0;
                leftFlexCalibrationComplete = leftOpenCaptured &&
                    (newLeftFlexFlags & (1U << 6)) != 0;
                if (calibrationActive) {
                    unsigned long elapsed = millis() - calibrationStartTime;
                    leftStartAckInTime |= leftCalibrationStarted && elapsed <= 5000;
                    leftOpenAckInTime |= leftOpenCaptured && elapsed >= 8000 && elapsed <= 9000;
                    leftClosedAckInTime |= leftFlexCalibrationComplete &&
                        elapsed >= 13000 && elapsed <= 14000;
                }
            }
            leftPacketIndex = 0;
        }
    }
    
    // Keyboard timeout
    if (keyboardPacketValid && millis() - lastValidPacketTime >= 150) {
        keyboardPacketValid = false;
        haveLastSequenceNumber = false;
        gloveCalibrationHeld = false;
        calibrationChordPreviouslyHeld = false;
        calibrationStartPending = false;
        keyMask = 0;

        armStartTime = 0;
        disarmStartTime = 0;
        landStartTime = 0;
        rthStartTime = 0;

        KeyboardModeHoldStartTime = 0;
        GloveModeHoldStartTime = 0;
        ElrsModeHoldStartTime = 0;
        BuzzerHoldStartTime = 0;

        armTriggered = false;
        disarmTriggered = false;
        landTriggered = false;
        rthTriggered = false;

        keyboardModeTriggered = false;
        gloveModeTriggered = false;
        elrsModeTriggered = false;

        buzzerHoldTriggered = false;
    }

    if (millis() - lastSensorReadTime >= 10) {
        lastSensorReadTime = millis();

        // flex sensors
        Flex1Raw = analogRead(FLEX1_PIN);
        Flex2Raw = analogRead(FLEX2_PIN);

        if (rightFlexCalibrationComplete) {
            rightFlex1Bent = updateFlexBentState(
                Flex1Raw,
                rightFlex1Threshold,
                rightFlex1Hysteresis,
                rightFlex1ClosedIsLower,
                rightFlex1Bent
            );
            rightFlex2Bent = updateFlexBentState(
                Flex2Raw,
                rightFlex2Threshold,
                rightFlex2Hysteresis,
                rightFlex2ClosedIsLower,
                rightFlex2Bent
            );
        } else {
            rightFlex1Bent = false;
            rightFlex2Bent = false;
        }

        if (rightImuValid) {
            rightImuValid = readRightQuaternion();
            if (!rightImuValid) {
                rightFlexCalibrationComplete = false;
                calibrationSuccessful = false;
            }
        }

    }

    // Left timeout
    if (haveLastLeftSequenceNumber && millis() - lastLeftPacketTime >= 150) {
        haveLastLeftSequenceNumber = false;
        leftGloveValid = false;
        leftImuValid = false;
        
        leftFlexFlags = 0;

        leftFlex1Bent = false;
        leftFlex2Bent = false;
        leftOpenCaptured = false;
        leftFlexCalibrationComplete = false;
        leftCalibrationStarted = false;

        /*
        leftFlex3Bent = false;
        leftFlex4Bent = false;
        leftFlex5Bent = false;
        */
    }

    updateFlexCalibration();

    // Air Keymask
    groundControlMask = 0;

    if (keyboardPacketValid) {
        // Movement
        groundControlMask = keyMask & 0x00FF;
        
        // Commands
        if (rthTriggered) {
            groundControlMask |= (1U << 8);
        }

        if (landTriggered) {
            groundControlMask |= (1U << 9);
        }

        if (buzzerEnabled) {
            groundControlMask |= (1U << 10);
        }

        if (keyboardModeTriggered) {
            groundControlMask |= (1U << 11);
        }

        if (gloveModeTriggered) {
            groundControlMask |= (1U << 12);
        }

        if (elrsModeTriggered) {
            groundControlMask |= (1U << 13);
        }

        if (armTriggered) {
            groundControlMask |= (1U << 14);
        }

        if (disarmTriggered) {
            groundControlMask |= (1U << 15);
        }
    }

    if (calibrationActive) {
        // Keep DISARM, LAND, RTH and buzzer available during an accepted run.
        groundControlMask &= (1U << 8) | (1U << 9) | (1U << 10) | (1U << 15);
        unsigned long elapsed = millis() - calibrationStartTime;
        if (elapsed >= 5000 && elapsed < 10000 && keyboardPacketValid) {
            groundControlMask |= (1U << 11) | (1U << 12) | (1U << 13);
        }
    }

    if (millis() - lastGroundSendTime >= 10) {
        lastGroundSendTime = millis();

        if (espNowReady) {
            buildGroundPacket();

            esp_err_t sendResult = esp_now_send(airMacAddress, groundPacketBuffer, GROUND_PACKET_SIZE);
        

            if (sendResult == ESP_OK) {
                groundSequenceNumber++;
            }
        }
    }
    
    // Handle Air -> Right telemetry
    handleAirTelemetry();
}
