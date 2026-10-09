# Review-only probe: real Printer/HTTP code; fake queue, never calls a physical printer.
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[4];out=Path(__import__('tempfile').mkdtemp(prefix='wms625-review-native-'))
subprocess.run(['clang','-c',str(root/'tools/print-agent/wms_cups_observe.c'),'-o',str(out/'cups.o')],check=True)
base=subprocess.check_output(['git','show','a2b766393:tools/print-agent/wms_print_direct_macos.swift'],cwd=root,text=True)
head=subprocess.check_output(['git','show','20ab8fa83:tools/print-agent/wms_print_direct_macos.swift'],cwd=root,text=True)
png='iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8//8/AwMDEwMDAwMDAwAkBgMB/DXemwAAAABJRU5ErkJggg=='
bench='''
let directory=URL(fileURLWithPath:CommandLine.arguments[1])
var count=0
let start=Date()
private let p=try Printer(directory:directory,autoWork:false,submit:{_,_ in count+=1;return "test-\\(count)"},queue:{"test"})
for i in 0..<350 {
 let body:[String:Any]=["idempotencyKey":"batch-\\(i)","imageDataUrl":"data:image/png;base64,PNG","widthMm":58,"heightMm":40]
 _=try p.printJob(body);p.process("batch-\\(i)");_=try p.printJob(body)
}
print("seconds=\\(Date().timeIntervalSince(start)) submissions=\\(count)")
'''.replace('PNG',png)
http='''
private func request(_ p:Printer,_ body:[String:Any]) throws -> String {
 var fds:[Int32]=[0,0]
 guard socketpair(AF_UNIX,SOCK_STREAM,0,&fds)==0 else { throw PrintError.message("socketpair failed") }
 let data=try JSONSerialization.data(withJSONObject:body)
 let header="POST /print HTTP/1.1\\r\\nHost: 127.0.0.1:\\(port)\\r\\nX-WMS-Print: 1\\r\\nContent-Length: \\(data.count)\\r\\n\\r\\n"
 sendAll(fds[0],data:Data(header.utf8)+data)
 handle(fds[1],printer:p)
 var response=Data();var buffer=[UInt8](repeating:0,count:8192)
 while true {let n=recv(fds[0],&buffer,buffer.count,0);if n<=0 {break};response.append(contentsOf:buffer[0..<n])}
 Darwin.close(fds[0]);return String(data:response,encoding:.utf8)!
}
let directory=URL(fileURLWithPath:CommandLine.arguments[1])
try FileManager.default.createDirectory(at:directory,withIntermediateDirectories:true)
let png=Data(base64Encoded:"PNG")!
var id=png;id.append(Data("|58.0x40.0".utf8))
try JSONSerialization.data(withJSONObject:["import-receipt":["hash":digest(id),"receipt":"old-7"],"import-unknown":["hash":digest(id)]]).write(to:directory.appendingPathComponent("direct-jobs.json"))
var count=0
private let p=try Printer(directory:directory,submit:{_,_ in count+=1;return "test-\\(count)"},queue:{"test"})
for key in ["new","new","import-receipt","import-unknown","import-unknown"] {
 let body:[String:Any]=["idempotencyKey":key,"imageDataUrl":"data:image/png;base64,PNG","widthMm":58,"heightMm":40]
 let response=try request(p,body)
 let parts=response.components(separatedBy:"\\r\\n\\r\\n")
 let obj=try JSONSerialization.jsonObject(with:Data(parts[1].utf8)) as! [String:Any]
 print("key=\\(key) \\(parts[0].components(separatedBy:"\\r\\n")[0]) status=\\(obj["status"]!) receipt=\\(obj["receipt"] ?? "nil") submissions=\\(count)")
}
'''.replace('PNG',png)
for name,src,append in [('bench-before',base,bench),('bench-after',head,bench),('http',head,http)]:
 (out/(name+'.swift')).write_text(src.rsplit('\ndo {\n    if CommandLine.arguments',1)[0]+append)
 subprocess.run(['/usr/bin/swiftc','-module-cache-path','/private/tmp/wms625-review-module-cache','-O',str(out/(name+'.swift')),'-Xlinker',str(out/'cups.o'),'-lcups','-o',str(out/name)],check=True)
 if name=='http':subprocess.run([str(out/name),str(out/'http-store')],check=True)
for i in range(3):
 for name in (['bench-before','bench-after'] if i%2==0 else ['bench-after','bench-before']):
  print(name,i,flush=True)
  subprocess.run([str(out/name),str(out/(name+str(i)))],check=True)
