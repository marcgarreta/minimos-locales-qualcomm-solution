"""Kangaroo Matrix: shows what the Kangaroo Path portal is doing on the LED matrix.

Two threads, no model calls:
- poll(): every 2 s reads http://<board>/api/board (counters only, no names) from the portal.
- animate(): builds the current frame at ~12 fps; the sketch asks for it with Bridge.call("frame").

Rotation: Wi-Fi devices, students online, missions handed in today, the class "equaliser"
(average level per topic), today's accuracy, problem bank, and the hopping kangaroo.
Events (a mission handed in, a student logging in, a new student or problem) interrupt it
with a short animation. If the portal doesn't answer, a sad face breathes slowly.
"""
import json
import socket
import struct
import threading
import time
import urllib.request

from arduino.app_utils import App, Bridge

import scenes

PORT = 80
HOST_HEADER = "192.168.4.1"      # the portal redirects other Host names (captive portal)

state = {"data": None, "ok": False, "since_ok": None, "base": None, "frame": scenes.encode(scenes.blank())}
queue = []                        # pending event animations: (render, seconds)
lock = threading.Lock()


def default_gateway():
    """The Docker host as seen from the app's container (first default route)."""
    try:
        with open("/proc/net/route") as f:
            for line in f.readlines()[1:]:
                parts = line.split()
                if parts[1] == "00000000":
                    return socket.inet_ntoa(struct.pack("<L", int(parts[2], 16)))
    except (OSError, IndexError, ValueError):
        pass
    return None


def candidates():
    seen = []
    for host in (state["base"], "127.0.0.1", default_gateway(), "172.17.0.1", "192.168.4.1"):
        if host and host not in seen:
            seen.append(host)
    return seen


def fetch(host):
    req = urllib.request.Request(f"http://{host}:{PORT}/api/board", headers={"Host": HOST_HEADER})
    with urllib.request.urlopen(req, timeout=2) as r:
        return json.loads(r.read())


def poll():
    last_seq = None
    while True:
        data = None
        for host in candidates():
            try:
                data = fetch(host)
                if state["base"] != host:
                    print(f"portal found at {host}:{PORT}", flush=True)
                state["base"] = host
                break
            except (OSError, ValueError):
                continue
        with lock:
            state["ok"] = data is not None
            if data:
                state["data"] = data
                seq = data.get("event_seq", 0)
                if last_seq is not None and seq > last_seq:     # only events that happen while we watch
                    for ev in data.get("events", []):
                        if ev["seq"] > last_seq:
                            queue.extend(scenes.event_animation(ev))
                last_seq = seq
        time.sleep(2)


def animate():
    scene_i, scene_t0 = 0, time.time()
    current, cur_t0 = None, 0.0
    started = time.time()
    while True:
        now = time.time()
        with lock:
            ok, data = state["ok"], state["data"] or {}
            if current is None and queue:
                current, cur_t0 = queue.pop(0), now
        if current:
            render, secs = current
            frame = render(now - cur_t0)
            if now - cur_t0 >= secs:
                current = None
                scene_t0 = now                     # restart the rotation's timer after an event
        elif not ok:
            frame = scenes.booting(now - started, data, 0) if now - started < 20 else scenes.offline(now, data, 0)
        else:
            fn, secs = scenes.ROTATION[scene_i]
            if fn is scenes.accuracy and data.get("accuracy_today") is None:
                scene_i, scene_t0 = (scene_i + 1) % len(scenes.ROTATION), now
                continue
            frame = fn(now - scene_t0, data, secs)
            if now - scene_t0 >= secs:
                scene_i, scene_t0 = (scene_i + 1) % len(scenes.ROTATION), now
        state["frame"] = scenes.encode(frame)
        time.sleep(0.08)


served = {"n": 0}


def get_frame():
    served["n"] += 1
    if served["n"] in (1, 100) or served["n"] % 15000 == 0:     # first one, then about every 10 minutes
        print(f"matrix: {served['n']} frames sent to the sketch", flush=True)
    return state["frame"]


Bridge.provide("frame", get_frame)
threading.Thread(target=poll, daemon=True).start()
threading.Thread(target=animate, daemon=True).start()
App.run()
