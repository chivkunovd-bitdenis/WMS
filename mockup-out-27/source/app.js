import { useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { ThemeProvider, CssBaseline, Box, Typography, Paper, Stack, Button, Tabs, Tab, Divider, FormControl, InputLabel, Select, MenuItem, Link } from '@mui/material'
import ArrowForward from '@mui/icons-material/ArrowForward'
import ArrowBack from '@mui/icons-material/ArrowBack'
import OpenInNew from '@mui/icons-material/OpenInNew'
import { muiTheme } from '../../frontend/src/mui/theme'
import { PrintAction, SecondaryAction } from '../../frontend/src/ui-kit/Actions'
import forms from './forms.json'

const choices = [
  {id:'inline', file:'variant-inline.html', title:'Размер и цвет под товаром', description:'Характеристики внутри строки товара. Существующие колонки остаются на своих местах.', number:'01'},
  {id:'columns', file:'variant-columns.html', title:'Размер и цвет в колонках', description:'Отдельные колонки рядом с наименованием. Удобно сравнивать варианты товара по вертикали.', number:'02'},
]
const variant=document.body.dataset.variant

function Gallery() {
  return <Box sx={{maxWidth:1160,mx:'auto',px:{xs:2,md:4},py:5}}>
    <Typography variant="overline" color="primary">WMS-680 · Макеты печатных форм</Typography>
    <Typography variant="h4" sx={{fontWeight:800,letterSpacing:'-.025em',mt:1}}>Размер и цвет в накладных</Typography>
    <Typography color="text.secondary" sx={{mt:1,maxWidth:740}}>Два варианта оформления существующих накладных. В каждом можно открыть FBO, приёмку и отгрузку, сравнить с текущей формой и вызвать печать.</Typography>
    <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',md:'1fr 1fr'},gap:3,mt:4}}>
      {choices.map(choice=><Paper key={choice.id} variant="outlined" sx={{overflow:'hidden'}}>
        <Box component="a" href={choice.file} aria-label={`Открыть: ${choice.title}`} sx={{display:'block',height:260,overflow:'hidden',position:'relative',bgcolor:'#dbe1ec',borderBottom:'1px solid',borderColor:'divider'}}>
          <iframe src={`documents/${choice.id}-fbo-short.html`} title={`Образец: ${choice.title}`} tabIndex={-1} style={{width:870,height:1150,border:0,transform:'scale(.55)',transformOrigin:'top left',position:'absolute',left:'50%',marginLeft:-239,pointerEvents:'none'}}/>
        </Box>
        <Box sx={{p:3}}>
          <Typography variant="overline" color="text.secondary">Вариант {choice.number}</Typography>
          <Typography variant="h6">{choice.title}</Typography>
          <Typography color="text.secondary" sx={{mt:1,minHeight:54}}>{choice.description}</Typography>
          <Button href={choice.file} variant="contained" endIcon={<ArrowForward/>} sx={{mt:2}}>Открыть вариант</Button>
        </Box>
      </Paper>)}
    </Box>
    <Typography variant="body2" color="text.secondary" sx={{mt:3}}>Демонстрационные товары и реквизиты. Макеты не обращаются к WMS; печать открывает только выбранный образец.</Typography>
  </Box>
}

function Preview() {
  const choice=choices.find(c=>c.id===variant)
  const [form,setForm]=useState('fbo')
  const [count,setCount]=useState('short')
  const [current,setCurrent]=useState(false)
  const [height,setHeight]=useState(1170)
  const frame=useRef(null)
  const file=`documents/${current?'current':choice.id}-${form}-${count}.html`
  function loaded() { setHeight((frame.current?.contentDocument?.documentElement.scrollHeight??1150)+24) }
  return <Box sx={{maxWidth:1280,mx:'auto',px:{xs:1.5,md:4},py:3}}>
    <Stack direction="row" alignItems="center" justifyContent="space-between" gap={2} sx={{mb:2}}>
      <Link href="index.html" underline="hover" sx={{display:'inline-flex',alignItems:'center',gap:.5,fontSize:14}}><ArrowBack fontSize="small"/>Все варианты</Link>
      <Typography variant="caption" color="text.secondary">WMS-680 · Вымышленные данные</Typography>
    </Stack>
    <Typography variant="h5">{choice.title}</Typography>
    <Typography color="text.secondary" variant="body2" sx={{mt:.5,mb:2.5}}>{choice.description}</Typography>
    <Paper variant="outlined" sx={{overflow:'hidden'}}>
      <Tabs value={form} onChange={(_,value)=>{setForm(value)}} variant="scrollable" scrollButtons="auto" aria-label="Печатная форма">
        {forms.map(f=><Tab key={f.id} value={f.id} label={f.label} sx={{fontSize:13,minHeight:52}}/>)}
      </Tabs>
      <Divider/>
      <Stack direction={{xs:'column',md:'row'}} alignItems={{xs:'stretch',md:'center'}} justifyContent="space-between" spacing={2} sx={{p:2}}>
        <Stack direction="row" alignItems="center" flexWrap="wrap" gap={1.5}>
          <FormControl size="small" sx={{minWidth:190}}>
            <InputLabel id="sample-label">Образец документа</InputLabel>
            <Select labelId="sample-label" label="Образец документа" value={count} onChange={e=>setCount(e.target.value)}>
              <MenuItem value="short">6 позиций · 92 шт.</MenuItem><MenuItem value="long">36 позиций · 552 шт.</MenuItem>
            </Select>
          </FormControl>
          <Button variant="text" onClick={()=>setCurrent(c=>!c)} aria-pressed={current}>{current?'Вернуться к макету':'Текущая форма'}</Button>
        </Stack>
        <Stack direction="row" spacing={1} alignItems="center">
          <SecondaryAction href={file} target="_blank" endIcon={<OpenInNew fontSize="small"/>}>Открыть лист</SecondaryAction>
          <PrintAction placement="panel" what="накладную" onClick={()=>{frame.current?.contentWindow?.focus();frame.current?.contentWindow?.print()}}/>
        </Stack>
      </Stack>
      <Divider/>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{px:2,py:1,bgcolor:'#f8fafc'}}>
        <Typography variant="caption" color="text.secondary">{current?'Текущая форма без размера и цвета':'Предпросмотр печатной формы'} · A4</Typography>
        <Link href={choices.find(c=>c.id!==variant).file} underline="hover" variant="caption">Другой вариант</Link>
      </Stack>
      <Box sx={{bgcolor:'background.default',overflowX:'auto',py:1}}>
        <iframe key={file} ref={frame} onLoad={loaded} src={file} title="Предпросмотр накладной" style={{display:'block',width:'100%',minWidth:830,height,border:0}}/>
      </Box>
    </Paper>
    <Typography variant="caption" color="text.secondary" sx={{display:'block',mt:1.5}}>В образце есть длинные характеристики и отсутствующие значения «—». Колонки «Факт» в листах приёмки и отгрузки оставлены пустыми для ручного заполнения.</Typography>
  </Box>
}
function App(){return <ThemeProvider theme={muiTheme}><CssBaseline/><Box sx={{bgcolor:'background.paper',borderBottom:'1px solid',borderColor:'divider',px:{xs:2,md:4},py:1.5}}><Stack direction="row" alignItems="center" spacing={2}><Typography sx={{fontWeight:900,fontSize:20,color:'primary.main'}}>WMS</Typography><Divider orientation="vertical" flexItem/><Typography variant="body2" color="text.secondary">Макеты накладных</Typography></Stack></Box>{variant?<Preview/>:<Gallery/>}</ThemeProvider>}
createRoot(document.getElementById('root')).render(<App/>);
