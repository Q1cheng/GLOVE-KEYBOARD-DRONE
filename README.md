# Custom Quadcopter Control System

Firmware and ground-station software for a custom 6-inch quadcopter controlled through a MacBook keyboard and wearable sensor gloves. The system uses three ESP32 microcontrollers to collect inputs, transmit control data, and interface with a custom STM32F405 flight controller running INAV 9.1.0.

## System Architecture

┌─────────────────────┐
│     LEFT GLOVE      │
│ ESP32 + IMU + Flex  │
└──────────┬──────────┘
           │ UART
           v
┌─────────────────────┐       ┌─────────────────────┐
│     RIGHT GLOVE     │<─────>│       MACBOOK       │
│ ESP32 + IMU + Flex  │  USB  │ Keyboard + Display  │
└──────────┬──────────┘       └─────────────────────┘
           │
           │ ESP-NOW (2.4 GHz)
           v
┌─────────────────────┐
│      AIR ESP32      │
│  Packet Processing  │
│    CRSF Encoding    │
└──────────┬──────────┘
           │ CRSF UART
           v
┌─────────────────────┐
│    CUSTOM ZSFC      │
│     STM32F405       │
│     INAV 9.1.0      │
└──────────┬──────────┘
           │
           v
┌─────────────────────┐
│     4-IN-1 ESC      │
│      4 Motors       │
└─────────────────────┘


## Operation

The left glove sends BNO055 IMU and flex-sensor readings to the right glove over UART. The right ESP32 combines sensor data with keyboard inputs received from the MacBook.

Control data is transmitted to the airborne ESP32 using ESP-NOW. The Air ESP32 validates incoming packets and converts commands into CRSF channel frames for the STM32 flight controller. INAV handles stabilization and motor control.

The system supports keyboard, gesture, and optional ELRS control modes. Communication includes CRC validation, sequence tracking, and link timeouts.

## Telemetry and Display

The MacBook application handles keyboard input and displays available system telemetry. The communication architecture supports bidirectional data transfer between the ground and airborne ESP32s.

A separate analog FPV system transmits camera footage through a 5.8 GHz VTX and RC905 receiver to the MacBook.

## Communication

| Connection            | Protocol               |
──────────────────────────────────────────────────
| Left → Right ESP32    | UART, 115200 baud      |
| MacBook ↔ Right ESP32 | USB Serial             |
| Right ↔ Air ESP32     | ESP-NOW, Channel 6     |
| Air ESP32 → STM32     | CRSF, 420000 baud      |
| STM32 → ESC           | Digital motor protocol |
| FPV Camera → Receiver | Analog 5.8 GHz         |

## Hardware

- Custom STM32F405VGT6 flight controller
- Three ESP32 S3DEVKITC1 microcontrollers
- Two BNO055 IMUs and flex sensors
- BMI270 gyroscope/accelerometer
- IST8310 magnetometer and Beitian BE-180i GPS
- Sequre AM32 A2 4-in-1 ESC
- Four A2208 1800KV brushless motors
- 4S LiPo battery
- DPS368XTSA1

## Safety

The firmware implements control-source validation and communication timeouts. Loss of valid control data is designed to trigger INAV's receiver failsafe. Hardware verification is required before flight.