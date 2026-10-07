// Read immutable Git objects; do not repeat completed 419 runtime checks.
const {execFileSync} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const ts = require('/Users/deniscivkunov/Projects/WMS/frontend/node_modules/typescript');
const before = '4190460c97db0db439712b17a083c5b474ee3d74';
const target = 'b6c2140d85e7ca5f8b7ede1cb26d30b1744c55a6';
const P = '98978e667bbc305cc08a9b541016fef06686388e';
const git = (...args) => execFileSync('git', args);
const blob = (ref, name) => git('show', `${ref}:${name}`);
const data = (ref, name) => JSON.parse(blob(ref, name));
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
const base = 'docs/evidence/WMS-652/final-closure-20261007/';
const harness = 'frontend/src/test-contracts/inbound684586Harness.tsx';
const proof = data(target, base + '684-type-only-proof.json');
assert.equal(ts.version, proof.typescript);
assert.equal(blob(P,harness).toString(), blob(target,harness).toString());
const old = blob(before,harness).toString();
const expected = old.replace('const printWindow = frame.contentWindow!', 'const printWindow: Window & typeof globalThis = frame.contentWindow! as Window & typeof globalThis');
assert.notEqual(expected, old);
assert.equal(blob(target,harness).toString(), expected);
const compile = text => ts.transpileModule(text, {fileName:harness, compilerOptions:proof.compilerOptions}).outputText;
assert.equal(compile(old), compile(expected));
assert.equal(sha(compile(expected)), proof.compiled_sha256);
assert.deepEqual(git('diff','--name-only',before,target).toString().trim().split('\n').sort(),
 [base+'684-type-only-proof.json',base+'proposed-final-P-S.json',harness,'guards/PROCESS_CONTRACTS.json'].sort());
const policy = data(target,'guards/PROCESS_CONTRACTS.json');
const prior = data(before,'guards/PROCESS_CONTRACTS.json');
assert.equal(policy.files[harness],sha(blob(target,harness)));
prior.files[harness] = policy.files[harness];
assert.deepEqual(policy,prior);
const template = base+'wms680-reviewed-activation-template.json';
assert.equal(blob(before,template).toString(),blob(target,template).toString());
const proposalPath = base+'proposed-final-P-S.json';
const proposal = data(target,proposalPath);
const proposalBefore = data(before,proposalPath);
proposalBefore.product_reference_P = P;
for (const field of ['workflow_product_scope_trusted_ref','fixture_final_reviewed_source','fixture_frozen_source','fixture_accepted_sources_addition']) proposalBefore.reviewed_activation_template[field] = P;
proposalBefore.latest_product_changes.push('WMS684 erased type-only iframe annotation; transpiled JS identical to419 proof recorded');
assert.deepEqual(proposal,proposalBefore);
const productScope = blob(target,'scripts/ci/product_scope.py');
const delta = JSON.parse(execFileSync('python3',['-c',`import json,subprocess,types; m=types.ModuleType('scope'); exec(subprocess.check_output(['git','show','${target}:scripts/ci/product_scope.py']),m.__dict__); print(json.dumps([p for p in subprocess.check_output(['git','diff','--name-only','--no-renames','${P}','${target}']).decode().splitlines() if m.product_path(p)]))`]).toString());
assert.deepEqual(delta,[]);
git('merge-base','--is-ancestor',P,target);
const result = {target,proposed_P:P,typescript:ts.version,compilerOptions:proof.compilerOptions,
 compiled_js_identical:true,compiled_js_sha256:sha(compile(expected)),exact_annotation_only:true,
 policy_only_harness_hash_updated:true,policy_counts:[Object.keys(policy.files).length,Object.keys(policy.suites).length,Object.values(policy.suites).reduce((n,s)=>n+s.cases.length,0)],
 product_delta_from_P:delta,unchanged_680_template:true,
 approved_template_sha256:{[template]:sha(blob(target,template)),[proposalPath]:sha(blob(target,proposalPath))},
 full_tsc_eslint:'Tester publication claim inspected; not independently rerun in this incremental review'};
fs.writeFileSync(path.join(__dirname,'incremental-b6.json'),JSON.stringify(result,null,2)+'\n');
fs.writeFileSync(path.join(__dirname,'P-S-template-b6.json'),blob(target,proposalPath));
fs.writeFileSync(path.join(__dirname,'684-type-only-proof-b6.json'),blob(target,base+'684-type-only-proof.json'));
console.log(JSON.stringify(result,null,2));
