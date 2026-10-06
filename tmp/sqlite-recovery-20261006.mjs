// Narrow recovery: eight old generated test databases, archive before unlink.
import fs from 'node:fs';
import {execFileSync,spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
const owner='/Users/deniscivkunov/Projects/WMS/.claude/worktrees/agent-ac6c35b1b853f4ccb';
const out='/Users/deniscivkunov/Projects/WMS/.worktrees/night-ready-acceptance-1006/tmp';
const rels=Array.from({length:8},(_,i)=>'backend/tests/wms_pytest_gw'+i+'.sqlite');
const archive=out+'/sqlite-recovery-20261006-old8.tar.gz';
const manifest=out+'/sqlite-recovery-20261006-old8.json';
const hash=b=>createHash('sha256').update(b).digest('hex');
if(fs.existsSync(archive)||fs.existsSync(manifest))throw new Error('Refuse overwrite existing recovery');
const cwd=execFileSync('lsof',['-nP','-d','cwd','-Fn'],{encoding:'utf8',maxBuffer:4*1024*1024});
if(cwd.includes(owner))throw new Error('Old worktree has active cwd');
const handles=()=>{const r=spawnSync('lsof',['-nP','-t',...rels.map(r=>owner+'/'+r)],{encoding:'utf8'});if(r.status!==1||r.stdout.trim())throw new Error('Open handle or lsof failure');};
handles();
const now=Date.now();
const entries=rels.map(rel=>{
  const path=owner+'/'+rel,s=fs.lstatSync(path);
  if(!s.isFile()||s.isSymbolicLink()||now-s.mtimeMs<7*86400000)throw new Error('Not old regular generated file');
  const tracked=spawnSync('git',['ls-files','--error-unmatch','--',rel],{cwd:owner,encoding:'utf8'});
  if(tracked.status!==1)throw new Error('Tracked file or Git failure');
  for(const suffix of ['-wal','-shm','-journal'])if(fs.existsSync(path+suffix))throw new Error('SQLite companion present');
  const bytes=fs.readFileSync(path);
  if(bytes.subarray(0,16).toString()!=='SQLite format 3\0')throw new Error('Not SQLite');
  return {path,member:rel,size:s.size,allocatedBytes:s.blocks*512,mtime:new Date(s.mtimeMs).toISOString(),sha256:hash(bytes),device:s.dev,inode:s.ino,mtimeMs:s.mtimeMs};
});
const before=execFileSync('df',['-k',out],{encoding:'utf8'});
execFileSync('tar',['-czf',archive,'-C',owner,...rels],{stdio:'pipe'});
for(const e of entries){
  const archived=execFileSync('tar',['-xOf',archive,e.member],{maxBuffer:8*1024*1024});
  const original=fs.readFileSync(e.path);
  if(!archived.equals(original)||hash(archived)!==e.sha256)throw new Error('Archive byte verification failed');
}
handles();
for(const e of entries){
  const s=fs.lstatSync(e.path);
  if(s.dev!==e.device||s.ino!==e.inode||s.mtimeMs!==e.mtimeMs||s.size!==e.size||hash(fs.readFileSync(e.path))!==e.sha256)throw new Error('Source changed before unlink');
}
const result={checkedAt:new Date().toISOString(),archive,archiveBytes:fs.statSync(archive).size,archiveSha256:hash(fs.readFileSync(archive)),
  originalBytes:entries.reduce((n,e)=>n+e.size,0),allocatedOriginalBytes:entries.reduce((n,e)=>n+e.allocatedBytes,0),
  verification:'Every tar member byte-compared in memory with its original before unlink; SHA256 equal; old >7 days; untracked; no cwd/handles/companions',
  entries,beforeDf:before,deleted:false};
fs.writeFileSync(manifest,JSON.stringify(result,null,2)+'\n',{flag:'wx'});
for(const e of entries)fs.unlinkSync(e.path);
result.deleted=entries.every(e=>!fs.existsSync(e.path));
result.afterDf=execFileSync('df',['-k',out],{encoding:'utf8'});
result.logicalNetFreedBytes=result.allocatedOriginalBytes-fs.statSync(archive).blocks*512;
fs.writeFileSync(manifest,JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({archive,archiveBytes:result.archiveBytes,archiveSha256:result.archiveSha256,originalBytes:result.originalBytes,logicalNetFreedBytes:result.logicalNetFreedBytes,deleted:result.deleted,beforeDf:result.beforeDf,afterDf:result.afterDf},null,2));
