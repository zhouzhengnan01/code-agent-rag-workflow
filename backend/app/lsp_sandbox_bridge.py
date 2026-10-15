"""Source copied into a Docker command; only administrator-selected argv is executed."""
BRIDGE = r'''
import base64,json,subprocess,sys
data=json.loads(base64.b64decode(sys.argv[1]))
p=subprocess.Popen(data['argv'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
seq=0
diagnostics={}
def send(payload):
 raw=json.dumps(payload).encode();p.stdin.write(('Content-Length: %d\r\n\r\n'%len(raw)).encode()+raw);p.stdin.flush()
def request(method,params):
 global seq
 seq+=1;rid=seq;send({'jsonrpc':'2.0','id':rid,'method':method,'params':params})
 while True:
  headers={}
  while True:
   line=p.stdout.readline()
   if not line: raise RuntimeError('LSP process exited')
   if line in (b'\r\n',b'\n'):break
   k,v=line.decode().split(':',1);headers[k.lower()]=v.strip()
  size=int(headers['content-length'])
  if size>1048576:raise RuntimeError('LSP frame too large')
  message=json.loads(p.stdout.read(size))
  if message.get('method')=='textDocument/publishDiagnostics':
   info=message.get('params') or {};diagnostics[info.get('uri')]=info.get('diagnostics',[])
  if message.get('id')==rid:
   if message.get('error'):raise RuntimeError(str(message['error']))
   return message.get('result')
  if 'id' in message and message.get('method'):
   method=message['method'];items=(message.get('params') or {}).get('items',[])
   value=[None]*len(items) if method=='workspace/configuration' else ([] if method=='workspace/workspaceFolders' else None)
   send({'jsonrpc':'2.0','id':message['id'],'result':value})
try:
 request('initialize',{'processId':None,'rootUri':data['root_uri'],'capabilities':{'textDocument':{'publishDiagnostics':{},'diagnostic':{}}},'workspaceFolders':[{'uri':data['root_uri'],'name':'workspace'}]})
 send({'jsonrpc':'2.0','method':'initialized','params':{}})
 for doc in data['documents']:send({'jsonrpc':'2.0','method':'textDocument/didOpen','params':{'textDocument':doc}})
 try:result=request(data['method'],data['params'])
 except RuntimeError:
  if data['method']!='textDocument/diagnostic':raise
  uri=data['params']['textDocument']['uri']
  request('textDocument/documentSymbol',{'textDocument':{'uri':uri}})
  result={'kind':'full','items':diagnostics.get(uri,[]),'source':'publishDiagnostics-fallback','complete':False}
 print(json.dumps({'result':result},ensure_ascii=False))
finally:
 p.terminate()
 try:p.wait(timeout=2)
 except subprocess.TimeoutExpired:p.kill()
'''
