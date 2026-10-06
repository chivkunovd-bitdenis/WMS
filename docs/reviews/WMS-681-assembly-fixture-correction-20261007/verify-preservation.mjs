import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { execFileSync } from 'node:child_process'
import ts from '../../../frontend/node_modules/typescript/lib/typescript.js'

const file = 'frontend/src/screens/v2/FfFbsSupplyWorkspace.assembly.dom.test.tsx'
const git = (...args) => execFileSync('git', args, { encoding: 'utf8' }).trimEnd()
const baseBlob = git('rev-parse', 'a38ce8964')
const incomingBlob = git('rev-parse', '58e64cc04')
const base = git('show', baseBlob)
const incoming = git('show', incomingBlob)
const combined = fs.readFileSync(file, 'utf8')
const hash = (s) => crypto.createHash('sha256').update(s).digest('hex')
const tokens = (s) => {
  const scanner = ts.createScanner(ts.ScriptTarget.Latest, true, ts.LanguageVariant.JSX, s)
  const result = []
  while (scanner.scan() !== ts.SyntaxKind.EndOfFileToken) result.push(scanner.getTokenText())
  return JSON.stringify(result)
}
function cases(source) {
  const ast = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const result = []
  const visit = (node, suite = []) => {
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 'describe') {
      const [title, callback] = node.arguments
      visit(callback, [...suite, title.text])
      return
    }
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 'it') {
      const [title, callback] = node.arguments
      const assertions = []
      const findAssertions = (child) => {
        if (ts.isExpressionStatement(child) && child.getText(ast).startsWith('expect(')) assertions.push(tokens(child.getText(ast)))
        ts.forEachChild(child, findAssertions)
      }
      findAssertions(callback.body)
      result.push({ title: title.text, fullName: [...suite, title.text].join(' > '), body: callback.body.getText(ast), assertions })
      return
    }
    ts.forEachChild(node, (child) => visit(child, suite))
  }
  visit(ast)
  return result
}
const oldCases = cases(base)
const incomingCases = cases(incoming)
const newCases = cases(combined)
const acceptedQrCases = incomingCases.filter(c => c.title.startsWith('WMS-681:') || c.fullName.startsWith('WMS-681 recovery'))
if (oldCases.length !== 20 || acceptedQrCases.length !== 11 || newCases.length !== 31) throw new Error('Unexpected case counts')
const manifest = []
const authorityCommit = 'c7f755ce3a6c0ebce9a37567ae423aaa54565f51'
const authorityPath = 'docs/reviews/WMS-681-integration-qr-expectation-clarification.md'
const authorityBlob = git('rev-parse', `${authorityCommit}:${authorityPath}`)
const semanticSupersessions = []
oldCases.forEach((old, index) => {
  const next = newCases[index]
  if (old.fullName !== next.fullName) throw new Error(`Prior case ID changed: ${old.fullName}`)
  if (index === 9) {
    // Exactly the analyst-authorized explicit QR case; no general body/expectation exemption.
    const expected = old.body
      .replace("    boxes = [{ ...box('box-1', 1, [], false), wb_trbx_id: null }]", "    boxes = [{ ...box('box-1', 1, [], false), wb_trbx_id: null, barcode: 'FBS-OLD-PHYSICAL-1' }]\n    const originalBoxes = structuredClone(boxes)\n    qrRecoveryFixture = true\n    qrFailureIds = ['box-1']")
      .replace("    expect(document.body.textContent).toContain('Грузоместо WB для короба не создано')", "    expect(document.body.textContent).toContain('WB не ответил при получении QR.')")
      .replace("    expect(calls.filter((call) => call.path.endsWith('/retry-qr'))).toHaveLength(0)", "    expect(calls.filter((call) => call.path.endsWith('/retry-qr'))).toEqual([\n      { method: 'POST', path: `/operations/fbs-supplies/${SUPPLY_ID}/boxes/box-1/retry-qr`, body: null },\n    ])\n    expect(boxes).toEqual(originalBoxes)\n    expect(calls.some((call) => call.method === 'POST' && call.path === `/operations/fbs-supplies/${SUPPLY_ID}/boxes`)).toBe(false)\n    expect(calls.some((call) => call.path.startsWith('/qr/'))).toBe(false)")
    if (next.body !== expected || old.assertions[0] !== next.assertions[0]) throw new Error('Explicit QR change exceeds analyst-authorized correction')
    semanticSupersessions.push({ caseId: old.fullName, authorityCommit, authorityBlob, authorityPath, replacedAssertions: old.assertions.slice(1), replacementAndAddedAssertions: next.assertions.slice(1), unchangedNoPreviewAssertion: old.assertions[0] })
    manifest.push({ id: 'BASE-10', sourceBlob: baseBlob, oldCaseId: old.fullName, newCaseId: next.fullName, oldBodySha256: hash(old.body), newBodySha256: hash(next.body), oldAssertions: old.assertions.length, assertions: next.assertions.length, semanticSupersession: 'Exactly two expectations superseded by R4/R6; three additional preservation/fallback guards' })
  } else {
    if (old.body !== next.body) throw new Error(`Prior case changed: ${old.fullName}`)
    manifest.push({ id: `BASE-${String(index+1).padStart(2,'0')}`, sourceBlob: baseBlob, oldCaseId: old.fullName, newCaseId: next.fullName, unchangedBodySha256: hash(old.body), assertions: old.assertions.length, unchangedAssertionSha256: hash(JSON.stringify(old.assertions)) })
  }
})
acceptedQrCases.forEach((old,index) => {
  const next = newCases[20+index]
  if (old.title !== next.title || JSON.stringify(old.assertions) !== JSON.stringify(next.assertions)) throw new Error(`Accepted QR assertions changed: ${old.fullName}`)
  manifest.push({ id: `681-QR-${String(index+1).padStart(2,'0')}`, sourceBlob: incomingBlob, oldCaseId: old.fullName, newCaseId: next.fullName, assertions: old.assertions.length, unchangedAssertionSha256: hash(JSON.stringify(old.assertions)) })
})
if (/\b(?:it|test|describe)\s*\.\s*(?:skip|only|todo|skipIf|runIf)\b/.test(combined)) throw new Error('Conditional/exclusive/skipped cases found')
const baseStart = base.slice(base.indexOf('async function startFrame()'), base.indexOf('const showBoxes'))
const combinedStart = combined.slice(combined.indexOf('async function startFrame()'), combined.indexOf('const showBoxes'))
if (baseStart !== combinedStart) throw new Error('Shared current scanner startup assertions changed')
const incomingClickAll = incoming.slice(incoming.indexOf('const clickAllBoxQr'), incoming.indexOf("describe('WMS-681 recovery"))
const combinedClickAll = combined.slice(combined.indexOf('const clickAllBoxQr'), combined.indexOf("describe('WMS-681 recovery"))
if (incomingClickAll !== combinedClickAll) throw new Error('Accepted bulk click helper changed')
const result = { sharedCurrentScannerStartupByteIdentical: true, acceptedBulkClickHelperByteIdentical: true, baseBlob, incomingBlob, combinedBlob: git('hash-object',file), priorCases: oldCases.length, acceptedQrCases: acceptedQrCases.length, combinedCases: newCases.length, priorAssertionStatements: oldCases.reduce((n,c)=>n+c.assertions.length,0), acceptedQrAssertionStatements: acceptedQrCases.reduce((n,c)=>n+c.assertions.length,0), priorByteIdenticalBodies: 19, explicitlySupersededPriorCases: 1, allOtherPriorBodiesByteIdentical: true, currentPriorAssertionStatements: newCases.slice(0,20).reduce((n,c)=>n+c.assertions.length,0), semanticSupersessions, allAcceptedQrAssertionsTokenIdentical: true, noSkipOnlyTodo: true, cases: manifest }
fs.writeFileSync(path.join(path.dirname(new URL(import.meta.url).pathname),'case-preservation.json'), JSON.stringify(result,null,2)+'\n')
console.log(JSON.stringify({...result,cases:undefined,semanticSupersessions:undefined},null,2))
