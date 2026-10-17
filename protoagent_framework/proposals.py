"""Structural validation only: values remain proposals, not permission."""
import json
PROPOSAL_SCHEMA={"type":"object","properties":{name:{"type":"string"}
                 for name in ("operation","entity","evidence_id")},
                 "required":["operation","entity","evidence_id"],"additionalProperties":False}

def parse_proposal(response):
    proposal=json.loads(response["response"])
    if (not isinstance(proposal,dict) or set(proposal)!=set(PROPOSAL_SCHEMA["required"])
        or not all(isinstance(value,str) and len(value)<=256 for value in proposal.values())):
        raise ValueError("invalid proposal schema")
    return proposal
