"""Bounded context/action/consequence memory; verified receipts only."""
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class ActionContextTrace:
    context: tuple[float, ...]
    action: int
    reward: float
    evidence_id: str
    step: int

class ActionContextMemory:
    def __init__(self, threshold=.995, capacity=2048):
        self.threshold=threshold
        self.capacity=capacity
        self.traces=[]
        self.ids=set()

    def observe(self, context, action, reward, evidence_id, step, verified=False):
        values=tuple(float(x) for x in context)
        if (not verified or not evidence_id or evidence_id in self.ids or
            not all(math.isfinite(x) for x in values) or not math.isfinite(reward)):
            return False
        self.traces.append(ActionContextTrace(values,int(action),max(-1.,min(1.,float(reward))),
                                              evidence_id,int(step)))
        self.ids.add(evidence_id)
        if len(self.traces)>self.capacity:
            self.ids.remove(self.traces.pop(0).evidence_id)
        return True

    def predict(self, context, action):
        values=tuple(float(x) for x in context)
        norm=math.sqrt(sum(x*x for x in values))
        hits=[]
        for trace in self.traces:
            if trace.action!=action or len(trace.context)!=len(values):
                continue
            denominator=norm*math.sqrt(sum(x*x for x in trace.context))
            similarity=sum(a*b for a,b in zip(values,trace.context))/denominator if denominator else -1.
            if similarity>=self.threshold:
                hits.append((trace,similarity))
        if not hits:
            return {"support":0,"value":0.,"abstained":True,"evidence_ids":[],"last_reward":None}
        # Recent verified consequences displace stale associations after a regime change.
        hits=hits[-4:]
        weights=[similarity*(.5**(len(hits)-index-1)) for index,(_,similarity) in enumerate(hits)]
        value=sum(trace.reward*weight for (trace,_),weight in zip(hits,weights))/sum(weights)
        return {"support":len(hits),"value":value,"abstained":False,
                "evidence_ids":[trace.evidence_id for trace,_ in hits],
                "last_reward":hits[-1][0].reward}

def evidence_priority(prediction):
    """Preference for a diagnostic probe, never authorization for an action."""
    if prediction.get("abstained",True) or not prediction.get("support",0):
        return 0
    if prediction.get("last_reward",0)<=0:
        return -1
    return 1 if prediction.get("value",0)>=.5 else 0

def arbitrate_information_actions(candidates, systematic_unknown=False):
    """All legal probes remain available. No hidden label or score retuning."""
    priorities={candidate["action"]:evidence_priority(candidate["action_context"])
                for candidate in candidates}
    def key(candidate):
        priority=priorities[candidate["action"]]
        if systematic_unknown and priority==0:
            # Missing local evidence is not permission to trust a remote neighbour.
            return priority, 0., -candidate["action"]
        return priority, candidate["score"], -candidate["action"]
    selected=max(candidates,key=key)
    return selected,{"priorities":priorities,
                     "chosen_action":selected["action"],
                     "reason":"verified_action_context" if priorities[selected["action"]]>0 else
                              "unknown_context_exploration" if priorities[selected["action"]]==0 else
                              "contradicted_context_recheck"}
