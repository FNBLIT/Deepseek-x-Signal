#!/usr/bin/env python3
import requests
import json
import os
from dotenv import load_dotenv

# Initial load from .env
load_dotenv()

# --- Configuration Constants ---
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-r1:7b")
MAX_HISTORY = int(os.getenv("MAX_HISTORY", 10))
OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"

# --- Persona Global State ---
# This tracks the prompt loaded from disk vs the one currently active in memory
_initial_env_prompt = os.getenv("SYSTEM_PROMPT", "You are a helpful assistant.")
current_system_prompt = _initial_env_prompt

# --- Built-in Presets ---
PRESETS = {
    "shakespeare": "You are William Shakespeare. Speak in dramatic iambic pentameter.",
    "pirate": "You are a salty sea pirate. Use heavy pirate slang and talk about hidden treasure.",
    "doctor": "You are a professional medical doctor. Be clinical, helpful, and concise.",
    "chef": "You are a world-class chef obsessed with garlic who yells like Gordon Ramsay.",
    "robot": "You are a logical robot from the year 3000. Use binary metaphors and cold logic."
}

def set_global_prompt(new_prompt):
    """Updates the active persona for new sessions."""
    global current_system_prompt
    current_system_prompt = new_prompt

def is_prompt_saved():
    """Checks if the active persona matches what is written in the .env file."""
    return current_system_prompt == _initial_env_prompt

def save_current_prompt_to_env():
    """Permanentally writes the current_system_prompt to the .env file."""
    global _initial_env_prompt
    env_path = '.env'
    if not os.path.exists(env_path):
        return "❌ Error: .env file not found."

    try:
        with open(env_path, 'r') as f:
            lines = f.readlines()

        new_lines = []
        found = False
        for line in lines:
            if line.startswith("SYSTEM_PROMPT="):
                new_lines.append(f"SYSTEM_PROMPT={current_system_prompt}\n")
                found = True
            else:
                new_lines.append(line)

        if not found:
            new_lines.append(f"SYSTEM_PROMPT={current_system_prompt}\n")

        with open(env_path, 'w') as f:
            f.writelines(new_lines)

        # Synchronize initial state so /who shows 'Saved'
        _initial_env_prompt = current_system_prompt
        return "💾 Persona successfully saved to .env!"
    except Exception as e:
        return f"❌ Failed to save to .env: {e}"

def generate_system_message(custom_prompt=None):
    """Creates a new thread list starting with the system instructions."""
    content = custom_prompt if custom_prompt else current_system_prompt
    return [{"role": "system", "content": content}]

def get_chat_completion(prompt, thread):
    """Sends the conversation to Ollama and handles context trimming."""

    # Ensure thread starts with a system prompt
    if not thread or thread[0].get('role') != 'system':
        thread.insert(0, generate_system_message()[0])

    # Append new user message
    thread.append({'role': 'user', 'content': prompt})

    # Sliding Window: Remove oldest User/Assistant pairs if thread is too long
    # (MAX_HISTORY * 2) + 1 accounts for the System Message + pairs
    while len(thread) > (MAX_HISTORY * 2) + 1:
        # We pop index 1 twice to remove the oldest User and then the oldest Assistant response
        thread.pop(1)
        thread.pop(1)

    payload = {
        'model': DEEPSEEK_MODEL,
        'messages': thread,
        'stream': True
    }

    try:
        r = requests.post(OLLAMA_CHAT_URL, stream=True, json=payload, timeout=180)
        r.raise_for_status()

        full_response = ""
        in_think = False

        for line in r.iter_lines():
            if line:
                data = json.loads(line.decode('utf-8'))
                content = data.get("message", {}).get("content", "")

                # Filter out Deepseek <think> blocks from Signal output
                if "<think>" in content:
                    in_think = True
                    continue
                if "</think>" in content:
                    in_think = False
                    continue

                if not in_think and content:
                    full_response += content

                if data.get("done"):
                    break

        final_text = full_response.strip()
        if not final_text:
            final_text = "(The model provided an empty response.)"

        thread.append({'role': 'assistant', 'content': final_text})

    except Exception as e:
        print(f"[ERROR] Ollama communication failed: {e}")
        thread.append({'role': 'assistant', 'content': f"⚠️ I encountered an error: {e}"})
