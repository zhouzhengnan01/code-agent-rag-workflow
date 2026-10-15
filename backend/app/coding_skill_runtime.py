"""Read-only, no-install dependency preflight for authorized, integrity-verified Skill packages."""
import base64
import json
from pathlib import Path
import re
import shlex

from .db import resource_get
from .sandbox import run_command
from .skill_packages import package_path, verify_package
from .workspace import tenant_workspace


SCHEMAS = {"skill_check_environment": {"description": "检查已授权完整 Skill 包的工具和依赖版本，只读、离线、不安装依赖、不执行技能脚本。", "parameters": {"type": "object", "properties": {"skill_id": {"type": "string"}}, "required": ["skill_id"]}}}

CHECKER = r'''
import base64,importlib.metadata,json,pathlib,re,shutil,subprocess,sys
data=json.loads(base64.b64decode(sys.argv[1]))
TOOLS={'python':['python','--version'],'node':['node','--version'],'npm':['npm','--version'],'git':['git','--version'],'sh':['sh','-c','printf shell'],'bash':['bash','--version'],'rg':['rg','--version'],'patch':['patch','--version'],'java':['java','--version'],'dotnet':['dotnet','--version'],'go':['go','version'],'rustc':['rustc','--version'],'ffmpeg':['ffmpeg','-version']}
def clean_version(value):
 match=re.search(r'(?<![A-Za-z0-9])v?(\d+(?:\.\d+)*(?:[-+][0-9A-Za-z.-]+)?)',value)
 return match.group(1) if match else None
def check_version(actual,wanted):
 if not wanted or wanted=='*':return True
 if not actual:return None
 def numbers(value):
  if not re.fullmatch(r'\d+(?:\.\d+)*',value):return None
  return tuple(int(x) for x in value.split('.'))
 actual=numbers(actual)
 if actual is None:return None
 clauses=[part.strip() for part in wanted.split(',')]
 for clause in clauses:
  match=re.fullmatch(r'(>=|<=|==|!=|>|<|=|\^|~)?\s*(\d+(?:\.\d+)*)',clause)
  if not match:return None
  operator,value=match.groups();expected=numbers(value);width=max(len(actual),len(expected));a=actual+(0,)*(width-len(actual));b=expected+(0,)*(width-len(expected))
  if operator=='^':
   pivot=next((i for i,x in enumerate(expected) if x),len(expected)-1);upper=list(expected);upper[pivot]+=1
   for i in range(pivot+1,len(upper)):upper[i]=0
   upper=tuple(upper)+(0,)*(width-len(upper));ok=b<=a<upper
  elif operator=='~':
   upper=list(expected);pivot=1 if len(upper)>1 else 0;upper[pivot]+=1
   for i in range(pivot+1,len(upper)):upper[i]=0
   upper=tuple(upper)+(0,)*(width-len(upper));ok=b<=a<upper
  else:ok={'>=':a>=b,'<=':a<=b,'>':a>b,'<':a<b,'!=':a!=b,'==':a==b,'=':a==b,None:a==b}[operator]
  if not ok:return False
 return True
def tool(name):
 if name not in TOOLS:return {'name':name,'status':'unsupported','reason':'binary is not in trusted check allowlist'}
 if not shutil.which(TOOLS[name][0]):return {'name':name,'status':'missing','version':None}
 try:
  run=subprocess.run(TOOLS[name],capture_output=True,text=True,timeout=5,env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/tmp','LANG':'C.UTF-8'})
  version=clean_version((run.stdout+'\n'+run.stderr)[:4096]);return {'name':name,'status':'ok' if run.returncode==0 else 'check_failed','version':version}
 except Exception:return {'name':name,'status':'check_failed','version':None}
tools=[tool(name) for name in ('python','node','npm','git')]
results=[]
for dep in data['dependencies']:
 kind,name,wanted=dep['type'],dep['name'],dep.get('version','')
 item={'type':kind,'name':name,'required_version':wanted}
 actual=None
 try:
  if kind=='python':actual=importlib.metadata.version(name)
  elif kind=='npm':
   paths=[pathlib.Path.cwd()/'node_modules'/name/'package.json',pathlib.Path('/usr/local/lib/node_modules')/name/'package.json']
   package=next((path for path in paths if path.is_file()),None)
   if package:actual=str(json.loads(package.read_text())['version'])
  elif kind=='binary':
   found=tool(name);actual=found.get('version')
   if found['status']!='ok':results.append({**item,'status':found['status'],'reason':found.get('reason')});continue
  else:results.append({**item,'status':'unsupported','reason':'unknown dependency type'});continue
 except importlib.metadata.PackageNotFoundError:pass
 except Exception:results.append({**item,'status':'check_failed'});continue
 if actual is None:results.append({**item,'status':'missing','installed_version':None});continue
 safe=clean_version(actual)
 verdict=check_version(safe,wanted)
 results.append({**item,'installed_version':safe,'status':'ok' if verdict is True else 'version_mismatch' if verdict is False else 'unsupported_constraint'})
print(json.dumps({'tools':tools,'dependencies':results,'ready':all(item['status']=='ok' for item in results),'automatic_install':False}))
'''


