import {useEffect,useMemo,useState,useSyncExternalStore} from 'react'
import {createRoot} from 'react-dom/client'
import {createPortal} from 'react-dom'
import {BrowserRouter} from 'react-router-dom'
import {Box,Button,CssBaseline,MenuItem,Stack,TextField,ThemeProvider,Typography} from '@mui/material'
import {muiTheme} from '../../../reference-frontend/src/mui/theme'
import {FfFbsSupplyWorkspace} from '../../../reference-frontend/src/screens/v2/FfFbsSupplyWorkspace'
import {FfFbsSupplyAssembly} from '../../../reference-frontend/src/screens/v2/FfFbsSupplyAssembly'
import {getWorkspace,ids,installMockApi,reset} from './mockApi'
import {journal,setProposal,journalSnapshot,subscribeJournal} from './state'
installMockApi()
const query=new URLSearchParams(location.search)
setProposal(query.get("variant")!=="baseline")
if(query.get("marketplace")==="ozon")reset("ozon")
const token='fictional-wms666-demo',authHeaders=()=>({Authorization:'Bearer fictional-wms666-demo'})
function JournalCount(){useSyncExternalStore(subscribeJournal,journalSnapshot);return <>{journal.length}</>}
function JournalContents(){
 useSyncExternalStore(subscribeJournal,journalSnapshot)
 return <>{journal.slice(0,15).map((item,index)=><Box key={index} sx={{mt:1,borderTop:1,borderColor:'divider',pt:1}}><Typography variant="body2">{item.text}</Typography><pre style={{fontSize:11,whiteSpace:'pre-wrap',margin:0}}>{JSON.stringify(item.detail,null,2)}</pre></Box>)}</>
}
function App(){
 const[mode,setMode]=useState(query.get('mode')==='group'?'group':'single'),[variant,setVariant]=useState(query.get('variant')==='baseline'?'baseline':'proposal'),[marketplace,setMarketplace]=useState<'wb'|'ozon'>(query.get('marketplace')==='ozon'?'ozon':'wb'),[generation,setGeneration]=useState(0),[opened,setOpened]=useState(true),[showLog,setShowLog]=useState(false)
 const initialWorkspace=useMemo(()=>getWorkspace(ids[0]),[generation,marketplace])
 const[panelHost,setPanelHost]=useState<HTMLElement|null>(null)
 useEffect(()=>{let previous:HTMLElement|null|undefined;const update=()=>{const next=document.getElementById('demo-service-host');if(next!==previous){previous=next;setPanelHost(next)}};const observer=new MutationObserver(update);observer.observe(document.body,{childList:true,subtree:true});update();return()=>observer.disconnect()},[])
 const restart=()=>{setGeneration(value=>value+1);setOpened(true);for(const id of ids)sessionStorage.setItem(`wms:fbs:${id}:stage`,'packing')}
 return <>
  {createPortal(<Box sx={{position:'fixed',top:0,left:0,right:0,zIndex:1600,bgcolor:'#172038',color:'#fff',px:2,py:1}} data-testid="demo-service-panel">
   <Stack direction="row" spacing={1.5} sx={{alignItems:"center"}}>
    <Typography variant="caption" sx={{minWidth:110}}>Служебная панель<br/>локального макета</Typography>
    <TextField select size="small" value={mode} onChange={event=>{setMode(event.target.value);restart()}} sx={{bgcolor:'#fff',minWidth:190}}><MenuItem value="single">Отдельная поставка</MenuItem><MenuItem value="group">Сборочное задание</MenuItem></TextField>
    <TextField select size="small" value={variant} onChange={event=>{setVariant(event.target.value);setProposal(event.target.value==='proposal');restart()}} sx={{bgcolor:'#fff',minWidth:165}}><MenuItem value="proposal">Предложение</MenuItem><MenuItem value="baseline">Исходный интерфейс</MenuItem></TextField>
    <TextField select size="small" value={marketplace} onChange={event=>{const next=event.target.value as 'wb'|'ozon';setMarketplace(next);reset(next);restart()}} sx={{bgcolor:'#fff',minWidth:100}}><MenuItem value="wb">WB</MenuItem><MenuItem value="ozon">Ozon</MenuItem></TextField>
    <Button color="inherit" onClick={()=>{reset(marketplace);restart()}}>Сбросить</Button><Button color="inherit" onClick={()=>setShowLog(value=>!value)}>Журнал (<JournalCount/>)</Button>
    {!opened?<Button color="inherit" onClick={()=>setOpened(true)}>Открыть</Button>:null}
    <Typography variant="caption" sx={{ml:'auto'}}>Сканы: DEMO-1-2 / DEMO-2-2 · КИЗ: 010460000000000121DEMO<br/>Назад отключён в демо · данные вымышлены · внешняя печать отключена</Typography>
   </Stack>
  </Box>,panelHost??document.body)}
  <Box sx={{'& .MuiDialog-root:not([data-demo-dialog]) .MuiDialog-paper':{}}}/>
  <style>{`.MuiDialog-root[data-testid="fbs-workspace"] .MuiDialog-paper,.MuiDialog-root[data-testid="fbs-assembly"] .MuiDialog-paper { margin-top:76px; height:calc(100vh - 92px); }`}</style>
  {mode==='single'?<FfFbsSupplyWorkspace key={`${generation}-single`} token={token} authHeaders={authHeaders} supplyId={ids[0]} initialWorkspace={initialWorkspace} open={opened} onClose={()=>setOpened(false)}/>:<FfFbsSupplyAssembly key={`${generation}-group`} token={token} authHeaders={authHeaders} supplyIds={ids} open={opened} onClose={()=>setOpened(false)}/>}
  {showLog?<Box sx={{position:'fixed',bottom:12,right:12,zIndex:1700,width:540,maxHeight:'45vh',overflow:'auto',bgcolor:'#fff',boxShadow:5,border:1,borderColor:'divider',p:1.5}} data-testid="demo-log"><Typography variant="subtitle2">Служебный журнал · ожидаемые действия, без внешних эффектов</Typography><JournalContents/></Box>:null}
 </>
}
createRoot(document.getElementById('root')!).render(<ThemeProvider theme={muiTheme}><CssBaseline/><BrowserRouter><App/></BrowserRouter></ThemeProvider>)
