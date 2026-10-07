import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import {fileURLToPath} from 'node:url'
import {realpathSync} from 'node:fs'
import {demoTransform} from './demoTransform'
const root=fileURLToPath(new URL('.',import.meta.url))
export default defineConfig({root,cacheDir:fileURLToPath(new URL('../../../node_modules/.vite',import.meta.url)),plugins:[demoTransform(),react()],resolve:{dedupe:['react','react-dom','@mui/material','@emotion/react','@emotion/styled']},server:{host:'127.0.0.1',port:16667,strictPort:true,fs:{allow:[fileURLToPath(new URL('../../../',import.meta.url)),realpathSync(fileURLToPath(new URL('../../../reference-frontend',import.meta.url))),realpathSync(fileURLToPath(new URL('../../../node_modules',import.meta.url)))]}}})
