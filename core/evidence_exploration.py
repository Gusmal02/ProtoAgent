"""Optional exploration after unrewarded stagnation, never an authority grant.

Actual attempt counts are not k-nearest-neighbor support. The chooser receives
legal candidate IDs only; it never receives task targets, routes or distances.
"""
def select_underexplored(candidates, attempts, stagnation, *, after=8, choose_index, no_change_evidence=None):
    if not candidates or stagnation < after:
        return None, {"triggered":False,"cause":"insufficient_stagnation"}
    evidence=no_change_evidence or {}
    # A reversible preference, not a permanent prohibition. After eight actual
    # no-change observations, sample that action at 1/8 the frequency. Unknown
    # actions and changing actions retain full exploration opportunity.
    effective=lambda c:attempts.get(c["action"],0)*(8 if evidence.get(c["action"],0)>=8 else 1)
    minimum=min(effective(c) for c in candidates)
    pool=[c for c in candidates if effective(c)==minimum]
    index=choose_index(len(pool))
    if type(index) is not int or not 0<=index<len(pool):raise ValueError("invalid tie index")
    chosen=pool[index]
    return chosen,{"triggered":True,"cause":"unrewarded_stagnation",
                   "minimum_actual_attempts":minimum,"tied_candidates":len(pool),
                   "chosen_action":chosen["action"],"no_solution_information":True}
