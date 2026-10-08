#!/usr/bin/env python3
"""Local CLI adapter: emit completed Chrome DOM, stop only this isolated group."""
import os,signal,subprocess,sys,tempfile,time
chrome='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
args=sys.argv[1:]
if '--dump-dom' not in args:
 os.execv(chrome,[chrome,*args])
with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
 p=subprocess.Popen([chrome,*args],stdout=output,stderr=errors,start_new_session=True)
 complete=False;raw=b''
 try:
  end=time.monotonic()+28
  while time.monotonic()<end:
   output.seek(0);raw=output.read()
   if b'</html>' in raw:
    complete=True;break
   if p.poll() is not None:break
   time.sleep(.05)
 finally:
  try:os.killpg(p.pid,signal.SIGKILL)
  except ProcessLookupError:pass
  p.wait()
 sys.stdout.buffer.write(raw)
 if not complete:
  errors.seek(0);sys.stderr.buffer.write(errors.read());sys.exit(1)
