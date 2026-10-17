"""Host-owned phase metrics, independent of actor success declarations.

The observer reads metrics. A diagnosis is a proposal, never authority to patch
the motor, trim evidence or change a frozen campaign. No oracle required.
"""
import json
import math
import sqlite3
import statistics
import time

class Telemetry:
    def __init__(self,path):
        self.db=sqlite3.connect(path,timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('''CREATE TABLE IF NOT EXISTS phase_metrics(
            seq INTEGER PRIMARY KEY, episode TEXT NOT NULL, phase TEXT NOT NULL,
            milliseconds REAL NOT NULL, available_bytes INTEGER NOT NULL,
            checkpoint_bytes INTEGER NOT NULL, recorded_epoch REAL NOT NULL)''')
        self.db.execute('CREATE INDEX IF NOT EXISTS phase_window ON phase_metrics(phase,seq)');self.db.commit()
    def record_from_host(self,episode,phase,milliseconds,*,available_bytes,checkpoint_bytes):
        if type(episode) is not str or type(phase) is not str or not phase:
            raise ValueError('invalid metric identity')
        if not math.isfinite(milliseconds) or milliseconds<0:
            raise ValueError('invalid measured duration')
        if any(type(v) is not int or v<0 for v in (available_bytes,checkpoint_bytes)):
            raise ValueError('invalid metric resources')
        self.db.execute('INSERT INTO phase_metrics VALUES(NULL,?,?,?,?,?,?)',
            (episode,phase,milliseconds,available_bytes,checkpoint_bytes,time.time()));self.db.commit()
    def observation(self,phase,*,window=20,ratio=2.0):
        if type(window) is not int or not 5<=window<=1000 or not math.isfinite(ratio) or ratio<=1:
            raise ValueError('invalid observation window')
        first=[row[0] for row in self.db.execute('SELECT milliseconds FROM phase_metrics WHERE phase=? ORDER BY seq LIMIT ?',
            (phase,window))]
        recent=list(self.db.execute('''SELECT milliseconds,available_bytes,checkpoint_bytes
            FROM phase_metrics WHERE phase=? ORDER BY seq DESC LIMIT ?''',(phase,window)))
        if len(first)<window or self.db.execute('SELECT COUNT(*) FROM phase_metrics WHERE phase=?',(phase,)).fetchone()[0]<2*window:
            return {'state':'insufficient_evidence','phase':phase,'repair_authorized':False}
        baseline=statistics.median(first);current=statistics.median(row[0] for row in recent)
        return {'state':'degradation' if current>max(1.,baseline)*ratio else 'stable','phase':phase,
            'baseline_median_ms':baseline,'recent_median_ms':current,
            'ratio':current/max(1.,baseline),'available_bytes':recent[0][1],
            'checkpoint_bytes':recent[0][2],'repair_authorized':False,
            'scope':'observed phase degradation, not proof of root cause'}
    def close(self):self.db.close()
