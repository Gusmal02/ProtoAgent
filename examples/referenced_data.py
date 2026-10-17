"""Second domain: a trusted local data-quality report, base SDK only."""
import argparse,json
from pathlib import Path
from protoagent_framework import MemoryStore,NativeToolStore,ToolRequest,ToolResult

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',required=True);args=parser.parse_args()
    root=Path(args.workspace);root.mkdir(parents=True,exist_ok=False)
    memory=MemoryStore(root/'memory.sqlite');effects=NativeToolStore(root/'reports.sqlite',initialize=lambda db:db.execute('CREATE TABLE reports(value TEXT)'))
    try:
        rows=[{'id':1,'amount':3},{'id':2,'amount':7}]
        reference=memory.put({'columns':['id','amount'],'row_count':len(rows)},entity='synthetic-data',revision=0)
        report=memory.resolve(reference,entity='synthetic-data',revision=0)
        request=ToolRequest('record-report','synthetic-data',0,{'reference':reference.to_dict()})
        def record(db,req):
            db.execute('INSERT INTO reports VALUES(?)',(json.dumps(report),))
            return ToolResult((1,1,0),evidence={'recorded':True,'at_goal':True})
        for _ in range(2):effects.execute('report-1',request,mutate=record,authorize=lambda db,r:r.entity=='synthetic-data' and r.revision==0)
        assert effects.read('SELECT count(*) FROM reports')==[(1,)]
        print(json.dumps({'report':report,'stored_once':True,'authority_from_memory':False}))
    finally:effects.close();memory.close()

if __name__=='__main__':main()