def _dependency(value):
    if isinstance(value, dict):
        kind = str(value.get("type") or "python").lower()
        name = str(value.get("name") or "")
        version = str(value.get("version") or value.get("constraint") or "")
    else:
        raw = str(value)
        prefix, separator, remainder = raw.partition(":")
        kind, raw = (prefix.lower(), remainder) if separator else ("python", raw)
        if kind == "npm":
            position = raw.find("@", 1)
            name, version = (raw[:position], raw[position + 1:]) if position >= 0 else (raw, "")
        else:
            match = re.fullmatch(r"([A-Za-z0-9_.-]+)(.*)", raw)
            if not match: raise ValueError("Invalid dependency declaration")
            name, version = match.groups()
    pattern = r"(?:@[A-Za-z0-9_.-]+/)?[A-Za-z0-9_.-]+" if kind == "npm" else r"[A-Za-z0-9][A-Za-z0-9_.-]*"
    if len(name) > 100 or not re.fullmatch(pattern, name) or any(part in (".", "..") for part in name.split("/")): raise ValueError("Invalid dependency name")
    if len(version) > 120 or not re.fullmatch(r"[0-9A-Za-z.*+^~<>=!,| -]*", version): raise ValueError("Invalid dependency version")
    return {"type": kind, "name": name, "version": version.strip()}


async def execute(name, args, agent, root):
    if name != "skill_check_environment": raise ValueError("Unknown Skill runtime tool")
    skill_id = str(args.get("skill_id") or "")
    if skill_id not in (agent.get("skill_ids") or []): raise PermissionError("未授权的 Skill 包")
    skill = resource_get("skills", skill_id)
    if not skill or not skill.get("enabled", True): raise PermissionError("Skill 包未启用或不存在")
    verified = verify_package(skill)
    package = package_path(skill)
    actual_files = sorted(path.relative_to(package).as_posix() for path in package.rglob("*") if path.is_file())
    if actual_files != sorted(skill.get("files") or []) or any(path.is_symlink() for path in package.rglob("*")): raise ValueError("Skill 包文件集合与完整性记录不一致")
    manifest = package / "skill.json"
    declared = json.loads(manifest.read_text(encoding="utf-8")).get("dependencies", []) if manifest.is_file() else verified["dependencies"]
    if declared != verified["dependencies"]: raise ValueError("Skill manifest 依赖与登记信息不一致")
    if not isinstance(declared, list) or len(declared) > 100: raise ValueError("Skill dependencies must be a list of at most 100 declarations")
    dependencies = [_dependency(item) for item in declared]
    try: cwd = Path(root).resolve().relative_to(tenant_workspace().resolve()).as_posix() or "."
    except ValueError: raise ValueError("Skill preflight workspace escapes tenant boundary")
    encoded = base64.b64encode(json.dumps({"dependencies": dependencies}).encode()).decode()
    result = await run_command(shlex.join(["python", "-c", CHECKER, encoded]), "read-only", cwd)
    if result.get("exit_code") != 0: raise RuntimeError("Sandbox Skill dependency preflight failed")
    report = json.loads(result.get("output") or "{}")
    return {"skill_id": skill_id, "version": verified["version"], "integrity_verified": True, "runtime": "docker-sandbox", **report}
