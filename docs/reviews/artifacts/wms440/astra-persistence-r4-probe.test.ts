import { expect, it, vi } from 'vitest'
import { beginIntakePickerAttempt, finishIntakePickerAttempt, intakeMutation, readIntake, sendIntakeMutations } from './inboundDraftPersistence'

function setup() {
  const disk = new Map<string,string>()
  vi.stubGlobal('localStorage', {getItem:(k:string)=>disk.get(k)??null,setItem:(k:string,v:string)=>disk.set(k,v)})
  const token=`h.${btoa(JSON.stringify({tenant_id:'review',sub:'reviewer'}))}.s`
  const path='/operations/inbound-intake-requests/review/lines'
  const accepted:Record<string,number>={}
  const appliedIds=new Set<string>()
  let loseNextB=false
  const fetch=vi.fn().mockImplementation(async (_path:string,request:{body:string})=>{
    const body=JSON.parse(request.body)
    if(body.expected_qty>1_000_000_000) return new Response('{"detail":"invalid_qty"}',{status:422})
    if(!appliedIds.has(body.mutation_id)) {
      appliedIds.add(body.mutation_id)
      accepted[body.product_id]=(accepted[body.product_id]??0)+body.expected_qty
    }
    if(body.product_id==='b' && loseNextB) {loseNextB=false; throw new Error('response lost')}
    return new Response('{}')
  })
  vi.stubGlobal('fetch',fetch)
  const applyPicker=(quantities:Record<string,number>)=>Object.keys(quantities).length
    ? sendIntakeMutations(token,'review',Object.entries(quantities).map(([product_id,expected_qty])=>intakeMutation('POST',path,{product_id,expected_qty,increment:true})))
    : Promise.resolve(finishIntakePickerAttempt(token,'review'))
  return {token,accepted,fetch,applyPicker,loseB:()=>{loseNextB=true}}
}

it.each(['correct B','deselect B','replace B','empty selection','close and new attempt'])('preserves picker attempt lifecycle: %s', async(mode)=>{
  const s=setup()
  beginIntakePickerAttempt(s.token,'review')
  await expect(s.applyPicker({a:3,b:1_000_000_001})).rejects.toThrow('invalid_qty')
  expect(s.accepted).toEqual({a:3})
  if(mode==='correct B') {await s.applyPicker({a:3,b:2});expect(s.accepted).toEqual({a:3,b:2})}
  if(mode==='deselect B') {await s.applyPicker({a:3});expect(s.accepted).toEqual({a:3});expect(s.fetch).toHaveBeenCalledTimes(2)}
  if(mode==='replace B') {await s.applyPicker({a:3,c:2});expect(s.accepted).toEqual({a:3,c:2})}
  if(mode==='empty selection') {await s.applyPicker({});expect(s.accepted).toEqual({a:3});expect(s.fetch).toHaveBeenCalledTimes(2)}
  if(mode==='close and new attempt') {finishIntakePickerAttempt(s.token,'review');beginIntakePickerAttempt(s.token,'review');await s.applyPicker({a:3});expect(s.accepted).toEqual({a:6})}
  expect(readIntake(s.token,'review').pickerAttempt).toBeUndefined()
  expect(readIntake(s.token,'review').applied).toBeUndefined()
  expect(readIntake(s.token,'review').pending).toBeUndefined()
  vi.unstubAllGlobals()
})

it('replays the exact lost B after closing the picker, then allows a new A batch', async()=>{
  const s=setup()
  beginIntakePickerAttempt(s.token,'review');s.loseB()
  await expect(s.applyPicker({a:3,b:2})).rejects.toThrow('response lost')
  const pending=readIntake(s.token,'review').pending
  finishIntakePickerAttempt(s.token,'review')
  expect(readIntake(s.token,'review').pending).toEqual(pending)
  await sendIntakeMutations(s.token,'review')
  expect(s.accepted).toEqual({a:3,b:2})
  expect(s.fetch.mock.calls[1][1].body).toEqual(s.fetch.mock.calls[2][1].body)
  beginIntakePickerAttempt(s.token,'review');await s.applyPicker({a:1})
  expect(s.accepted).toEqual({a:4,b:2})
  vi.unstubAllGlobals()
})
