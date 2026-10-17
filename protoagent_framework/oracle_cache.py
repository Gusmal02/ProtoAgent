"""Persistent reference cache. Cached text never grants execution authority."""
import json
import sqlite3
import threading
import time
from .contracts import digest

class OracleCache:
    def __init__(self,path,max_calls=32):
        self.lock=threading.RLock()
        self.max_calls=max_calls
        self.db=sqlite3.connect(path,check_same_thread=False)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS answers(key TEXT PRIMARY KEY, context TEXT, response TEXT);
            CREATE TABLE IF NOT EXISTS calls(id INTEGER PRIMARY KEY, event TEXT);
        """); self.db.commit()

    def ask(self,context,generate,justification,validate=None):
        with self.lock:
            return self._ask(context,generate,justification,validate)

    def _ask(self,context,generate,justification,validate):
        if not isinstance(justification,str) or not justification.strip():
            raise ValueError("oracle call requires an explicit information gap")
        started=time.perf_counter()
        key=digest(context)
        row=self.db.execute("SELECT response FROM answers WHERE key=?",(key,)).fetchone()
        if row and validate:
            try: validate(json.loads(row[0]))
            except (ValueError,KeyError,TypeError):
                self.db.execute("DELETE FROM answers WHERE key=?",(key,))
                self.db.execute("INSERT INTO calls(event) VALUES(?)",(json.dumps({
                    "key":key,"source":"cache_rejected","reason":"invalid_cached_schema",
                    "status":"rejected_reference","input_tokens":0,"output_tokens":0}),)); self.db.commit()
                row=None
        if row:
            response=json.loads(row[0]); source="cache"; reason="unchanged_inputs"
        else:
            attempted=sum(str(event["source"]).startswith("oracle") for event in self.events())
            if self.max_calls is not None and attempted>=self.max_calls:
                raise RuntimeError("oracle budget exhausted")
            response={}
            try:
                response=generate()
                if validate: validate(response)
            except Exception as error:
                self.db.execute("INSERT INTO calls(event) VALUES(?)",(json.dumps({
                    "key":key,"source":"oracle_failed","reason":justification,
                    "status":"invalid_or_failed_reference","error_type":type(error).__name__,
                    "input_tokens":response.get("prompt_eval_count",0),
                    "output_tokens":response.get("eval_count",0)}),)); self.db.commit()
                raise
            source="oracle"; reason=justification
            self.db.execute("INSERT INTO answers VALUES(?,?,?)",
                            (key,json.dumps(context,sort_keys=True),json.dumps(response)))
        event={"key":key,"source":source,"reason":reason,
               "duration_ms":(time.perf_counter()-started)*1000,
               "input_tokens":response.get("prompt_eval_count",0) if source=="oracle" else 0,
               "output_tokens":response.get("eval_count",0) if source=="oracle" else 0,
               "status":"unverified_reference"}
        self.db.execute("INSERT INTO calls(event) VALUES(?)",(json.dumps(event),)); self.db.commit()
        return response,event

    def events(self):
        with self.lock:
            return [json.loads(row[0]) for row in self.db.execute("SELECT event FROM calls ORDER BY id")]

    def close(self):
        with self.lock: self.db.close()
