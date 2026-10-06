from pathlib import Path
import subprocess,time,tempfile
folder=Path(__file__).resolve().parent
chrome='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
def render(name,kind):
 target=folder/(name+('.png' if kind=='png' else '.pdf'))
 with tempfile.TemporaryDirectory(prefix='wms656-render-') as profile:
  args=[chrome,'--headless=new','--disable-gpu','--no-first-run','--disable-background-networking','--disable-component-update','--disable-sync','--no-pdf-header-footer',f'--user-data-dir={profile}']
  args+= [f'--screenshot={target}','--window-size=580,400','--hide-scrollbars'] if kind=='png' else [f'--print-to-pdf={target}']
  p=subprocess.Popen(args+[(folder/(name+'.html')).as_uri()],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  try:
   until=time.time()+20
   while time.time()<until:
    if target.exists() and (kind=='png' or b'%%EOF' in target.read_bytes()[-32:]): break
    time.sleep(.1)
   else: raise RuntimeError('renderer deadline: '+name)
  finally:
   p.terminate()
   try:p.wait(timeout=2)
   except subprocess.TimeoutExpired:p.kill();p.wait()
if not (folder/'fixture.png').exists():render('fixture','png')
else:
 for name in ['58x40','60x80','60x40','70x120','58x39-driver']:
  render(name,'pdf')
  subprocess.run(['pdftoppm','-scale-to','1200','-png',str(folder/(name+'.pdf')),str(folder/name)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
