'use strict';
const {execFileSync}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const SHA=process.argv[3] || 'd7d38935628805b90e3cc0295861bac4a7a0824f';
const ROOT='/Users/deniscivkunov/Projects/WMS/.worktrees/wms396-stage';
const OUTPUT=process.argv[2]; assert(OUTPUT?.startsWith('/'));
const listed=execFileSync('git',['ls-tree','-r','--name-only',SHA,'--','backend/app','backend/alembic'],{cwd:ROOT,encoding:'utf8'}).trim().split('\n').filter(x=>x.endsWith('.py'));
const expected=Object.fromEntries(listed.map(p=>[p.slice('backend/'.length),crypto.createHash('sha256').update(execFileSync('git',['show',`${SHA}:${p}`],{cwd:ROOT})).digest('hex')]));
const py=`import json,hashlib,pathlib,os
roots=[pathlib.Path('/app/app'),pathlib.Path('/app/alembic')]
print('VERIFY='+json.dumps({'deployment':os.environ.get('RAILWAY_DEPLOYMENT_ID'),'files':{str(f.relative_to('/app')):hashlib.sha256(f.read_bytes()).hexdigest() for p in roots for f in p.rglob('*.py')}}))`;
const raw=execFileSync('railway',['ssh','--project','c28e681d-4535-4c96-ac97-c7b600a7f8e4','--environment','58a08b66-1290-45a2-8737-e3d7408389e5','--service','e4a67f11-4318-4386-b9f9-fe5ae0d4f5cc','--','python','-c',py],{cwd:ROOT,encoding:'utf8',timeout:45000,stdio:['ignore','pipe','pipe']});
const actual=JSON.parse(raw.split('\n').find(x=>x.startsWith('VERIFY=')).slice(7));
const missing=Object.keys(expected).filter(p=>!(p in actual.files));
const differing=Object.keys(expected).filter(p=>p in actual.files&&actual.files[p]!==expected[p]);
const extra=Object.keys(actual.files).filter(p=>!(p in expected));
const result={sha:SHA,deployment:actual.deployment,expectedFiles:listed.length,actualFiles:Object.keys(actual.files).length,missing,differing,extra,checkedAt:new Date().toISOString()};
fs.mkdirSync(path.dirname(OUTPUT),{recursive:true});fs.writeFileSync(OUTPUT,JSON.stringify(result,null,2));console.log(JSON.stringify(result));assert.equal(missing.length+differing.length+extra.length,0);
