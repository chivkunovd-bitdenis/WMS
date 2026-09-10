"""Read a freshly generated emulator hierarchy; never reuse a failed dump."""
import subprocess
import xml.etree.ElementTree as ET

ADB = '/opt/homebrew/share/android-commandlinetools/platform-tools/adb'

def hierarchy():
    for _ in range(5):
        subprocess.run([ADB, '-s', 'emulator-5554', 'shell', 'rm', '-f', '/sdcard/wms363-ui.xml'], check=True)
        result = subprocess.run([ADB, '-s', 'emulator-5554', 'shell', 'uiautomator', 'dump', '/sdcard/wms363-ui.xml'], capture_output=True, text=True, check=True)
        if 'dumped to:' not in result.stdout:
            continue
        data = subprocess.check_output([ADB, '-s', 'emulator-5554', 'exec-out', 'cat', '/sdcard/wms363-ui.xml'])
        return ET.fromstring(data)
    raise RuntimeError('No fresh UI hierarchy after five attempts')

if __name__ == '__main__':
    for node in hierarchy().iter('node'):
        if node.get('password') == 'true':
            continue
        if node.get('text') or node.get('class') == 'android.widget.EditText':
            print(node.get('class'), node.get('text'), node.get('bounds'))
