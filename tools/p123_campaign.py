"""Sequential P1/P2/P3 controller, frozen inputs, native deadlines and negatives."""
import argparse,hashlib,importlib.util,json,os,subprocess,sys,time
from pathlib import Path


def load_support(path):
    spec=importlib.util.spec_from_file_location('p123_support',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def write(path,value):path.write_text(json.dumps(value,indent=2,default=str),encoding='utf8')


def native_memory():
    if sys.platform=='win32':
        import ctypes
        class Memory(ctypes.Structure):
            _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(n,ctypes.c_size_t) for n in ('peak_ws','ws','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile','private')]
        kernel=ctypes.WinDLL('kernel32',use_last_error=True);psapi=ctypes.WinDLL('psapi',use_last_error=True)
        kernel.GetCurrentProcess.restype=ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.POINTER(Memory),ctypes.c_ulong]
        m=Memory();m.cb=ctypes.sizeof(m)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(m),m.cb):raise ctypes.WinError(ctypes.get_last_error())
        return {'working_set_bytes':m.ws,'private_bytes':m.private,'peak_working_set_bytes':m.peak_ws}
    status=Path('/proc/self/status')
    if status.exists():
        fields={line.split(':')[0]:line.split(':')[1].strip() for line in status.read_text().splitlines() if ':' in line}
        return {name:int(fields[key].split()[0])*1024 for name,key in [('working_set_bytes','VmRSS'),('peak_working_set_bytes','VmHWM'),('anonymous_rss_bytes','RssAnon')] if key in fields}
    return {'unavailable':True}


