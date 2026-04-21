from p4utils.mininetlib.log import setLogLevel, info
import redis
import json
import uuid, hashlib
from openai import OpenAI
from error import InvalidModelException
from llm_config import get_provider_settings, DEEPSEEK_MODEL, ECNU_MODEL
# redis默认使用6379接口
r = redis.Redis(host='localhost', port=6379, decode_responses=True)

# 维护一个动态session列表
active_sessions = []

ecnu_ai = ECNU_MODEL
deepseek = DEEPSEEK_MODEL

# 【修改】新的系统提示词，指导模型输出特定格式
original_prompt = [{
    'role': 'system', 
    'content': """你是一个专业的网络工程师和P4程序员。你的任务是分析用户提供的网络拓扑，并根据用户的问题提供专业的解答。
如果用户提供的拓扑 JSON 中包含 `intent_description` 字段，请将它视为用户明确的编排需求来源，优先据此生成 `intent.summary` 和 `intent.flows`；不要忽略这段说明。
你的每次回答都必须严格遵循以下JSON格式，不要有任何多余的文字或解释：
{
  "analysis": "这里是你对用户问题的详细分析和文字说明，请使用Markdown格式。",
  "intent": {
    "summary": "一句话概括用户的网络编排意图；如果用户还没有提出明确需求，则为空字符串。",
    "flows": [
      {
        "src": "源主机ID，例如 h1",
        "dst": "目标主机ID，例如 h2",
        "must_pass": ["必须经过的交换机列表，没有则返回空数组"],
        "avoid": ["需要避开的交换机列表，没有则返回空数组"],
        "priority": "转发偏好，例如 shortest / load_balance / low_latency",
        "backup_level": 1
      }
    ]
  },
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
    "第一个问题？(此处以用户的身份猜测用户想提出的问题)",
    "第二个问题？(此处以用户的身份猜测用户想提出的问题)",
    "第三个问题？(此处以用户的身份猜测用户想提出的问题)"
  ]
}
如果某个部分没有内容（例如用户只是打招呼，不需要生成文件或暂时无法形成意图），请将对应的值设为空字符串、空对象或空列表，但不要省略任何键。
intent 部分必须保持结构稳定：至少包含 summary 和 flows 两个键；flows 中的每一项都必须包含 src、dst、must_pass、avoid、priority、backup_level。
当 `intent_description` 已经明确描述路径偏好、必经节点、避让节点、优先级或冗余要求时，请尽量将这些信息提取到结构化的 `intent` 中。"""
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


def normalize_response_payload(payload):
    if not isinstance(payload, dict):
        payload = {}

    intent = payload.get("intent")
    if not isinstance(intent, dict):
        intent = {}

    flows = intent.get("flows")
    if not isinstance(flows, list):
        flows = []

    normalized_flows = []
    for flow in flows:
        if not isinstance(flow, dict):
            continue
        normalized_flows.append({
            "src": flow.get("src", ""),
            "dst": flow.get("dst", ""),
            "must_pass": flow.get("must_pass", []) if isinstance(flow.get("must_pass", []), list) else [],
            "avoid": flow.get("avoid", []) if isinstance(flow.get("avoid", []), list) else [],
            "priority": flow.get("priority", ""),
            "backup_level": flow.get("backup_level", 0),
        })

    payload["analysis"] = payload.get("analysis", "")
    payload["intent"] = {
        "summary": intent.get("summary", ""),
        "flows": normalized_flows
    }
    payload["files"] = payload.get("files", []) if isinstance(payload.get("files", []), list) else []
    payload["questions"] = payload.get("questions", []) if isinstance(payload.get("questions", []), list) else []
    return payload


def build_degraded_response(analysis_message, questions=None):
    payload = {
        "analysis": analysis_message,
        "intent": {
            "summary": "",
            "flows": []
        },
        "files": [],
        "questions": questions or []
    }
    payload = normalize_response_payload(payload)
    payload["success"] = True
    payload["degraded"] = True
    return payload


def llm_provider_is_configured(base_url, api_key):
    placeholder_values = {"", "your_api", "your_api_key"}
    return base_url not in placeholder_values and api_key not in placeholder_values

def get_response(client, model, history, session_id):
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=history
        )
        completion_json = completion.model_dump_json()
        response_content = json.loads(completion_json)['choices'][0]['message']['content'].strip('```').lstrip('json\n')
    except Exception as e:
        info(f"OpenAI API call failed: {e}")
        error_response = build_degraded_response(
            f"抱歉，调用AI模型时出错：\n`{str(e)}`\n已跳过在线分析，你仍然可以继续上传拓扑、生成网络并手动调整 intent。",
            ["什么是P4？", "什么是FatTree拓扑？", "如何开始学习网络编程？"]
        )
        append_message(session_id, 'assistant', json.dumps(error_response))
        return error_response

    append_message(session_id, 'assistant', response_content)
    
    try:
        response_content = json.loads(response_content)
        response_content = normalize_response_payload(response_content)
        response_content["success"] = True
        response_content["degraded"] = False
        return response_content
    except json.JSONDecodeError:
        info(f"LLM did not return valid JSON: {response_content}")
        fallback_response = build_degraded_response(
            f"抱歉，模型返回的格式有误，已使用降级响应。\n\n**原始回复：**\n```\n{response_content}\n```",
            ["如何实现基本的L2转发？", "这个拓扑的瓶颈可能在哪里？", "如何为h1到h2生成一条静态路径？"]
        )
        append_message(session_id, 'assistant', json.dumps(fallback_response))
        return fallback_response

# 修改后的 call_llm 函数
def call_llm(model, session_id, user_message, topo_str=None):
    provider_settings = get_provider_settings(model)
    if provider_settings is None:
        raise InvalidModelException
    base_url = provider_settings['base_url']
    api_key = provider_settings['api_key']

    content_to_send = user_message
    if topo_str:
        content_to_send += "\n\n" + topo_str

    append_message(session_id, 'user', content_to_send)

    if not llm_provider_is_configured(base_url, api_key):
        fallback_response = build_degraded_response(
            "AI 模型尚未完成配置，已跳过在线分析。你仍然可以继续上传拓扑、构建网络，并在设置页补充 API 地址和密钥后恢复在线分析。",
            ["如何手动编写 intent.json？", "当前拓扑有哪些主机和交换机？", "怎样继续测试 VBP 路径验证？"]
        )
        append_message(session_id, 'assistant', json.dumps(fallback_response))
        return fallback_response

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    history = get_history(session_id)

    return get_response(client, model, history, session_id)
    

if __name__ == '__main__':
    session_id = secure_session_id()
    setLogLevel('info')
    # ctrl + c 退出
    try:
        while True:
            message = input('请输入: ')
            response = call_llm(deepseek, session_id, message)
            print('--------------以下是ai的回复----------------')
            print(response)
            print('--------------以上是ai的回复----------------')
    except KeyboardInterrupt:
        exit(0)
