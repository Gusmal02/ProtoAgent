"""Installed-wheel regression gate. Sequential, bounded, stdlib orchestrator."""
import argparse,ast,hashlib,importlib.metadata,json,os,re,subprocess,sys,time,zipfile
from pathlib import Path

def audit_wheel(wheel):
    errors=[];licenses=[];modules=[]
    with zipfile.ZipFile(wheel) as archive:
        if sum(i.file_size for i in archive.infolist())>8*1024*1024:errors.append('wheel size budget')
        for info in archive.infolist():
            name=info.filename
            if '..' in Path(name).parts or name.startswith(('/','\\')):errors.append('archive traversal:'+name)
            if not name.startswith(('protoagent_framework/','protoagent_framework-')):errors.append('unexpected package:'+name)
            if any(part in name.lower() for part in ('site-packages','sdk-env','node_modules','.sqlite','.pth','.pem','.key','gemini_programming_config')):errors.append('unexpected payload:'+name)
            raw=archive.read(name)
            if name.endswith(('.py','.json','.md')):
                text=raw.decode('utf8')
                for label,pattern in [('private_path',r'[A-Za-z]:\\Users\\'),('gemini_key',r'AIza[0-9A-Za-z_-]{35}'),('private_key',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),('provider_secret',r'sk-[A-Za-z0-9_-]{24,}')]:
                    if re.search(pattern,text):errors.append(label+':'+name)
                if name.endswith('.py'):
                    tree=ast.parse(text);modules.append(name)
                    for node in ast.walk(tree):
                        if isinstance(node,ast.ImportFrom) and node.module and node.module.split('.')[0] in ('core','memory','f8_next'):errors.append('private namespace:'+name)
            if '/licenses/' in name:licenses.append(name)
        if not any(n.endswith('/LICENSE') for n in licenses) or not any(n.endswith('/NOTICE') for n in licenses):errors.append('missing license or notice')
    return {'accepted':not errors,'errors':errors,'module_count':len(modules),'license_files':licenses,'wheel_sha256':hashlib.sha256(wheel.read_bytes()).hexdigest()}

def main():
    p=argparse.ArgumentParser();p.add_argument('--wheel',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--profile',choices=('base','full'),default='full');args=p.parse_args()
    root=Path(__file__).resolve().parents[1];out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);started=time.perf_counter()
    report={'state':'running','profile':args.profile,'package_audit':audit_wheel(args.wheel.resolve()),'commands':[],'dependencies':[]}
    def command(label,arguments,timeout=180):
        began=time.perf_counter();env=dict(os.environ,OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
        proc=subprocess.run([sys.executable,'-I']+list(map(str,arguments)),cwd=out,capture_output=True,text=True,timeout=timeout,env=env)
        (out/(label+'.stdout')).write_text(proc.stdout,encoding='utf8');(out/(label+'.stderr')).write_text(proc.stderr,encoding='utf8')
        report['commands'].append({'label':label,'exit_code':proc.returncode,'seconds':time.perf_counter()-began})
        (out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf8')
        if proc.returncode:raise RuntimeError(label+' failed; inspect preserved logs')
    try:
        if not report['package_audit']['accepted']:raise RuntimeError('package content audit failed')
        command('installed_lazy',['-c',"import protoagent_framework as p,sys,json; from pathlib import Path; print(json.dumps({'version':p.__version__,'path':p.__file__,'torch_loaded':'torch' in sys.modules})); assert 'site-packages' in str(Path(p.__file__)); assert 'torch' not in sys.modules"])
        command('installed_payload',['-c',"import zipfile,sys,hashlib,json,protoagent_framework as p; from pathlib import Path; root=Path(p.__file__).parent.parent; z=zipfile.ZipFile(sys.argv[1]); names=[n for n in z.namelist() if n.startswith('protoagent_framework/') and n.endswith('.py')]; mismatches=[n for n in names if not (root/n).is_file() or hashlib.sha256((root/n).read_bytes()).digest()!=hashlib.sha256(z.read(n)).digest()]; print(json.dumps({'checked':len(names),'mismatches':mismatches})); assert not mismatches",args.wheel.resolve()])
        for name in ('protoagent-framework','numpy','torch','networkx'):
            try:report['dependencies'].append({'name':name,'version':importlib.metadata.version(name),'license':importlib.metadata.metadata(name).get('License-Expression') or importlib.metadata.metadata(name).get('License')})
            except importlib.metadata.PackageNotFoundError:
                if args.profile=='full':raise
        patterns=['test_release_base.py','test_release_completion.py','test_release_collaboration.py'] if args.profile=='base' else ['test_release_*.py']
        for index,pattern in enumerate(patterns):command('unit_'+str(index),['-m','unittest','discover','-s',root/'tests','-p',pattern,'-v'])
        command('governance_conformance',['-m','protoagent_framework.conformance','--episodes','64','--output',out/'conformance.json'])
        command('example_data',[root/'examples/referenced_data.py','--workspace',out/'example-data'])
        command('example_collaboration',[root/'examples/collaboration_data_ops.py','--workspace',out/'example-team'])
        if args.profile=='full':command('example_motor',[root/'examples/local_counter.py','--workspace',out/'example-motor'])
        report['state']='passed'
    except Exception as exc:report['state']='failed';report['error']=type(exc).__name__+': '+str(exc)
    report['wall_seconds']=time.perf_counter()-started
    report['source_hashes']={str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest() for directory in ('tests','examples') for path in sorted((root/directory).glob('*.py'))}
    (out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps({'state':report['state'],'seconds':report['wall_seconds'],'output':str(out)}))
    if report['state']!='passed':raise SystemExit(1)

if __name__=='__main__':main()
