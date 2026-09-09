"""WMS-401: existing QA bearer, GET only; no credentials or payloads in output."""
from pathlib import Path
import json
import re
import subprocess
import tempfile
import httpx

ROOT = Path('/Users/deniscivkunov/Projects/WMS')
MOBILE = ROOT / '.worktrees/wms397-mobile/android'
BASE = 'https://web-production-9e7c1.up.railway.app/api/'
SUPPLY = '4e38cabf-b129-4a28-85b0-3dd3631da6a4'
TENANT = '9c31f3f4-ce62-4c1f-891a-295b278f1e69'
JAVA = Path('/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home/bin')
cache = Path.home() / '.gradle/caches/modules-2/files-2.1'
jars = []
for group, artifact, version in [
    ('org.jetbrains.kotlin', 'kotlin-stdlib', '2.0.21'),
    ('org.jetbrains.kotlinx', 'kotlinx-serialization-core-jvm', '1.7.3'),
    ('org.jetbrains.kotlinx', 'kotlinx-serialization-json-jvm', '1.7.3'),
]:
    jars.extend(str(p) for p in (cache/group/artifact/version).rglob('*.jar'))
cp = ':'.join([str(MOBILE/'app/build/tmp/kotlin-classes/debug'), *jars])
source = '''
import java.nio.file.*;
import kotlinx.serialization.json.*;
import kotlinx.serialization.*;
public class Decode {
 public static void main(String[] args) throws Exception {
  Json json = JsonKt.Json(Json.Default, b -> {b.setIgnoreUnknownKeys(true); return kotlin.Unit.INSTANCE;});
  Class<?> cls=Class.forName("ru.wms.tsd.core.api.fbs."+args[0]);
  Object companion=cls.getField("Companion").get(null);
  KSerializer serializer=(KSerializer)companion.getClass().getMethod("serializer").invoke(companion);
  try {json.decodeFromString(serializer, Files.readString(Path.of(args[1]))); System.out.println("DECODE_OK");}
  catch(Exception e){System.out.println(e.getClass().getSimpleName()+": "+e.getMessage().split("JSON input:")[0]); System.exit(2);}
 }
}
'''
proof = {'base': BASE, 'source_sha': subprocess.check_output(['git','-C',str(MOBILE),'rev-parse','HEAD'],text=True).strip(), 'get_only': True, 'responses': []}
with tempfile.TemporaryDirectory(prefix='wms401-decode-') as scratch:
    path=Path(scratch)
    (path/'Decode.java').write_text(source)
    subprocess.run([str(JAVA/'javac'),'-cp',cp,str(path/'Decode.java')],check=True,capture_output=True)
    token=(ROOT/'.secrets/staging-token.txt').read_text().strip().removeprefix('Bearer ')
    with httpx.Client(base_url=BASE, headers={'Authorization': 'Bearer '+token}, timeout=35) as client:
        me=client.get('auth/me'); me.raise_for_status()
        assert me.json()['tenant_id']==TENANT
        proof['tenant_id']=me.json()['tenant_id']
        def check(route, model):
            response=client.get(route)
            entry={'path':route,'http_status':response.status_code,'bytes':len(response.content),'seconds':round(response.elapsed.total_seconds(),3)}
            if response.status_code==200:
                data=response.json()
                entry['items_count']=len(data.get('items',data.get('orders',[]))) if isinstance(data,dict) else len(data)
                if model:
                    (path/'payload.json').write_text(response.text)
                    run=subprocess.run([str(JAVA/'java'),'-cp',cp+':'+scratch,'Decode',model,str(path/'payload.json')],capture_output=True,text=True)
                    entry['decode']=run.stdout.strip()
                    entry['decode_exit']=run.returncode
            else: data=None
            proof['responses'].append(entry)
            return data
        check('operations/fbs-orders/worklist?marketplace=wb&limit=100','FbsOrderPage')
        check('operations/fbs-supplies/worklist?marketplace=wb&status_group=active&limit=100','FbsWorklistResponse')
        workspace=check(f'operations/fbs-supplies/{SUPPLY}/workspace','FbsWorkspace')
        check(f'operations/fbs-supplies/{SUPPLY}/pick-options',None)
        if workspace and workspace['supply'].get('packaging_task_id'):
            check('operations/packaging-tasks/'+workspace['supply']['packaging_task_id'],'PackagingTask')
        schema=client.get('openapi.json'); schema.raise_for_status()
        routes=schema.json()['paths']
        text=(MOBILE/'app/src/main/java/ru/wms/tsd/core/api/fbs/FbsApi.kt').read_text()
        proof['missing_routes']=[method+' '+route for method,route in re.findall(r'@(GET|POST|DELETE)\("([^\"]+)"\)',text) if not any(re.sub(r'\{[^}]+\}','{}',p)==re.sub(r'\{[^}]+\}','{}','/'+route) and method.lower() in spec for p,spec in routes.items())]
print(json.dumps(proof,indent=2))
