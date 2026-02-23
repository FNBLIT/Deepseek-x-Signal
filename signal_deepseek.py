#!/usr/bin/env python3
import time, threading, queue, os
from dotenv import load_dotenv
from signal_jsonrpc import *
from ollama_chat import (
    generate_system_message,
    get_chat_completion,
    set_global_prompt,
    save_current_prompt_to_env,
    is_prompt_saved,
    current_system_prompt,
    DEEPSEEK_MODEL,
    PRESETS
)

load_dotenv()
BOT_NUMBER = os.getenv("SIGNAL_PHONE_NUMBER_TO_SEND_FROM")
task_queue = queue.Queue()
sessions = {}
worker_busy = False

# --- Worker Thread (Remains same) ---
def worker():
    global worker_busy
    while True:
        task = task_queue.get()
        sender, group_id, message, timestamps, stop_waiting = task
        worker_busy = True
        stop_waiting.set()

        session_key = group_id if group_id else sender
        if session_key not in sessions:
            sessions[session_key] = generate_system_message()

        stop_active = threading.Event()
        def typing():
            while not stop_active.is_set():
                send_signal_typing_indicator_start(sender, group_id); time.sleep(4)
        threading.Thread(target=typing, daemon=True).start()

        try:
            get_chat_completion(message, sessions[session_key])
            send_signal_message(sessions[session_key][-1]["content"], sender, group_id)
        finally:
            stop_active.set()
            send_signal_typing_indicator_stop(sender, group_id)
            worker_busy = False
            task_queue.task_done()

threading.Thread(target=worker, daemon=True).start()

# --- Handler with Pre-emption Logic ---
def handle_incoming_messages(message, timestamps, _, sender, group_id, mentions, quote_author):
    is_dm = group_id is None
    is_mention = any(m.get('number') == BOT_NUMBER for m in (mentions or []))
    is_reply = (quote_author == BOT_NUMBER)

    if not (is_dm or is_mention or is_reply):
        return

    msg_clean = message.strip()
    msg_lower = msg_clean.lower()
    session_key = group_id if group_id else sender

    # 1. COMMAND: /help
    if msg_lower == "/help":
        help_text = "🤖 *Bot Commands:*\n\n🔹 `/who` - Current persona\n🔹 `/prompt [text]` - Change persona\n🔹 `/reset [preset]` - Wipe history\n🔹 `/save` - Save to disk"
        send_signal_message(help_text, sender, group_id)
        return  # <--- CRITICAL: Stop here so LLM never sees this!

    # 2. COMMAND: /who
    if msg_lower == "/who":
        from ollama_chat import current_system_prompt
        status = "✅ Saved" if is_prompt_saved() else "⚠️ Unsaved"
        who_text = f"🧠 *Brain:* {DEEPSEEK_MODEL}\n🎭 *Persona:* {current_system_prompt}\n💾 *Status:* {status}"
        send_signal_message(who_text, sender, group_id)
        return  # <--- CRITICAL

    # 3. COMMAND: /save
    if msg_lower == "/save":
        result = save_current_prompt_to_env()
        send_signal_message(result, sender, group_id)
        return  # <--- CRITICAL

    # 4. COMMAND: /prompt
    if msg_lower.startswith("/prompt "):
        new_instruction = msg_clean[8:].strip()
        set_global_prompt(new_instruction)
        sessions[session_key] = generate_system_message(new_instruction)
        send_signal_message(f"✍️ Persona updated to: \"{new_instruction}\"", sender, group_id)
        return  # <--- CRITICAL

    # 5. COMMAND: /reset
    if msg_lower.startswith("/reset"):
        parts = msg_lower.split()
        preset_name = parts[1] if len(parts) > 1 else None
        if preset_name in PRESETS:
            new_p = PRESETS[preset_name]
            set_global_prompt(new_p)
            sessions[session_key] = generate_system_message(new_p)
            resp = f"🎭 Switched to: {preset_name.upper()}"
        else:
            sessions[session_key] = generate_system_message()
            resp = "📜 History cleared."
        send_signal_message(resp, sender, group_id)
        return  # <--- CRITICAL

    # --- IF NO COMMANDS MATCH, PROCEED TO LLM ---
    send_signal_read_receipt(timestamps, sender, group_id)
    stop_waiting = threading.Event()
    def wait_typing():
        while not stop_waiting.is_set():
            send_signal_typing_indicator_start(sender, group_id); time.sleep(4)
    threading.Thread(target=wait_typing, daemon=True).start()

    task_queue.put((sender, group_id, message, timestamps, stop_waiting))

if __name__ == "__main__":
    raise_exception_if_signal_cli_daemon_is_down()
    while True:
        poll_for_incoming_messages(handle_incoming_messages, None)
        time.sleep(1)
