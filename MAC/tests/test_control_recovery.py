"""Execute the actual firmware helpers without transmitting to hardware."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_firmware_audit import ROOT, function
from command_guide import COMMANDS


@unittest.skipUnless(shutil.which('clang++'), 'clang++ required')
class ControlRecoveryTests(unittest.TestCase):
    def compile_and_run(self, code):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.cpp').write_text(code)
            result = subprocess.run(['clang++', '-std=c++17', str(path / 'test.cpp'),
                                     '-o', str(path / 'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(path / 'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_actual_air_output_and_fault_recovery(self):
        source = (ROOT / 'ESP32_AIR/ESP32_AIR.ino').read_text()
        code = '''
#include <cstdint>
#include <cassert>
constexpr uint16_t CRSF_MIN=172, CRSF_CENTER=992, CRSF_MAX=1811;
constexpr int MODE_KEYBOARD=1, MODE_GLOVE=2, MODE_ELRS=3;
int currentMode=MODE_KEYBOARD;
bool primaryControlValid=false, previousPrimaryControlValid=false, fcControlFault=false;
bool groundLinkValid=true, keyboardPacketValid=true, leftGloveValid=true;
bool leftImuValid=true, rightImuValid=true, gloveOrientationCalibrated=true;
bool gloveFlexCalibrated=true, gloveControlsReady=true, elrsValid=false;
bool armSwitchCommand=false, rthCommand=false, landCommand=false;
bool fcTelemetryValid=true, fcStatusValid=true, fcArmed=false, fcNavStatusValid=true;
bool fcRthActive=false, fcLandingActive=false, fcAltHoldActive=false;
uint16_t finalRoll=992, finalPitch=992, finalYaw=992, finalThrottle=1100;
uint16_t fcChannels[16];
'''
        for signature in ('uint16_t clampCrsf(uint16_t value)',
                          'void updateFcChannels()', 'void updatePrimaryControlValidity()'):
            code += function(source, signature)
        code += '''
int main() {
 updatePrimaryControlValidity(); updateFcChannels();
 assert(primaryControlValid && fcChannels[2]==172 && fcChannels[4]==172);
 armSwitchCommand=true; fcArmed=true; fcAltHoldActive=true;
 updatePrimaryControlValidity(); updateFcChannels();
 assert(primaryControlValid && fcChannels[2]==1100 && fcChannels[7]==1811);
 rthCommand=true; updateFcChannels();
 assert(fcChannels[2]==1100 && fcChannels[7]==1811);
 fcRthActive=true; fcAltHoldActive=false;
 updatePrimaryControlValidity(); updateFcChannels();
 assert(primaryControlValid && fcChannels[2]==992 && fcChannels[7]==172);
 landCommand=true; updateFcChannels(); assert(fcChannels[6]==172);
 fcStatusValid=false; updatePrimaryControlValidity();
 assert(!primaryControlValid && fcControlFault);
 fcStatusValid=true; updatePrimaryControlValidity(); assert(!primaryControlValid);
 armSwitchCommand=false; updatePrimaryControlValidity(); updateFcChannels();
 assert(primaryControlValid && !fcControlFault && fcChannels[4]==172);
 currentMode=MODE_ELRS; elrsValid=true; updatePrimaryControlValidity();
 assert(primaryControlValid);
 elrsValid=false; updatePrimaryControlValidity(); assert(!primaryControlValid);
 currentMode=MODE_KEYBOARD; armSwitchCommand=true; groundLinkValid=false;
 updatePrimaryControlValidity(); assert(fcControlFault && !primaryControlValid);
 groundLinkValid=true; updatePrimaryControlValidity(); assert(!primaryControlValid);
 armSwitchCommand=false; updatePrimaryControlValidity();
 armSwitchCommand=true; fcRthActive=false; fcAltHoldActive=false;
 updatePrimaryControlValidity(); assert(fcControlFault && !primaryControlValid);
}
'''
        self.compile_and_run(code)

    def test_actual_right_arm_disarm_hold_times(self):
        source = (ROOT / 'ESP32_RIGHT/ESP32_RIGHT.ino').read_text()
        block = source[source.index('                // ARM\n'):source.index('                // LAND\n')]
        code = '''
#include <cstdint>
#include <cassert>
uint32_t now=100;
uint32_t millis() { return now; }
uint16_t keyMask=0;
bool armBlockedUntilRelease=false, armTriggered=false, disarmTriggered=false;
uint32_t armStartTime=0, disarmStartTime=0;
void update() {
''' + block + '''
}
int main() {
 keyMask=1U<<14; update(); now=3099; update(); assert(!armTriggered);
 now=3100; update(); assert(armTriggered);
 keyMask=0; update(); assert(!armTriggered && !armStartTime);
 keyMask=1U<<15; update(); now=6099; update(); assert(!disarmTriggered);
 now=6100; update(); assert(disarmTriggered);
 keyMask=0; update(); assert(!disarmTriggered && !disarmStartTime);
}
'''
        self.compile_and_run(code)
        self.assertEqual([c.seconds for c in COMMANDS if c.name in ('ARM', 'DISARM')], [3, 3])

    def test_air_rejects_conflicting_mode_requests(self):
        source = (ROOT / 'ESP32_AIR/ESP32_AIR.ino').read_text()
        block = source[source.index('    requestedMode = MODE_NONE;', source.index('// Mode change detection')):
                       source.index('    previousKeyboardModeRequest = keyboardModeRequest;')]
        self.compile_and_run('''
#include <cstdint>
#include <cassert>
constexpr int MODE_NONE=0, MODE_KEYBOARD=1, MODE_GLOVE=2, MODE_ELRS=3;
int requestedMode=0;
bool keyboardModeRequest=false, gloveModeRequest=false, elrsModeRequest=false;
bool previousKeyboardModeRequest=false, previousGloveModeRequest=false, previousElrsModeRequest=false;
void update() {
''' + block + '''
}
int main() {
 for (int mask=0; mask<8; mask++) {
  keyboardModeRequest=mask&1; gloveModeRequest=mask&2; elrsModeRequest=mask&4;
  update();
  assert(requestedMode == (mask==1 ? 1 : mask==2 ? 2 : mask==4 ? 3 : 0));
 }
}
''')

    def test_actual_quaternion_read_rejects_failed_and_partial_transactions(self):
        for side in ('left', 'right'):
            with self.subTest(side=side):
                folder = 'ESP32_' + side.upper()
                source = (ROOT / folder / (folder + '.ino')).read_text()
                code = '''
#include <cstdint>
#include <cassert>
struct Bus {
 uint8_t bytes[8]={0,64,0,0,0,0,0,0}; int index=0, count=8, error=0;
 void beginTransmission(int) {} void write(int) {}
 int endTransmission(bool) { return error; }
 int requestFrom(uint8_t, uint8_t) { index=0; return count; }
 int available() { return count-index; } int read() { return bytes[index++]; }
} Wire;
'''
                code += '\n'.join(f'float {side}Quat{axis}=0;' for axis in 'WXYZ')
                name = 'read' + side.capitalize() + 'Quaternion'
                code += function(source, 'bool ' + name + '()')
                code += f'''
int main() {{
 assert({name}() && {side}QuatW==1);
 Wire.error=1; assert(!{name}()); Wire.error=0;
 Wire.count=4; assert(!{name}()); Wire.count=8;
 Wire.bytes[1]=0; assert(!{name}());
 Wire.bytes[1]=127; assert(!{name}());
}}
'''
                self.compile_and_run(code)


if __name__ == '__main__':
    unittest.main()
