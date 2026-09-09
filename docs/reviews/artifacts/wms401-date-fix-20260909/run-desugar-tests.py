"""Run the actual targeted tests using the cached Android java.time implementation.
Only java/time classes are patched into the host JVM; this is not an AVD test.
"""
import os
import pathlib
import subprocess
import sys
import tempfile
import zipfile

root = pathlib.Path(__file__).resolve()
while not (root / ".worktrees/wms397-mobile/android/gradlew").is_file():
    root = root.parent
android = root / ".worktrees/wms397-mobile/android"
jar = next((pathlib.Path.home() / ".gradle/caches/modules-2/files-2.1/com.android.tools/desugar_jdk_libs/2.1.4").rglob("*.jar"))
env = dict(os.environ, JAVA_HOME="/opt/homebrew/opt/openjdk@17", ANDROID_HOME="/opt/homebrew/share/android-commandlinetools")
with tempfile.TemporaryDirectory(prefix="wms401-desugar-tests-") as temporary:
    patch = pathlib.Path(temporary) / "patch"
    with zipfile.ZipFile(jar) as archive:
        for name in archive.namelist():
            if name.startswith("java/time/") and name.endswith(".class"):
                target = patch / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
    probe = pathlib.Path(temporary) / "DateProbe.java"
    probe.write_text('''import java.time.*;
public class DateProbe {
    public static void main(String[] args) {
        for (String value : new String[]{"2026-09-09T10:43:24+00:00", "2026-09-09T10:43:24Z", "2026-09-09T13:43:24+03:00", "2026-09-09T10:43:24.123456+00:00"}) {
            try { System.out.println("Instant " + value + " => " + Instant.parse(value)); }
            catch (Exception failure) { System.out.println("Instant " + value + " => " + failure); }
            System.out.println("OffsetDateTime " + value + " => " + OffsetDateTime.parse(value).toInstant());
        }
    }
}
''')
    subprocess.run([env["JAVA_HOME"] + "/bin/javac", str(probe)], check=True)
    for runtime in ([], ["--patch-module", "java.base=" + str(patch)]):
        print("Runtime:", "desugar_jdk_libs 2.1.4 java.time" if runtime else "host JDK17", flush=True)
        subprocess.run([env["JAVA_HOME"] + "/bin/java", *runtime, "-cp", temporary, "DateProbe"], check=True)
    if "--probe-only" in sys.argv:
        sys.exit(0)
    init = pathlib.Path(temporary) / "test.init.gradle"
    init.write_text("allprojects { tasks.withType(Test).configureEach { jvmArgs '--patch-module', 'java.base=" + str(patch) + "'; outputs.upToDateWhen { false } } }\n")
    subprocess.run([str(android / "gradlew"), "-p", str(android), "--no-daemon", "--max-workers=2", "--init-script", str(init), ":app:testDebugUnitTest", "--tests", "ru.wms.tsd.features.fbs.FbsViewModelTest"], env=env, check=True)
