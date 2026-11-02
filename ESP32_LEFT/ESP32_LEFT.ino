#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BNO055.h>
#include <utility/imumaths.h>

// Only thumb and index are present in protocol version 1.
const uint8_t FLEX1_PIN = 4;
const uint8_t FLEX2_PIN = 5;

uint16_t Flex1Raw = 0;
uint16_t Flex2Raw = 0;
bool leftFlex1Bent = false;
bool leftFlex2Bent = false;

uint16_t leftFlex1Threshold = 0;
uint16_t leftFlex2Threshold = 0;
uint16_t leftFlex1Hysteresis = 20;
uint16_t leftFlex2Hysteresis = 20;
bool leftFlex1ClosedIsLower = true;
bool leftFlex2ClosedIsLower = true;
bool flexCalibrationComplete = false;

const uint16_t FLEX_MIN_ENDPOINT_DELTA = 20;
const uint8_t CALIBRATION_START = 0xC1;
const uint8_t CALIBRATION_OPEN = 0xC2;
const uint8_t CALIBRATION_CLOSED = 0xC3;
const uint8_t CALIBRATION_COMMAND_SIZE = 6;
uint8_t calibrationCommand[CALIBRATION_COMMAND_SIZE];
uint8_t calibrationCommandIndex = 0;
uint8_t calibrationRunId = 0;
bool calibrationStarted = false;
bool openCaptured = false;
bool closedCaptured = false;

uint16_t leftFlex1Open = 0;
uint16_t leftFlex2Open = 0;
uint16_t leftFlex1Closed = 0;
uint16_t leftFlex2Closed = 0;

const uint8_t IMU_SDA_PIN = 8;
const uint8_t IMU_SCL_PIN = 9;

float leftQuatW = 1.0f;
float leftQuatX = 0.0f;
float leftQuatY = 0.0f;
float leftQuatZ = 0.0f;

bool leftImuValid = false;
Adafruit_BNO055 leftImu = Adafruit_BNO055(2, 0x28, &Wire);

const uint8_t RIGHT_UART_TX_PIN = 17;
const uint8_t RIGHT_UART_RX_PIN = 18;
HardwareSerial RightGloveSerial(1);

const uint8_t PROTOCOL_VERSION = 1;
const uint8_t MESSAGE_LEFT_GLOVE = 0x31;
const uint8_t PACKET_SIZE = 32;
const uint16_t PAYLOAD_LENGTH = 22;
uint8_t packetBuffer[PACKET_SIZE];
uint16_t sequenceNumber = 0;

unsigned long lastSensorReadTime = 0;

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

