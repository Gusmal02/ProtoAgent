"""Local human handoff; not authentication, deployment or a multi-user service."""
import argparse
import json
from pathlib import Path
from .code_generator import sha,validate_candidate


def prepare_review(directory, candidate, contract, reviews):
    candidate=validate_candidate(candidate,candidate.get('author','unknown'))
    if set(reviews)!={'qa','security'} or any(r.get('accepted') is not True or r.get('hash')!=candidate['hash'] for r in reviews.values()):
        raise PermissionError('fresh QA/Security required')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    (directory/'files').mkdir()
    for name,source in candidate['files'].items():
        with (directory/'files'/name).open('x',encoding='utf8',newline='\n') as stream:stream.write(source)
    packet={'schema':1,'state':'awaiting_human','artifact_hash':candidate['hash'],'files':sorted(candidate['files']),
            'contract_hash':sha(contract),'contract':contract,'reviews':reviews,
            'scope':'local exercise review, no deployment authority'}
    with (directory/'review.json').open('x',encoding='utf8') as stream:json.dump(packet,stream,indent=2)
    return packet


def decide(directory, *, decision, reviewer):
    if decision not in ('approve','reject') or type(reviewer) is not str or not reviewer.strip() or len(reviewer)>120:
        raise ValueError('explicit decision and reviewer label required')
    directory=Path(directory)
    packet=json.loads((directory/'review.json').read_text(encoding='utf8'))
    if sha(packet['contract'])!=packet['contract_hash']:raise ValueError('contract changed')
    if set(packet['reviews'])!={'qa','security'} or any(r.get('accepted') is not True or r.get('hash')!=packet['artifact_hash'] for r in packet['reviews'].values()):
        raise PermissionError('review bindings changed')
    names=packet['files']
    if len(set(names))!=len(names) or any(Path(n).name!=n or not n.endswith('.py') for n in names):raise ValueError('flat Python manifest')
    folder=directory/'files'
    if folder.is_symlink() or any(p.is_symlink() or not p.is_file() for p in folder.iterdir()) or set(p.name for p in folder.iterdir())!=set(names):
        raise ValueError('delivery manifest changed')
    files={n:(folder/n).read_text(encoding='utf8') for n in names}
    if sha(files)!=packet['artifact_hash']:raise ValueError('artifact changed; new review required')
    result={'decision':decision,'reviewer':reviewer.strip(),'artifact_hash':packet['artifact_hash'],
            'contract_hash':packet['contract_hash'],'scope':packet['scope']}
    with (directory/'human-decision.json').open('x',encoding='utf8') as stream:json.dump(result,stream,indent=2)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('--decision',choices=('approve','reject'),required=True)
    parser.add_argument('--reviewer',required=True)
    args=parser.parse_args();print(json.dumps(decide(args.directory,decision=args.decision,reviewer=args.reviewer),indent=2))


if __name__=='__main__':main()
