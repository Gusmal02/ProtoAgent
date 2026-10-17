"""Atomic typed delivery/ACK public implementation, never self-admission."""
import json
from .team import TeamError,_digest,_json,_identifier

ALLOWED={'request':{'schedule'},'produced':{'draft','compose'},'checked':{'challenge'},'result':{'execute'},'observation':{'observe','probe','message'}}

def publish(team,token,entity,delivery_id,recipient,origin,kind,payload):
    for value in (delivery_id,recipient,origin):_identifier(value)
    if kind not in ALLOWED:raise TeamError('delivery type')
    _json(payload);team.db.execute('BEGIN IMMEDIATE')
    try:
        grant=team._authorize(token,'observe',entity);revision=team.status()['revision']
        row=team.db.execute('SELECT actor,entity,revision,kind,binding FROM operation_catalog WHERE team=? AND id=?',(team.id,origin)).fetchone()
        receipt=team.db.execute('SELECT actor,binding,state,result FROM team_operations WHERE team=? AND id=?',(team.id,origin)).fetchone()
        if not row or row[:3]!=(grant[0],entity,revision) or row[3] not in ALLOWED[kind] or not receipt or receipt[:3]!=(row[0],row[4],'verified'):raise TeamError('verified operation origin required')
        if not team.db.execute('SELECT 1 FROM members WHERE team=? AND actor=?',(team.id,recipient)).fetchone():raise TeamError('recipient not registered')
        if kind=='produced':
            result=json.loads(receipt[3]);artifact=result.get('artifact') if isinstance(result,dict) else None
            if not artifact or payload.get('artifact')!=artifact:raise TeamError('artifact does not belong to origin')
        envelope={'schema':1,'delivery_id':delivery_id,'origin':origin,'type':kind,'entity':entity,'revision':revision,'actor':grant[0],'role':grant[1],'operation_kind':row[3],'data':payload}
        binding=_digest([grant[0],recipient,envelope])
        old=team.db.execute('SELECT binding,seq FROM durable_deliveries WHERE team=? AND id=?',(team.id,delivery_id)).fetchone()
        if old:
            if old[0]!=binding:raise TeamError('delivery identity collision')
            team.db.commit();return old[1]
        team._charge()
        cursor=team.db.execute('INSERT INTO messages(team,sender,recipient,entity,revision,payload) VALUES(?,?,?,?,?,?)',(team.id,grant[0],recipient,entity,revision,_json(envelope)))
        team.db.execute('INSERT INTO durable_deliveries VALUES(?,?,?,?,?,?)',(team.id,delivery_id,binding,cursor.lastrowid,origin,recipient));team.db.commit()
    except BaseException:team.db.rollback();raise
    if team.events:team.events('delivery_published',{'delivery_id':delivery_id,'seq':cursor.lastrowid,'entity':entity,'origin':origin})
    return cursor.lastrowid

def acknowledge(team,token,entity,seq):
    team.db.execute('BEGIN IMMEDIATE')
    try:
        grant=team._authorize(token,'observe',entity)
        row=team.db.execute('SELECT m.recipient,m.entity,m.revision,m.payload FROM messages m JOIN durable_deliveries d ON d.seq=m.seq AND d.team=m.team WHERE m.team=? AND m.seq=?',(team.id,seq)).fetchone()
        if not row or row[:3]!=(grant[0],entity,team.status()['revision']):raise TeamError('delivery recipient/entity/revision mismatch')
        digest=_digest(json.loads(row[3]));old=team.db.execute('SELECT digest FROM delivery_acks WHERE team=? AND actor=? AND seq=?',(team.id,grant[0],seq)).fetchone()
        if old and old[0]!=digest:raise TeamError('delivery changed after ack')
        team.db.execute('INSERT OR IGNORE INTO delivery_acks VALUES(?,?,?,?)',(team.id,grant[0],seq,digest));team.db.commit()
    except BaseException:team.db.rollback();raise
    if team.events:team.events('delivery_acknowledged',{'seq':seq,'actor':grant[0],'entity':entity})
    return {'seq':seq,'actor':grant[0],'entity':entity,'revision':row[2],'data':json.loads(row[3]),'admitted':False,'duplicate':old is not None}
