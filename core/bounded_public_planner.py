"""Explicit paid-model BFS, not resonance-emergent planning or private answers.

Compiles a proposal from a public goal and queried consequences. Returns ONE
primitive action; execution/authority remain outside this planner. A plan is
discarded when its expected public state or contract identity no longer matches.
"""
import json
from collections import deque

def key(value):return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)

def select_primitive(problem, transition, cached=None):
    binding=key([problem["entity"],problem["revision"],problem["contract"],problem["goal"],problem["actions"]])
    state=problem["state"]
    if cached and cached["binding"]==binding and cached["route"] and cached["route"][0]["before"]==state:
        route=cached["route"]
        return route[0]["action"],{"binding":binding,"route":route[1:]},{"source":"paid_public_model","cache_hit":True,"queries":0}
    queue=deque([state]);parents={key(state):None};values={key(state):state};queries=0
    while queue:
        current=queue.popleft();identity=key(current)
        accepted=(current.get(problem['goal_field'])==problem['goal'] if problem.get('goal_field') else current==problem['goal'])
        if accepted:
            route=[]
            while parents[identity] is not None:
                prior,action=parents[identity]
                route.append({"before":values[prior],"action":action,"after":values[identity]})
                identity=prior
            route.reverse()
            if not route:return None,None,{"source":"paid_public_model","at_goal":True,"queries":queries}
            return route[0]["action"],{"binding":binding,"route":route[1:]},{"source":"paid_public_model","cache_hit":False,"queries":queries,"proposal_length":len(route)}
        for action in problem["actions"]:
            child=transition(current,action);queries+=1;child_id=key(child)
            if child_id not in parents:
                parents[child_id]=(identity,action);values[child_id]=child;queue.append(child)
    return None,None,{"source":"paid_public_model","exhausted_reachable_space":True,"queries":queries}