def worker(root,phase,support_path):
    from protoagent_framework.code_generator import sha
    from protoagent_framework.compositional_synthesis import CompositionalSynthesizer
    from protoagent_framework.compositional_generator import CompositionalGenerator
    from protoagent_framework.typed_synthesis_v3 import MultiInputSynthesizer,RecoveringTableSynthesizer
    from protoagent_framework.typed_synthesis_v2 import execute as execute_ir
    from protoagent_framework.project_editing import publish_project_from_host
    s=load_support(support_path);root.mkdir(parents=True,exist_ok=True)
    began=time.perf_counter();cpu_began=time.process_time();memory_before=native_memory();segments=[];step_started={};report={'phase':phase,'state':'running'}
    if phase=='P1':
        c=s.contract();values=s.samples(10104,10)+s.challenges()
        examples=[{'input':x,'output':s.oracle(x)} for x in values]
        old=MultiInputSynthesizer();start=time.perf_counter()
        try:baseline=old.synthesize(c|{'max_depth':10},examples);baseline_status='candidate'
        except RuntimeError as exc:baseline_status=str(exc)
        report['baseline']={'status':baseline_status,'candidates':old.used,'rows':old.rows_used,'seconds':time.perf_counter()-start}
        search=CompositionalSynthesizer();candidate=search.synthesize(c,examples)
        write(root/'candidate.json',candidate)
        artifact={'files':{'solution.py':candidate['source']}};artifact['hash']=sha(artifact['files'])
        assert s.security(artifact,c)['accepted']
        reserve=s.samples(73291,100)
        outputs=s.execute(artifact,c,reserve,root/'reserve-executed')
        assert outputs==[s.oracle(x) for x in reserve]
        # Independent prior six-operation contract retained as regression.
        def six(rows):
            pairs=set();totals={}
            for r in rows:
                pair=(r['group'],r['amount'])
                if pair in pairs:continue
                pairs.add(pair)
                if r['amount']>0:totals[r['group']]=totals.get(r['group'],0)+3*(r['amount']+1)
            return [{'group':k,'amount':totals[k]} for k in sorted(totals)]
        data=[v['sales'] for v in s.samples(10100,10)]
        old6=RecoveringTableSynthesizer();r6=old6.synthesize({'key':'group','value':'amount','max_depth':6},[{'input':v,'output':six(v)} for v in data])
        six_holdout=[v['sales'] for v in s.samples(73301,30)]
        assert all(execute_ir(r6['ir'],v,'group','amount')==six(v) for v in six_holdout)
        report.update(state='passed',reserve_passed=100,reserve_total=100,candidates=search.used,rows=search.rows_used,quality=candidate['quality'],six_regression=30)
    else:
        import torch;torch.set_num_threads(1)
        from protoagent_framework import Session
        from protoagent_framework.engine import Engine
        from protoagent_framework.programming_runtime import ProgrammingRuntime
        project=phase=='P3';c=s.contract(project=project)
        generator=CompositionalGenerator(root/'generation.sqlite',library_path=root/'library.sqlite')
        qa,qa_calls=s.qa_factory(root/'qa')
        def session_event(name,data):
            op=data['operation_id']
            if name=='operation_prepared':step_started[op]=time.perf_counter()
            elif name=='checkpoint_pending' and op in step_started:
                segments.append({'actor':data['session_id'],'seconds':time.perf_counter()-step_started.pop(op)})
        def factory(path,actor,budget):
            db=path/(actor+'.sqlite')
            if db.exists():return Session.resume(db,actor,events=session_event)
            return Session(db,actor,Engine(nodes=4,seed=881,config={'enable_evidence_exploration':True,'evidence_exploration_after':2}),budget=budget,goal={'accepted':True},events=session_event)
        try:
            with ProgrammingRuntime(root/'mission',contract=c,generator=generator,verifiers={'qa':qa,'security':s.security},session_factory=factory,steps=48,generations=3) as runtime:
                # Cut after actual generated candidate effect+receipt commit,
                # before Session checkpoint. This does not select a motor action.
                def event(name,data):
                    if phase=='P2' and name=='native_effect_committed' and data['tool']=='generate' and not (root/'cut.json').exists():
                        write(root/'cut.json',{'point':'native_generation_receipt_before_session_checkpoint','used':runtime.state()['used'],'pid':os.getpid(),'cpu_seconds_self':time.process_time()-cpu_began,'memory':native_memory()})
                        os._exit(89)
                runtime.store.events=event
                result=runtime.run();write(root/'motor.json',result)
                assert result['state']['status']=='completed',result['state']['status']
                assert all(result['audit'].values())
                candidate=result['state']['candidate']
                reserve=s.samples(73401 if project else 73400,100)
                outputs=s.execute(candidate,c,reserve,root/'terminal-reserve')
                assert outputs==[s.oracle(x) for x in reserve]
                report.update(state='passed',reserve_passed=100,motor_used=result['state']['used'],attempts=result['state']['attempts'],events=result['state']['events'],reconciled=result['reconciled_sessions'],qa_calls=len(qa_calls),generation_costs=result['state'].get('generation_costs'))
                if project:
                    base=root/'base';base.mkdir()
                    for name,source in s.BASE.items():(base/name).write_text(source,encoding='utf8')
                    published=publish_project_from_host(base,root/'published',sha(s.BASE),candidate,candidate['hash'],authorize=lambda:runtime.state()['enabled'] and runtime.accepted(runtime.state()))
                    sample=s.challenges()[3]
                    # Ordinary project import resolution for its own trusted
                    # modules, not borrowed SDK paths or a sandbox claim.
                    proc=subprocess.run([sys.executable,'-B',str(root/'published/cli.py')],input=json.dumps(sample),capture_output=True,text=True,timeout=20,cwd=root/'published',env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'})
                    assert proc.returncode==0,proc.stderr
                    assert json.loads(proc.stdout)==s.oracle(sample)
                    report['publication']=published
                    report['changed_modules']=[n for n in s.BASE if candidate['files'][n]!=s.BASE[n]]
                    # A changed public requirement, not a predeclared patch.
                    changed=s.contract(project=True,include_zero=True)
                    changed['project_files']=candidate['files']
                    qa2,calls2=s.qa_factory(root/'qa-repair',include_zero=True)
                    with ProgrammingRuntime(root/'repair-mission',contract=changed,generator=generator,verifiers={'qa':qa2,'security':s.security},session_factory=factory,steps=48,generations=3) as repair:
                        repaired=repair.run();write(root/'repair-motor.json',repaired)
                        assert repaired['state']['status']=='completed',repaired['state']['status']
                        candidate2=repaired['state']['candidate']
                        reserved=s.samples(73402,100)+s.challenges()
                        outputs=s.execute(candidate2,changed,reserved,root/'repair-reserve')
                        assert outputs==[s.oracle(x,True) for x in reserved]
                        fixed=publish_project_from_host(root/'published',root/'repaired-published',sha(candidate['files']),candidate2,candidate2['hash'],authorize=lambda:repair.state()['enabled'] and repair.accepted(repair.state()))
                        report['repair']={'completed':True,'reserve_passed':100,'boundary_regressions':4,'used':repaired['state']['used'],'attempts':repaired['state']['attempts'],'hash_changed':candidate2['hash']!=candidate['hash'],'publication':fixed}
                    runtime.revoke()
                    try:publish_project_from_host(base,root/'denied',sha(s.BASE),candidate,candidate['hash'],authorize=lambda:runtime.state()['enabled'])
                    except PermissionError:report['revoked_publication_denied']=not (root/'denied').exists()
                    else:raise AssertionError('revoked publication allowed')
        finally:generator.close()
    report['seconds']=time.perf_counter()-began
    report['resources']={'cpu_seconds_self':time.process_time()-cpu_began,'children_cpu_included':False,'memory_before':memory_before,'memory_after':native_memory(),'disk_bytes':sum(p.stat().st_size for p in root.rglob('*') if p.is_file())}
    report['step_segments']=segments
    if segments:
        import math
        ordered=sorted(s['seconds'] for s in segments)
        report['step_segment_latency']={f'p{q}_seconds':ordered[math.ceil(q/100*len(ordered))-1] for q in (50,95,99)}
        report['step_segment_latency']['scope']='session segments, nested calls overlap; interrupted segment excluded, not service SLO'
    write(root/'result.json',report);print(json.dumps(report))


def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--support',type=Path,required=True);p.add_argument('--phase',choices=['P1','P2','P3']);p.add_argument('--reuse-p1',type=Path);args=p.parse_args()
    root=args.output.resolve();support=args.support.resolve()
    if args.phase:
        try:worker(root,args.phase,support)
        except BaseException as exc:
            if isinstance(exc,SystemExit):raise
            write(root/'failure.json',{'type':type(exc).__name__,'error':str(exc)})
            raise
        return
    root.mkdir(parents=True,exist_ok=False)
    import protoagent_framework,inspect
    pkg=Path(protoagent_framework.__file__).parent
    manifest={'version':protoagent_framework.__version__,'phases':['P1','P2','P3'],'deadline_each':120,'reserve_seeds':[73291,73301,73400,73401,73402],
              'LLM':False,'network':False,'source_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in pkg.glob('*.py')},
              'controller_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'support_sha256':hashlib.sha256(support.read_bytes()).hexdigest()}
    write(root/'manifest.json',manifest);results=[]
    if args.reuse_p1:
        prior=json.loads((args.reuse_p1/'manifest.json').read_text())
        if prior['source_hashes']['compositional_synthesis.py']!=manifest['source_hashes']['compositional_synthesis.py']:raise ValueError('P1 source incompatible')
        p1=json.loads((args.reuse_p1/'P1/result.json').read_text())
        if p1['state']!='passed':raise ValueError('P1 not passed')
        results.append({'phase':'P1','exit_code':0,'reused':str(args.reuse_p1),'source_sha256':prior['source_hashes']['compositional_synthesis.py']})
    for phase in manifest['phases']:
        if phase=='P1' and args.reuse_p1:continue
        folder=root/phase;folder.mkdir()
        command=[sys.executable,'-I',str(Path(__file__).resolve()),str(folder),'--support',str(support),'--phase',phase]
        write(root/'progress.json',{'phase':phase,'state':'running','pid':os.getpid(),'time':time.time()})
        started=time.perf_counter()
        try:
            proc=subprocess.run(command,capture_output=True,text=True,timeout=120,env={**os.environ,'OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'})
            (folder/'stdout.log').write_text(proc.stdout,encoding='utf8');(folder/'stderr.log').write_text(proc.stderr,encoding='utf8')
            if phase=='P2' and proc.returncode==89:
                proc=subprocess.run(command,capture_output=True,text=True,timeout=max(1,120-(time.perf_counter()-started)))
                (folder/'resume-stdout.log').write_text(proc.stdout,encoding='utf8');(folder/'resume-stderr.log').write_text(proc.stderr,encoding='utf8')
            row={'phase':phase,'exit_code':proc.returncode,'seconds':time.perf_counter()-started}
        except subprocess.TimeoutExpired:
            row={'phase':phase,'state':'deadline_exhausted','seconds':time.perf_counter()-started}
        results.append(row);write(root/'progress.json',row)
        if row.get('exit_code')!=0:break
    write(root/'result.json',{'state':'passed' if len(results)==3 and all(r.get('exit_code')==0 for r in results) else 'failed','phases':results})
    print((root/'result.json').read_text())


if __name__=='__main__':main()
