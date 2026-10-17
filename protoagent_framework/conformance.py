"""Installed, stdlib-only public conformance profile over a native adapter."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import random
import time
from .api import GovernedRuntime, ContractError
from .canary_adapter import CanaryAdapter
from .contracts import ActionSpec, QuerySpec, Contract
from .wire import dumps, loads

def campaign(seed=101, episodes=100, factory=CanaryAdapter):
    rng=random.Random(seed); ticks=[0.]; adapter=factory()
    contract=Contract('v1',frozenset(('A','B')),frozenset((adapter.manifest.name,op)
        for op in ('read_state','pause','resume','rollback')))
    runtime=GovernedRuntime(contract,clock=lambda:ticks[0],proof_ttl=2,capacity=max(32,episodes*3))
    runtime.register(adapter); adapter.seed('A'); adapter.seed('B')
    checks=[]; rows=[]; timings=[]
    def check(name, passed): checks.append({'check':name,'passed':bool(passed)})
    try:
        for i in range(episodes):
            entity=rng.choice(('A','B')); other='A' if entity=='B' else 'B'
            before=adapter.state(entity); protected=adapter.state(other)
            proof=runtime.observe(QuerySpec(adapter.manifest.name,'read_state',entity))[0]
            op='resume' if before[0] else 'pause'
            action=loads(dumps(ActionSpec(adapter.manifest.name,op,entity,(proof.evidence_id,))))
            check('wire_roundtrip',action==ActionSpec(adapter.manifest.name,op,entity,(proof.evidence_id,)))
            mode=i%8; decision=runtime.authorize(action); started=time.perf_counter()
            if mode==0:
                runtime.set_contract(replace(contract,version='revoked',operations=frozenset()))
                result=runtime.execute(action,decision)
                check('revocation',result.state=='denied' and adapter.state(entity)==before)
                runtime.set_contract(contract)
            elif mode==1:
                forged=replace(action,evidence_ids=('unissued',)); result=runtime.execute(forged,runtime.authorize(forged))
                check('forged_evidence',result.state=='denied' and adapter.state(entity)==before)
            elif mode==2:
                ticks[0]+=3; result=runtime.execute(action,decision)
                check('expiry',result.state=='denied' and adapter.state(entity)==before)
            elif mode==3:
                wrong=replace(action,entity=other); result=runtime.execute(wrong,runtime.authorize(wrong))
                check('foreign_evidence',result.state=='denied' and adapter.state(other)==protected)
            elif mode==4:
                adapter.fail_once=True; result=runtime.execute(action,decision)
                check('transaction_failure',result.state=='failed' and adapter.state(entity)==before)
                result=runtime.execute(action,runtime.authorize(action))
                check('retry_after_failure',result.state=='executed')
                check('rollback',runtime.rollback(result.outcome.rollback_token).state=='rolled_back')
            elif mode==5:
                key='request-'+str(i)
                with ThreadPoolExecutor(max_workers=4) as pool:
                    answers=list(pool.map(lambda _:runtime.execute(action,decision,idempotency_key=key),range(4)))
                result=answers[0]
                check('single_mutation',all(a==result for a in answers) and adapter.state(entity)[1]==before[1]+1)
                runtime.rollback(result.outcome.rollback_token)
            elif mode==6:
                result=runtime.execute(action,decision)
                stale=runtime.execute(action,decision)
                check('native_revision',result.state=='executed' and stale.state=='denied')
                runtime.rollback(result.outcome.rollback_token)
            else:
                result=runtime.execute(action,decision)
                check('legitimate_execution',result.state=='executed')
                runtime.rollback(result.outcome.rollback_token)
            timings.append((time.perf_counter()-started)*1000)
            check('value_restored',adapter.state(entity)[0]==before[0])
            check('other_entity_unchanged',adapter.state(other)==protected)
            rows.append({'episode':i,'mode':mode,'entity':entity,'result':result.state,'value':adapter.state(entity)[0]})
        check('audit_intact',runtime.audit.intact())
        return {'seed':seed,'episodes':episodes,'checks':checks,'rows':rows,
                'passed':all(c['passed'] for c in checks),'p95_ms':sorted(timings)[int(.95*(len(timings)-1))]}
    finally: adapter.close()

def main():
    parser=argparse.ArgumentParser(description='Experimental ProtoAgent SDK conformance (not cognitive superiority).')
    parser.add_argument('--seed',type=int,default=101); parser.add_argument('--episodes',type=int,default=100)
    parser.add_argument('--output')
    args=parser.parse_args()
    if not 8<=args.episodes<=10000: parser.error('episodes must be 8..10000')
    report=campaign(args.seed,args.episodes)
    payload=json.dumps(report,indent=2)
    if args.output:
        from pathlib import Path
        Path(args.output).write_text(payload,encoding='utf8')
    print(json.dumps({'passed':report['passed'],'episodes':args.episodes,'checks':len(report['checks']),
                      'p95_ms':report['p95_ms']}))
    return 0 if report['passed'] else 1
if __name__=='__main__': raise SystemExit(main())
