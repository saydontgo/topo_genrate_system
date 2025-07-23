import redis
import json
import uuid, hashlib
from openai import OpenAI

# redis默认使用6379接口
r = redis.Redis(host='localhost', port=6379, decode_responses=True)

# 维护一个动态session列表
active_sessions = []

# 初始的提示词
original_prompt = [{'role': 'system', 'content': 'You are a helpful assistant.'}]
# 生成session_id
def secure_session_id():
    uid = uuid.uuid4().hex + uuid.uuid4().hex  # 拼两个 UUID
    return hashlib.sha256(uid.encode()).hexdigest()

def get_history(session_id):
    if session_id not in active_sessions:
        active_sessions.append(session_id)
        key = f"chat_history:{session_id}"
        r.set(key, json.dumps(original_prompt))
    data = r.get(f"chat_history:{session_id}")
    return json.loads(data) if data else []

def append_message(session_id, role, user_message, topo=None):
    key = f"chat_history:{session_id}"
    history = get_history(session_id)
    content = [{
                    "type": "text",
                    "text": user_message
            }]
    
    if topo:
        content.append({
                    "type": "text",
                    "text": topo
            })
        
    history.append(
        {
            "role": role, 
            "content": content
        })
    r.set(key, json.dumps(history))



def call_llm_1(session_id, user_message, topo=None):
    client = OpenAI(
        api_key='sk-79784ea536174319bd82937f20da9c52',  # 替换为您的API密钥
        base_url="https://chat.ecnu.edu.cn/open/api/v1",
    )

    append_message(session_id, 'user', user_message, topo)
    history = get_history(session_id)
    completion = client.chat.completions.create(
        model="ecnu-vl", # 模型列表：https://developer.ecnu.edu.cn/vitepress/llm/api/models.html
        messages=history
        )

    info = completion.model_dump_json()

    # 硬编码,对于不同模型要改
    response = json.loads(info)['choices'][0]['message']['content']
    append_message(session_id, 'assistant', response)
    
    return response

if __name__ == '__main__':
    session_id = secure_session_id()
    with open('test.json', 'r') as f:
        topo = f.read()
        print(topo)
    # ctrl + c 退出
    try:
        while True:
            message = input('请输入: ')
            response = call_llm_1(session_id, message, topo)
            print('--------------以下是ai的回复----------------')
            print(response)
            print('--------------以上是ai的回复----------------')
    except KeyboardInterrupt:
        exit(0)