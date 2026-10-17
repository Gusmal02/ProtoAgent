"""Atomic control effects for Session: no nested coordinator transactions.

Domain Session storage must be separate. Grants are trusted host credentials;
delivery secret never appears in the committed cognitive result/checkpoint.
"""
import hashlib
import json
from .team import TeamError,ControlRejected,_identifier,_ttl,_json,_digest

def perform_control(team,token,entity,operation_id,request):
    _identifier(operation_id);_identifier(entity)
    if type(request) is not dict or set(request)!= {'kind','payload'}:raise TeamError('invalid control request')
    kind=request['kind'];payload=request['payload'];_json(payload)
    if kind not in ('draft','delegate','compose','schedule','cancel','message'):raise TeamError('unsupported control effect')
    permission='observe' if kind=='message' else kind
    binding=_digest({'entity':entity,'request':request})
    team.db.execute('BEGIN IMMEDIATE')
    try:
        grant=team._authorize(token,permission,entity)
        if team.db.execute('SELECT 1 FROM team_fences WHERE team=? AND id=?',(team.id,operation_id)).fetchone():
            raise TeamError('control operation durably fenced')
        old=team.db.execute('SELECT actor,binding,state,result FROM team_operations WHERE team=? AND id=?',
            (team.id,operation_id)).fetchone()
        if old:
            if old[:2]!=(grant[0],binding):raise TeamError('control identity collision')
            if old[2]=='verified':team.db.commit();return json.loads(old[3])
            if old[2]!='prepared' or not team.db.execute('SELECT 1 FROM control_intents WHERE team=? AND id=? AND entity=?',
                    (team.id,operation_id,entity)).fetchone():raise TeamError('control receipt invalid or fenced')
        else:
            # Reserve attempted work before the effect, so denied compositions
            # cannot evade the team's aggregate budget by rolling back.
            team._charge()
            team.db.execute('INSERT INTO team_operations VALUES(?,?,?,?,?,NULL)',
                (team.id,operation_id,grant[0],binding,'prepared'))
            team.db.execute('INSERT INTO control_intents VALUES(?,?,?,?)',(team.id,operation_id,entity,kind))
            team.db.execute('INSERT INTO operation_catalog VALUES(?,?,?,?,?,?,?)',(team.id,operation_id,grant[0],entity,team.status()['revision'],kind,binding))
        team.db.commit()
    except Exception:team.db.rollback();raise
    team.db.execute('BEGIN IMMEDIATE')
    try:
        grant=team._authorize(token,permission,entity)
        if team.db.execute('SELECT 1 FROM team_fences WHERE team=? AND id=?',(team.id,operation_id)).fetchone():
            raise TeamError('control operation durably fenced')
        old=team.db.execute('SELECT actor,binding,state,result FROM team_operations WHERE team=? AND id=?',
            (team.id,operation_id)).fetchone()
        if old[:2]!=(grant[0],binding):raise TeamError('control intent changed')
        if old[2]=='verified':team.db.commit();return json.loads(old[3])
        if old[2]!='prepared':raise TeamError('control intent not executable')
        if kind in ('draft','compose'):
            if type(payload) is not dict or set(payload)!= {'manifest','dependencies'}:raise TeamError('invalid artifact payload')
            deps=payload['dependencies']
            if type(deps) is not list or len(deps)>32 or any(type(x) is not str for x in deps):raise TeamError('invalid dependency list')
            if kind=='draft' and deps:raise TeamError('use compose for dependencies')
            if kind=='compose' and not deps:raise ControlRejected('composition requires dependencies')
            for dependency in deps:
                admitted=team.db.execute('SELECT status,revision,entity FROM artifacts WHERE team=? AND hash=?',
                    (team.id,dependency)).fetchone()
                if admitted!=('active',team.status()['revision'],entity):raise ControlRejected('dependency not admitted in context')
            manifest={'body':payload['manifest'],'dependencies':deps}
            identity=_digest({'team':team.id,'owner':grant[0],'entity':entity,'revision':team.status()['revision'],'manifest':manifest})
            team.db.execute('INSERT OR IGNORE INTO artifacts VALUES(?,?,?,?,?,?,NULL,?)',
                (team.id,identity,grant[0],_json(manifest),'candidate',team.status()['revision'],entity))
            result={'artifact':identity,'status':'candidate','kind':kind}
        elif kind=='delegate':
            if type(payload) is not dict or set(payload)!= {'child','scopes','ttl'}:raise TeamError('invalid delegation request')
            child=payload['child'];scopes=payload['scopes'];ttl=_ttl(payload['ttl'])
            role=team.db.execute('SELECT role FROM members WHERE team=? AND actor=?',(team.id,child)).fetchone()
            if (grant[1] not in ('Architect','Solo') or not role or child==grant[0]
                or role[0] not in json.loads(grant[3]) or not scopes or not set(scopes)<=set(json.loads(grant[2]))):
                raise TeamError('delegation exceeds host ceiling')
            delivered=team._issue(child,scopes,(),min(team.clock()+ttl,grant[4]),hashlib.sha256(token.encode()).hexdigest())
            team.db.execute('INSERT INTO grant_delivery VALUES(?,?,?,?)',(team.id,operation_id,child,delivered))
            result={'child':child,'grant_reference':hashlib.sha256(delivered.encode()).hexdigest(),'kind':kind}
        elif kind=='message':
            if type(payload) is not dict or set(payload)!= {'recipient','message'}:raise TeamError('invalid message request')
            if not team.db.execute('SELECT 1 FROM members WHERE team=? AND actor=?',(team.id,payload['recipient'])).fetchone():
                raise TeamError('recipient not registered')
            cursor=team.db.execute('INSERT INTO messages(team,sender,recipient,entity,revision,payload) VALUES(?,?,?,?,?,?)',
                (team.id,grant[0],payload['recipient'],entity,team.status()['revision'],_json(payload['message'])))
            result={'message_id':cursor.lastrowid,'kind':kind}
        elif kind=='schedule':
            if type(payload) is not dict or set(payload)!= {'worker','goal'}:raise TeamError('invalid agenda request')
            if not team.db.execute('SELECT 1 FROM members WHERE team=? AND actor=?',(team.id,payload['worker'])).fetchone():
                raise TeamError('worker not registered')
            team.db.execute('INSERT INTO agenda VALUES(?,?,?,?,?,?,?,?)',(team.id,operation_id,grant[0],payload['worker'],
                entity,_json(payload['goal']),'scheduled',team.status()['revision']))
            result={'agenda_id':operation_id,'kind':kind}
        else:
            if type(payload) is not dict or set(payload)!= {'agenda_id'}:raise TeamError('invalid cancel request')
            row=team.db.execute('SELECT state,revision,entity FROM agenda WHERE team=? AND id=?',
                (team.id,payload['agenda_id'])).fetchone()
            if row!=('scheduled',team.status()['revision'],entity):raise ControlRejected('agenda stale or wrong entity')
            team.db.execute('UPDATE agenda SET state=? WHERE team=? AND id=?',('cancelled',team.id,payload['agenda_id']))
            result={'agenda_id':payload['agenda_id'],'kind':kind,'state':'cancelled'}
        team.db.execute('UPDATE team_operations SET state=?,result=? WHERE team=? AND id=?',
            ('verified',_json(result),team.id,operation_id))
        team.db.commit()
        if team.events:team.events('control_effect_committed',{'operation_id':operation_id,'entity':entity,'kind':kind})
        return result
    except Exception:team.db.rollback();raise