void writeUint8LE(uint8_t* buffer, uint8_t& index, uint8_t value) {
    buffer[index++] = value;
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

uint16_t readFlexSnapshot(uint8_t pin) {
    uint32_t sum = 0;
    for (uint8_t sample = 0; sample < 8; sample++) {
        sum += analogRead(pin);
    }
    return sum / 8;
}

bool calculateFlexThresholds() {
    uint16_t delta1 = abs((int)leftFlex1Closed - (int)leftFlex1Open);
    uint16_t delta2 = abs((int)leftFlex2Closed - (int)leftFlex2Open);

    if (delta1 < FLEX_MIN_ENDPOINT_DELTA ||
        delta2 < FLEX_MIN_ENDPOINT_DELTA) {
        return false;
    }

    leftFlex1Threshold = ((uint32_t)leftFlex1Open + leftFlex1Closed) / 2;
    leftFlex2Threshold = ((uint32_t)leftFlex2Open + leftFlex2Closed) / 2;
    leftFlex1Hysteresis = max((uint16_t)5, (uint16_t)(delta1 / 10));
    leftFlex2Hysteresis = max((uint16_t)5, (uint16_t)(delta2 / 10));
    leftFlex1ClosedIsLower = leftFlex1Closed < leftFlex1Open;
    leftFlex2ClosedIsLower = leftFlex2Closed < leftFlex2Open;
    return true;
}

void applyCalibrationCommand(uint8_t marker, uint8_t runId) {
    if (marker == CALIBRATION_START) {
        if (!calibrationStarted || runId != calibrationRunId) {
            calibrationRunId = runId;
            calibrationStarted = true;
            openCaptured = false;
            closedCaptured = false;
            flexCalibrationComplete = false;
            leftFlex1Bent = false;
            leftFlex2Bent = false;
        }
    } else if (!calibrationStarted || runId != calibrationRunId) {
        return;
    } else if (marker == CALIBRATION_OPEN && !openCaptured && leftImuValid) {
        leftImuValid = readLeftQuaternion();
        if (!leftImuValid) {
            flexCalibrationComplete = false;
            return;
        }
        leftFlex1Open = readFlexSnapshot(FLEX1_PIN);
        leftFlex2Open = readFlexSnapshot(FLEX2_PIN);
        openCaptured = true;
    } else if (marker == CALIBRATION_CLOSED && openCaptured && !closedCaptured) {
        leftFlex1Closed = readFlexSnapshot(FLEX1_PIN);
        leftFlex2Closed = readFlexSnapshot(FLEX2_PIN);
        closedCaptured = true;
        flexCalibrationComplete = calculateFlexThresholds();
    }
}

void processCalibrationMarkers() {
    while (RightGloveSerial.available() > 0) {
        uint8_t byte = RightGloveSerial.read();
        if (calibrationCommandIndex == 0 && byte != 0xA5) {
            continue;
        }
        if (calibrationCommandIndex == 1 && byte != 0x5A) {
            calibrationCommandIndex = byte == 0xA5 ? 1 : 0;
            continue;
        }
        calibrationCommand[calibrationCommandIndex++] = byte;
        if (calibrationCommandIndex == CALIBRATION_COMMAND_SIZE) {
            uint16_t receivedCrc = calibrationCommand[4] |
                ((uint16_t)calibrationCommand[5] << 8);
            if (crc16CcittFalse(calibrationCommand, 4) == receivedCrc) {
                applyCalibrationCommand(calibrationCommand[2], calibrationCommand[3]);
            }
            calibrationCommandIndex = 0;
        }
    }
}

void buildLeftGlovePacket() {
    uint8_t index = 0;
    writeUint8LE(packetBuffer, index, 0xA5);
    writeUint8LE(packetBuffer, index, 0x5A);
    writeUint8LE(packetBuffer, index, PROTOCOL_VERSION);
    writeUint8LE(packetBuffer, index, MESSAGE_LEFT_GLOVE);
    writeUint16LE(packetBuffer, index, PAYLOAD_LENGTH);
    writeUint16LE(packetBuffer, index, sequenceNumber);
    writeUint32LE(packetBuffer, index, millis());
    writeFloat32LE(packetBuffer, index, leftQuatW);
    writeFloat32LE(packetBuffer, index, leftQuatX);
    writeFloat32LE(packetBuffer, index, leftQuatY);
    writeFloat32LE(packetBuffer, index, leftQuatZ);

    uint8_t flexFlags = 0;
    if (leftFlex1Bent) {
        flexFlags |= (1U << 0);
    }
    if (leftFlex2Bent) {
        flexFlags |= (1U << 1);
    }
    if (calibrationStarted) {
        flexFlags |= (1U << 4);
    }
    if (openCaptured) {
        flexFlags |= (1U << 5);
    }
    if (flexCalibrationComplete) {
        flexFlags |= (1U << 6);
    }
    if (leftImuValid) {
        flexFlags |= (1U << 7);
    }
    writeUint8LE(packetBuffer, index, flexFlags);
    writeUint8LE(packetBuffer, index, calibrationRunId);

    uint16_t crc = crc16CcittFalse(packetBuffer + 2, index - 2);
    writeUint16LE(packetBuffer, index, crc);
}

bool readLeftQuaternion() {
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
    leftQuatW = values[0];
    leftQuatX = values[1];
    leftQuatY = values[2];
    leftQuatZ = values[3];
    return true;
}

void setup() {
    analogReadResolution(12);
    analogSetPinAttenuation(FLEX1_PIN, ADC_11db);
    analogSetPinAttenuation(FLEX2_PIN, ADC_11db);
    Wire.begin(IMU_SDA_PIN, IMU_SCL_PIN);
    Wire.setClock(100000);
    Wire.setTimeOut(10);
    delay(1000);
    leftImuValid = leftImu.begin();
    RightGloveSerial.begin(115200, SERIAL_8N1, RIGHT_UART_RX_PIN, RIGHT_UART_TX_PIN);
}

void loop() {
    processCalibrationMarkers();

    if (millis() - lastSensorReadTime >= 10) {
        lastSensorReadTime = millis();
        Flex1Raw = analogRead(FLEX1_PIN);
        Flex2Raw = analogRead(FLEX2_PIN);

        if (flexCalibrationComplete) {
            leftFlex1Bent = updateFlexBentState(
                Flex1Raw,
                leftFlex1Threshold,
                leftFlex1Hysteresis,
                leftFlex1ClosedIsLower,
                leftFlex1Bent
            );
            leftFlex2Bent = updateFlexBentState(
                Flex2Raw,
                leftFlex2Threshold,
                leftFlex2Hysteresis,
                leftFlex2ClosedIsLower,
                leftFlex2Bent
            );
        } else {
            leftFlex1Bent = false;
            leftFlex2Bent = false;
        }

        if (leftImuValid) {
            leftImuValid = readLeftQuaternion();
            if (!leftImuValid) {
                flexCalibrationComplete = false;
            }
        }

        buildLeftGlovePacket();
        RightGloveSerial.write(packetBuffer, PACKET_SIZE);
        sequenceNumber++;
    }
}
