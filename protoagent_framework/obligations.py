"""Generic public-goal dependency frontier; predictions are not proof.

Operators describe public prerequisites and possible effects. The planner
does not inspect a domain oracle, synthesize a patch or execute an operation.
`may_add` is explicitly uncertain; only fresh host facts satisfy an obligation.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class Operator:
    action:int
    requires:frozenset[str]
    adds:frozenset[str]=frozenset()
    may_add:frozenset[str]=frozenset()

def frontier(goals,facts,operators):
    if not isinstance(facts,dict) or any(type(value) is not bool for value in facts.values()):
        raise ValueError('facts must be explicit booleans')
    if len(operators)>256 or len(goals)>256:raise ValueError('planning resource bound')
    if len({op.action for op in operators})!=len(operators):raise ValueError('duplicate operator identity')
    candidates={};missing=set();cycles=set()
    def visit(goal,path):
        if facts.get(goal,False):return
        if goal in path:cycles.add(goal);return
        producers=[op for op in operators if goal in op.adds or goal in op.may_add]
        if not producers:missing.add(goal);return
        for op in producers:
            unmet=[item for item in sorted(op.requires) if not facts.get(item,False)]
            if unmet:
                for item in unmet:visit(item,path+(goal,))
            else:
                row=candidates.setdefault(op.action,{'action':op.action,'obligations':set(),'uncertain':False})
                row['obligations'].add(goal);row['uncertain']|=goal in op.may_add
    for goal in sorted(set(goals)):visit(goal,())
    return {'satisfied':all(facts.get(goal,False) for goal in goals),
        'ready':[{'action':row['action'],'obligations':sorted(row['obligations']),'uncertain':row['uncertain']}
            for action,row in sorted(candidates.items())],
        'missing_capabilities':sorted(missing),'cycles':sorted(cycles),
        'scope':'possible next operations, not a completion or authority verdict'}
