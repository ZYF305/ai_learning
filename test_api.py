import dashscope
from dashscope import Generation

# 把你的 API Key 填到这里
dashscope.api_key = "sk-ws-H.EDRXMYI.bhkv.MEQCIC9urhcYBvf10ieBBWEhCR316lngh4aC14kczwLM_yEiAiAP-yPgqVW9BoQYyf9NHzwX0elb0zCPm4RGajYBOJKw_w"

response = Generation.call(
    model="qwen-turbo",
    messages=[{"role": "user", "content": "你好，请用一句话介绍你自己"}],
    result_format="message"
)

if response.status_code == 200:
    print("AI 回复：", response.output.choices[0].message.content)
else:
    print("调用失败：", response.message)