import redis
import json
import uuid, hashlib
from openai import OpenAI

# redis默认使用6379接口
r = redis.Redis(host='localhost', port=6379, decode_responses=True)

# 维护一个动态session列表
active_sessions = []

# 【修改】新的系统提示词，指导模型输出特定格式
original_prompt = [{
    'role': 'system', 
    'content': """你是一个专业的网络工程师和P4程序员。你的任务是分析用户提供的网络拓扑，并根据用户的问题提供专业的解答。
你的每次回答都必须严格遵循以下JSON格式，不要有任何多余的文字或解释：
{
  "analysis": "这里是你对用户问题的详细分析和文字说明，请使用Markdown格式。",
  "files": [
    {
      "filename": "p4_code.p4",
      "content": "这里是生成的P4代码或相关脚本内容。"
    },
    {
      "filename": "flow_rules.txt",
      "content": "这里是生成的流表规则或配置命令。"
    }
  ],
  "questions": [
    "猜你想问的问题1？",
    "猜你想问的问题2？",
    "猜你想问的问题3？"
  ]
}
如果某个部分没有内容（例如用户只是打招呼，不需要生成文件），请将对应的值设为空字符串或空列表，但不要省略任何键。"""
}]
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

# 【修改】append_message 函数
def append_message(session_id, role, content):
    key = f"chat_history:{session_id}"
    history = get_history(session_id)
    history.append({"role": role, "content": content})
    r.set(key, json.dumps(history))

# 修改后的 call_llm_1 函数
def call_llm_1(session_id, user_message, topo_str=None):
    client = OpenAI(
        api_key='sk-79784ea536174319bd82937f20da9c52', 
        base_url="https://chat.ecnu.edu.cn/open/api/v1",
    )

    content_to_send = user_message
    if topo_str:
        content_to_send += "\n\n" + topo_str

    append_message(session_id, 'user', content_to_send)
    history = get_history(session_id)

    try:
        completion = client.chat.completions.create(
            model="ecnu-max",
            messages=history,
            response_format={"type": "json_object"}
        )
        response_content = completion.choices[0].message.content
    except Exception as e:
        # 如果API调用失败，返回一个错误结构
        print(f"OpenAI API call failed: {e}")
        error_response = {
            "analysis": f"抱歉，调用AI模型时出错：\n`{str(e)}`\n请检查API密钥、网络连接或模型名称是否正确。",
            "files": [],
            "questions": ["什么是P4？", "什么是FatTree拓扑？", "如何开始学习网络编程？"]
        }
        append_message(session_id, 'assistant', json.dumps(error_response))
        return error_response

    append_message(session_id, 'assistant', response_content)
    
    try:
        return json.loads(response_content)
    except json.JSONDecodeError:
        print(f"LLM did not return valid JSON: {response_content}")
        fallback_response = {
            "analysis": "抱歉，模型返回的格式有误，请您重试。\n\n**原始回复：**\n```\n" + response_content + "\n```",
            "files": [],
            "questions": ["如何实现基本的L2转发？", "这个拓扑的瓶颈可能在哪里？", "如何为h1到h2生成一条静态路径？"]
        }
        append_message(session_id, 'assistant', json.dumps(fallback_response))
        return fallback_response

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