import requests
import time
import re
import json
import os
from datetime import datetime, timedelta

# ================= بيانات حساب Green API =================
ID_INSTANCE = "7107576012"
API_TOKEN_INSTANCE = "329061fc778d4d33bb3648f9914087c0a09fed5a57fb4c8597"
API_URL = "https://7107.api.greenapi.com"

# ================= مفتاح Groq API =================
GROQ_API_KEY = "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"

# ================= النموذج =================
MODEL = "llama-3.3-70b-versatile"

MEMORY_FILE = "chat_memory.json"

def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_memory(memory):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)

def clean_old_messages(memory):
    now = datetime.now()
    updated = False
    for user_id in list(memory.keys()):
        if 'history' in memory[user_id]:
            new_history = []
            for msg, rep, timestamp in memory[user_id]['history']:
                msg_time = datetime.fromisoformat(timestamp)
                if now - msg_time < timedelta(hours=24):
                    new_history.append((msg, rep, timestamp))
                else:
                    updated = True
            memory[user_id]['history'] = new_history
            if not new_history and 'last_update' in memory[user_id]:
                del memory[user_id]
                updated = True
    if updated:
        save_memory(memory)
    return memory

def get_user_history(user_id, memory, max_messages=15):
    if user_id not in memory:
        memory[user_id] = {'history': [], 'last_update': datetime.now().isoformat()}
    memory = clean_old_messages(memory)
    return memory.get(user_id, {}).get('history', [])[-max_messages:]

def add_to_history(memory, user_id, user_msg, bot_reply):
    now = datetime.now().isoformat()
    if user_id not in memory:
        memory[user_id] = {'history': []}
    memory[user_id]['history'].append((user_msg, bot_reply, now))
    if len(memory[user_id]['history']) > 50:
        memory[user_id]['history'] = memory[user_id]['history'][-50:]
    memory[user_id]['last_update'] = now
    save_memory(memory)
    return memory

def build_context(history):
    if not history:
        return ""
    context = "آخر محادثاتنا:\n"
    for user_msg, bot_reply, _ in history[-8:]:
        context += f"أنا: {user_msg}\nأنت: {bot_reply}\n"
    return context

def clean_reply(text):
    if not text:
        return "أهلاً."
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<\|.*?\|>', '', text, flags=re.DOTALL)
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    # إزالة الإيموجيات كلها (لأننا سنضيفها يدوياً في البرومنت بشكل متحكم)
    emoji_pattern = re.compile("["
        u"\U0001F600-\U0001F64F"
        u"\U0001F300-\U0001F5FF"
        u"\U0001F680-\U0001F6FF"
        u"\U0001F1E0-\U0001F1FF"
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE)
    text = emoji_pattern.sub(r'', text)
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        lower_line = line.strip().lower()
        if lower_line.startswith(('okay', 'let me', 'i need', 'the user', 'alright', 'first', 'i will', 'note:', 'response:', 'answer:', 'think')):
            continue
        if len(line.strip()) > 0:
            clean_lines.append(line)
    text = '\n'.join(clean_lines)
    text = re.sub(r'[*_~>#|]+', '', text)
    text = text.strip()
    if len(text) > 500:
        text = text[:500]
    return text if text else "أهلاً."

