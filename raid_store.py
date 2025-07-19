import random
from datetime import datetime

raid_store = {}

def gen_raid_id():
    while True:
        rid = f"{random.randint(100000, 999999)}"
        if rid not in raid_store:
            return rid

def add_raid(time_text, scheduled_dt):
    rid = gen_raid_id()
    raid_store[rid] = {
        "time_text": time_text,
        "scheduled_dt": scheduled_dt,
        "max_members": 8,
        "members": set(),
        "log": [("생성", time_text)]
    }
    return rid

def update_raid(rid, **kwargs):
    raid = raid_store.get(rid)
    if not raid:
        return False
    if "max_members" in kwargs:
        raid["max_members"] = min(max(1, kwargs["max_members"]), 8)
        raid["log"].append(("인원 변경", f"{raid['max_members']}명"))
    if "time_text" in kwargs and "scheduled_dt" in kwargs:
        raid["time_text"] = kwargs["time_text"]
        raid["scheduled_dt"] = kwargs["scheduled_dt"]
        raid["log"].append(("시간 변경", raid["time_text"]))
    return True

def delete_raid(rid):
    return raid_store.pop(rid, None) is not None
