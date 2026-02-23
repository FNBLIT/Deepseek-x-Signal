#!/usr/bin/env python3
import time, requests, os
from dotenv import load_dotenv

load_dotenv()
SIGNAL_PHONE_NUMBER_TO_SEND_FROM = os.getenv("SIGNAL_PHONE_NUMBER_TO_SEND_FROM")
daemon_rpc_url = "http://localhost:11535/api/v1/rpc"
daemon_headers = {"Content-Type": "application/json"}

def log_debug(msg):
    print(f"[DEBUG {time.strftime('%H:%M:%S')}] {msg}")

def raise_exception_if_signal_cli_daemon_is_down():
    try:
        r = requests.get("http://localhost:11535/api/v1/check", timeout=5)
        if r.status_code == 200: return
    except: pass
    raise ConnectionError("Signal CLI daemon is offline.")

def send_signal_message(message, recipient_number=None, group_id=None):
    params = {"message": message}
    if group_id: params["groupId"] = group_id
    else: params["recipient"] = [recipient_number]
    payload = {"jsonrpc": "2.0", "method": "send", "params": params, "id": int(time.time()*1000)}
    requests.post(daemon_rpc_url, json=payload, headers=daemon_headers)

def _send_typing(recipient_number, group_id, stop=False):
    params = {"stop": stop}
    if group_id: params["groupId"] = group_id
    else: params["recipient"] = [recipient_number]
    payload = {"jsonrpc": "2.0", "method": "sendTyping", "params": params, "id": int(time.time()*1000)}
    requests.post(daemon_rpc_url, json=payload, headers=daemon_headers)

def send_signal_typing_indicator_start(recipient_number=None, group_id=None):
    _send_typing(recipient_number, group_id, stop=False)

def send_signal_typing_indicator_stop(recipient_number=None, group_id=None):
    _send_typing(recipient_number, group_id, stop=True)

def send_signal_read_receipt(timestamps, sender, group_id):
    params = {"recipient": [sender], "targetSentTimestamp": timestamps}
    if group_id: params["groupId"] = group_id
    payload = {"jsonrpc": "2.0", "method": "sendReadReceipt", "params": params, "id": int(time.time()*1000)}
    requests.post(daemon_rpc_url, json=payload, headers=daemon_headers)

def receive_signal_messages():
    payload = {"jsonrpc": "2.0", "method": "receive", "params": {}, "id": int(time.time()*1000)}
    try:
        r = requests.post(daemon_rpc_url, json=payload, headers=daemon_headers)
        results = r.json().get("result", [])
        parsed = []
        for item in results:
            env = item.get("envelope", {})
            dm = env.get("dataMessage", {})
            if not dm.get("message"): continue
            parsed.append({
                "message": dm["message"],
                "timestamp": dm["timestamp"],
                "source": env.get("sourceNumber") or env.get("source"),
                "groupId": (dm.get("groupInfo") or {}).get("groupId"),
                "mentions": dm.get("mentions", []),
                "quote_author": (dm.get("quote") or {}).get("authorNumber")
            })
        return parsed
    except: return []

def poll_for_incoming_messages(handler, thread):
    for msg in receive_signal_messages():
        handler(msg["message"], [msg["timestamp"]], thread, msg["source"], msg["groupId"], msg["mentions"], msg["quote_author"])
