import { expect, it, vi } from 'vitest'
import { intakeMutation, readIntake, sendIntakeMutations } from './inboundDraftPersistence'

it.each(['correct B', 'deselect B'])('checks partial picker continuation: %s', async (mode) => {
  const disk = new Map<string,string>()
  vi.stubGlobal('localStorage', {getItem:(k:string)=>disk.get(k)??null,setItem:(k:string,v:string)=>disk.set(k,v)})
  const token=`h.${btoa(JSON.stringify({tenant_id:'review',sub:'reviewer'}))}.s`
  const path='/operations/inbound-intake-requests/review/lines'
  const accepted:Record<string,number>={}
  vi.stubGlobal('fetch',vi.fn().mockImplementation(async (_path:string,request:{body:string})=>{
    const body=JSON.parse(request.body)
    if(body.expected_qty>1_000_000_000) return new Response('{"detail":"invalid_qty"}',{status:422})
    accepted[body.product_id]=(accepted[body.product_id]??0)+body.expected_qty
    return new Response('{}')
  }))
  const applyPicker=(quantities:Record<string,number>)=>sendIntakeMutations(token,'review',Object.entries(quantities).map(([product_id,expected_qty])=>intakeMutation('POST',path,{product_id,expected_qty,increment:true})))
  await expect(applyPicker({a:3,b:1_000_000_001})).rejects.toThrow('invalid_qty')
  expect(accepted).toEqual({a:3})
  expect(readIntake(token,'review').pending).toBeUndefined()
  if (mode === 'correct B') {
    await applyPicker({a:3,b:2})
    expect(accepted).toEqual({a:3,b:2})
  } else {
    await applyPicker({a:3})
    expect(accepted).toEqual({a:6})
  }
  vi.unstubAllGlobals()
})
