"""Persistent analysis state: avoids inventing a new action on every invocation."""
from dataclasses import asdict, dataclass
from pathlib import Path
import json

@dataclass
class AnalysisState:
    symbol:str
    regime:str|None=None
    action:str|None=None
    t_action:str|None=None
    score:int|None=None
    support:float|None=None
    resistance:float|None=None
    data_time:str|None=None
    risk_active:bool=False
    risk_reference_level:float|None=None
    risk_reference_type:str|None=None
    risk_invalidation_level:float|None=None
    risk_status:str|None=None

class StateStore:
    def __init__(self,path=".astock_state.json"):
        self.path=Path(path)
    def load_all(self):
        if not self.path.exists(): return {}
        try: return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception: return {}
    def get(self,symbol):
        d=self.load_all().get(str(symbol))
        return AnalysisState(**d) if d else None
    def put(self,state):
        d=self.load_all(); d[state.symbol]=asdict(state)
        self.path.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")

def materially_changed(prev,current,score_delta=5):
    if prev is None: return True
    if prev.regime!=current["regime"] or prev.action!=current["action"] or prev.t_action!=current.get("t_action"): return True
    if prev.risk_active!=current.get("risk_active",False) or prev.risk_status!=current.get("risk_status"): return True
    if (prev.risk_reference_level!=current.get("structural_reference_level")
            or prev.risk_invalidation_level!=current.get("structural_invalidation_level")): return True
    return abs((prev.score or 0)-current["score"])>=score_delta
