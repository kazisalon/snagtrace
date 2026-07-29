"""Wire snagtrace into any LangChain or LangGraph agent via callbacks.

Requires: pip install snagtrace[langchain]
"""

from snagtrace import CostBudget, Doctor, LoopDetector
from snagtrace.adapters import SnagTraceCallbackHandler

doctor = Doctor(
    detectors=[
        LoopDetector(window=6, min_repeats=3),
        CostBudget(max_usd=5.00),
    ]
)
handler = SnagTraceCallbackHandler(doctor, agent_id="my_agent")

# agent_executor.invoke({"input": "..."}, config={"callbacks": [handler]})

result = handler.diagnose()
if not result.is_healthy:
    print(f"first fault: step {result.first_fault.step_id}, {result.first_fault.category}")
    print(result.first_fault.evidence)
