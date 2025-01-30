from typing import Annotated, Any, Dict, Sequence, TypedDict

import operator
from langchain_core.messages import BaseMessage


import json


def merge_dicts(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    return {**a, **b}

# Define agent state
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    data: Annotated[Dict[str, Any], merge_dicts]
    metadata: Annotated[Dict[str, Any], merge_dicts]



def show_agent_reasoning(result, agent_name):
    """Display agent reasoning in a consistent format"""
    print(f"\n==========  {agent_name}  ==========")
    print(json.dumps(result, indent=2))
    print("=" * 48)