from pathlib import Path
import json,subprocess,re
from PIL import Image
import zxingcpp
folder=Path(__file__).resolve().parent
checks=[]
for name in ['58x40','60x80','60x40','70x120','58x39-driver']:
 info=subprocess.check_output(['pdfinfo',str(folder/(name+'.pdf'))],text=True)
 assert int(re.search(r'Pages:\s+(\d+)',info)[1])==3
 for page in range(1,4):
  image=Image.open(folder/f'{name}-{page}.png').convert('RGB')
  expected='WMS656-ORDER' if page==2 else '010460055555555521WMS656TEST'
  results=zxingcpp.read_barcodes(image)
  assert len(results)==1 and results[0].text==expected,(name,page,results)
  assert image.convert('L').getextrema()[0]<128
  checks.append(dict(paper=name,page=page,decoded=expected,nonblank=True))
(folder/'validation.json').write_text(json.dumps(dict(sourceSha='5e599076f2082bcf6dbdd0e29f0a0fb583e76735',acceptanceHead='a6d266917e8fc70de71005c796d46923f34cccf2',fixture='synthetic saved full label; not seller original',checks=checks),indent=2)+'\n')
print('15 pages: correct order, nonblank, DataMatrix and QR decoded')