def get_ai_response(user_input, chat_id, memory):
    history = get_user_history(chat_id, memory)
    context = build_context(history)
    
    # لو سأل عن الاسم
    ask_name_keywords = ["اسمك", "مين انت", "انت مين", "مين تكون", "بتسمي نفسك", "what's your name"]
    if any(word in user_input.lower() for word in ask_name_keywords):
        return "اسمي ابن مورا."
    
    # لو قال كلمات توقف
    stop_words = ["فكك", "خلاص", "كفاية", "بس كده", "كفايه"]
    if any(word in user_input for word in stop_words):
        return "تمام."
    
    # لو فيه شتيمة أو سلبية قوية
    bad_words = ["خرا", "زفت", "وسخ", "قرف", "منيكة"]
    if any(word in user_input for word in bad_words):
        return "خلاص، اهدى شوية. إيه اللي مضايقك؟"
    
    for attempt in range(2):
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            }
            
            prompt = f"""أنت مساعد ذكي ومثقف اسمك "ابن مورا" لكن لا تذكر اسمك إلا إذا سألك المستخدم. تتحدث بالعامية المصرية.
تعليمات صارمة للغاية:
- ممنوع تكرار نفس الرد أبداً. ممنوع أن تقول "أهلاً أنا كويس وإنت" أكثر من مرة في المحادثة.
- إذا قال المستخدم "اذيك" أو "ازيك"، رد بأهلاً بسيط واسأله عن حاله، لكن لا تكرر هذا الرد في نفس المحادثة.
- إذا قال المستخدم "خرا" أو "زفت"، رد بـ "خلاص اهدى شوية. إيه اللي مضايقك؟".
- إذا قال "مش كويس"، اسأله باهتمام "إيه اللي مضايقك؟" أو "ليه كدا؟".
- ردودك قصيرة، مفيدة، وطبيعية. لا تشرح كثيراً.
- يمكنك استخدام إيموجية بسيطة من حين لآخر (😊،📚،💔،😂)، لكن ليس في كل رد.
- إذا سأل عن شيء علمي أو دراسي، أجب بشكل صحيح ومختصر.
- إذا طلب نكتة، احكي نكتة حقيقية.
- لا تسأل "يعني إيه" أبداً.
- لا تقدم نصائح عامة مملة.

{context}
الرسالة: "{user_input}"
رد المساعد (مصري، قصير، بدون تكرار، بدون أسئلة فارغة):"""
            
            data = {
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.8,
                "max_tokens": 150,
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=25)
            
            if response.status_code == 200:
                result = response.json()
                reply = result["choices"][0]["message"]["content"]
                reply = clean_reply(reply)
                if reply and len(reply) > 1:
                    return reply
                else:
                    return "أهلاً."
            elif response.status_code == 429:
                time.sleep(2)
                continue
            else:
                time.sleep(1)
                continue
                
        except Exception as e:
            print(f"محاولة {attempt+1} فشلت: {e}")
            time.sleep(1)
            continue
    
    return "آسف، عندي زحمة، جرب تاني."

def start_bot():
    print("🚀 البوت ابن مورا (النسخة المستقرة) شغال...")
    memory = load_memory()
    while True:
        try:
            receive_url = f"{API_URL}/waInstance{ID_INSTANCE}/receiveNotification/{API_TOKEN_INSTANCE}"
            resp = requests.get(receive_url, timeout=25)
            
            if resp.status_code == 200:
                notifications = resp.json()
                if notifications:
                    receipt_id = notifications['receiptId']
                    body = notifications.get('body', {})
                    
                    delete_url = f"{API_URL}/waInstance{ID_INSTANCE}/deleteNotification/{API_TOKEN_INSTANCE}/{receipt_id}"
                    requests.delete(delete_url, timeout=10)
                    
                    if body.get('typeWebhook') == 'incomingMessageReceived':
                        msg_data = body.get('messageData', {})
                        if 'textMessageData' in msg_data:
                            user_text = msg_data['textMessageData']['textMessage']
                            sender = body['senderData']['chatId']
                            
                            print(f"📩 رسالة جديدة: {user_text}")
                            reply_text = get_ai_response(user_text, sender, memory)
                            
                            memory = add_to_history(memory, sender, user_text, reply_text)
                            
                            send_url = f"{API_URL}/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN_INSTANCE}"
                            send_data = {"chatId": sender, "message": reply_text}
                            requests.post(send_url, json=send_data, timeout=10)
                            
                            print(f"✅ تم الرد: {reply_text}")
            else:
                time.sleep(2)
        
        except Exception as e:
            print(f"⚠️ خطأ: {e}")
            time.sleep(3)
        
        time.sleep(0.5)

if __name__ == "__main__":
    start_bot()