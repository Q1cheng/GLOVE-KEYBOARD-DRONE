from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


def function(source, signature):
    start = source.index(signature + " {")
    opening = source.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


@unittest.skipUnless(shutil.which("clang++"), "clang++ is required for firmware host tests")
class FirmwareAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT / "ESP32_AIR" / "ESP32_AIR.ino").read_text()
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        path = Path(cls.directory.name)
        flags = ("fcGpsValid", "fcVarioValid", "fcBatteryValid", "fcBaroValid",
                 "fcRpmValid", "fcTemperatureValid", "fcAttitudeValid", "fcFailsafeStatusValid")
        parsers = ("parseCrsfGps", "parseCrsfVario", "parseCrsfBattery", "parseCrsfBaro",
                   "parseCrsfRpm", "parseCrsfTemperature", "parseCrsfAttitude",
                   "parseCrsfFlightMode", "handleMspResponse")
        fixture = """
#include <cstdint>
#include <cassert>
#include <cstring>
uint32_t now = 0;
uint32_t millis() { return now; }
constexpr uint16_t CRSF_MIN = 172, CRSF_MAX = 1811;
constexpr uint32_t FC_TELEMETRY_TIMEOUT = 500;
uint32_t lastFcTelemetryTime = 0;
bool fcTelemetryValid = true;
uint8_t fcRxBuffer[64] = {}, fcRxIndex = 0;
struct { int available() { return 0; } uint8_t read() { return 0; } } FcSerial;
uint8_t crsfCrc8(const uint8_t*, uint8_t) { return 0; }
"""
        fixture += "\n".join(f"bool {flag} = true;" for flag in flags)
        fixture += "\n".join(f"void {parser}(const uint8_t*, uint8_t) {{}}" for parser in parsers)
        for signature in ("uint16_t clampCrsf(uint16_t value)",
                          "uint16_t crsfToPwm(uint16_t crsfValue)", "void readFcCrsf()"):
            fixture += "\n" + function(source, signature)
        fixture += """
int main(int argc, char** argv) {
    if (strcmp(argv[1], "pwm") == 0) {
        assert(crsfToPwm(0) == 988);
        assert(crsfToPwm(171) == 988);
        assert(crsfToPwm(172) == 988);
        assert(crsfToPwm(992) == 1500);
        assert(crsfToPwm(1811) == 2012);
        assert(crsfToPwm(65535) == 2012);
        for (uint16_t value = 172; value <= 1811; ++value)
            assert(crsfToPwm(value) == 988 + uint32_t(value - 172) * 1024 / 1639);
        return 0;
    }
    now = 500;
    readFcCrsf();
    assert(fcTelemetryValid);
"""
        fixture += "\n".join(f"assert({flag});" for flag in flags)
        fixture += "\nnow = 501; readFcCrsf(); assert(!fcTelemetryValid);\n"
        fixture += "\n".join(f"assert(!{flag});" for flag in flags)
        fixture += "\nfcTelemetryValid = true; lastFcTelemetryTime = now; readFcCrsf();\n"
        fixture += "\n".join(f"assert(!{flag});" for flag in flags)
        fixture += "\nreturn 0; }\n"
        (path / "audit.cpp").write_text(fixture)
        cls.binary = path / "audit"
        subprocess.run(["clang++", "-std=c++17", str(path / "audit.cpp"),
                        "-o", str(cls.binary)], check=True, capture_output=True, text=True)

    def run_case(self, case):
        result = subprocess.run([str(self.binary), case], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rc_conversion_clamps_and_preserves_in_range_values(self):
        self.run_case("pwm")

    def test_fc_timeout_invalidates_sensor_flags_until_new_sensor_readings(self):
        self.run_case("expiry")


@unittest.skipUnless(shutil.which("clang++"), "clang++ is required for firmware host tests")
class EspNowPeerTests(unittest.TestCase):
    def test_only_configured_peer_can_publish_received_packets(self):
        cases = (
            ("ESP32_AIR", "void onGroundPacketReceived(const esp_now_recv_info_t *info, const uint8_t *data, int length)",
             "rightMacAddress", "groundRxBuffer", "newGroundPacketAvailable", "groundPacketMux", 51),
            ("ESP32_RIGHT", "void onAirPacketReceived(const esp_now_recv_info_t* info, const uint8_t* data, int length)",
             "airMacAddress", "airTelemetryRxBuffer", "newAirTelemetryPacketAvailable", "airTelemetryMux", 113),
        )
        for directory, signature, peer, buffer, ready, mux, size in cases:
            with self.subTest(firmware=directory), tempfile.TemporaryDirectory() as temporary:
                source = (ROOT / directory / (directory + ".ino")).read_text()
                callback = signature.split("(")[0].split()[-1]
                fixture = f"""
#include <cstdint>
#include <cstring>
#include <cassert>
struct esp_now_recv_info_t {{ uint8_t* src_addr; }};
constexpr int AIR_TELEMETRY_PACKET_LENGTH = 113;
uint8_t {peer}[6] = {{1, 2, 3, 4, 5, 6}};
uint8_t {buffer}[{size}] = {{}};
bool {ready} = false;
int {mux} = 0;
void portENTER_CRITICAL(int*) {{}}
void portEXIT_CRITICAL(int*) {{}}
{function(source, signature)}
int main() {{
    uint8_t bytes[{size}]; memset(bytes, 42, sizeof(bytes));
    uint8_t wrong[6] = {{6, 5, 4, 3, 2, 1}};
    esp_now_recv_info_t stranger{{wrong}}, expected{{{peer}}};
    {callback}(&stranger, bytes, {size});
    assert(!{ready} && {buffer}[0] == 0);
    {callback}(nullptr, bytes, {size});
    assert(!{ready});
    {callback}(&expected, bytes, {size} - 1);
    assert(!{ready});
    {callback}(&expected, bytes, {size});
    assert({ready} && memcmp({buffer}, bytes, {size}) == 0);
}}
"""
                path = Path(temporary)
                (path / "peer.cpp").write_text(fixture)
                subprocess.run(["clang++", "-std=c++17", str(path / "peer.cpp"),
                                "-o", str(path / "peer")], check=True, capture_output=True, text=True)
                result = subprocess.run([str(path / "peer")], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
