import os
from dotenv import load_dotenv
load_dotenv()
import dashscope
from dashscope import Generation

dashscope.api_key = os.getenv('DASHSCOPE_API_KEY')

prompt = """你是一个厨艺高超的AI厨师。请根据以下要求生成 3 道菜谱：
口味要求：辣的

请按以下格式返回，每道菜之间用"---"分隔：
菜名：XXX
食材：XXX, XXX, XXX
做法：
1. XXX
2. XXX
3. XXX
---
菜名：XXX
食材：XXX, XXX, XXX
做法：
1. XXX
2. XXX
3. XXX
"""

response = Generation.call(
    model='qwen-turbo',
    messages=[{'role': 'user', 'content': prompt}],
    result_format='message'
)

print('状态码:', response.status_code)
if response.status_code == 200:
    print('返回内容:')
    print(response.output.choices[0].message.content)
else:
    print('错误:', response.message)