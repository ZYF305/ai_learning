import json
import re
import os
from dotenv import load_dotenv
import dashscope
from dashscope import Generation

load_dotenv()

# ==================== 路径处理 ====================
# 获取当前脚本所在目录，确保 menu.json 始终在脚本同目录下
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(BASE_DIR, "menu.json")

# ==================== 保存菜单到 JSON ====================
def save_menu():
    try:
        with open(JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(menu, f, ensure_ascii=False, indent=2)
        print(f"📁 已保存到：{JSON_PATH}")
    except Exception as e:
        print(f"❌ 保存失败！路径：{JSON_PATH}，错误：{e}")

# ==================== 读取数据 ====================
try:
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        menu = json.load(f)
    print(f"📂 已加载菜谱文件：{JSON_PATH}（共 {len(menu)} 道菜）")
except FileNotFoundError:
    menu = {}
    print(f"📂 未找到菜谱文件，将创建新文件：{JSON_PATH}")
except json.JSONDecodeError:
    menu = {}
    print(f"⚠️ 菜谱文件格式错误，已重置为空菜单：{JSON_PATH}")

# ==================== AI 推荐功能 ====================
def ai_recommend():
    # 🔑 替换成你自己的 API Key
    dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
    食材输入 = input("请输入你有的食材（用中文逗号或空格分隔）：")
    if not 食材输入.strip():
        print("❌ 食材不能为空！")
        return

    prompt = f"""你是一个厨艺高超的AI厨师。请根据以下食材推荐一道菜：
食材：{食材输入}

请按以下格式返回（严格按这个格式，不要有多余内容）：
菜名：XXX
食材：XXX, XXX, XXX
做法：
1. XXX
2. XXX
3. XXX
"""

    try:
        response = Generation.call(
            model="qwen-turbo",
            messages=[{"role": "user", "content": prompt}],
            result_format="message"
        )

        if response.status_code == 200:
            content = response.output.choices[0].message.content
            print("\n" + "=" * 40)
            print("🍳 AI 推荐菜谱：")
            print(content)
            print("=" * 40 + "\n")

            # ========== 用正则解析 ==========
            菜名 = ""
            食材 = []
            做法 = ""

            菜名匹配 = re.search(r'菜名[：:]\s*(.+)', content)
            if 菜名匹配:
                菜名 = 菜名匹配.group(1).strip()

            食材匹配 = re.search(r'食材[：:]\s*(.+)', content)
            if 食材匹配:
                食材文本 = 食材匹配.group(1).strip()
                食材 = [x.strip() for x in re.split(r'[，,]', 食材文本) if x.strip()]

            做法匹配 = re.search(r'做法[：:]\s*([\s\S]+)', content)
            if 做法匹配:
                做法 = 做法匹配.group(1).strip()

            if 菜名 and 食材 and 做法:
                if 菜名 in menu:
                    print(f"⚠️ 【{菜名}】已存在，已跳过添加")
                else:
                    menu[菜名] = {
                        "食材": 食材,
                        "做法": 做法
                    }
                    save_menu()
                    print(f"✅ AI 推荐的【{菜名}】已添加到你的菜谱中！")
            else:
                print("⚠️ 解析失败，请手动添加该菜谱。")
                print(f"   解析结果 -> 菜名: '{菜名}', 食材: {食材}, 做法: '{做法[:30]}...'")
                print("AI 原始返回：")
                print(content)
        else:
            print("❌ API 调用失败：", response.message)

    except Exception as e:
        print(f"❌ AI 服务暂时不可用，请稍后重试。错误信息：{e}")

# ==================== 主菜单 ====================
while True:
    print("\n📋 家庭菜谱管理系统")
    print("1. 查看所有菜")
    print("2. 手动新增菜")
    print("3. 删除菜")
    print("4. 修改菜")
    print("5. AI 推荐菜")
    print("6. 退出")

    选择 = input("请选择操作（1-6）：")

    if 选择 == "1":
        if not menu:
            print("📭 菜单是空的，请添加菜谱！")
        else:
            print("\n" + "=" * 40)
            for 菜名, 信息 in menu.items():
                print(f"【{菜名}】")
                print(f"  食材：{', '.join(信息['食材'])}")
                print(f"  做法：{信息['做法']}")
                print("-" * 30)
            print("=" * 40)

    elif 选择 == "2":
        菜名 = input("请输入要新增的菜名：")
        if 菜名 in menu:
            print(f"⚠️ 【{菜名}】已存在，不能重复添加！")
        else:
            食材输入 = input("请输入食材（用英文逗号分隔）：")
            食材列表 = [x.strip() for x in 食材输入.split(",")]
            做法输入 = input("请输入做法（用 \\n 分隔步骤）：")
            做法输入 = 做法输入.replace("\\n", "\n")
            menu[菜名] = {
                "食材": 食材列表,
                "做法": 做法输入
            }
            save_menu()
            print(f"✅ 已添加【{菜名}】！")

    elif 选择 == "3":
        菜名 = input("请输入要删除的菜名：")
        if 菜名 in menu:
            del menu[菜名]
            save_menu()
            print(f"✅ 已删除【{菜名}】")
        else:
            print(f"❌ 未找到【{菜名}】")

    elif 选择 == "4":
        菜名 = input("请输入要修改的菜名：")
        if 菜名 not in menu:
            print(f"❌ 未找到【{菜名}】")
        else:
            新食材 = input("请输入新的食材（用英文逗号分隔）：")
            新食材列表 = [x.strip() for x in 新食材.split(",")]
            新做法 = input("请输入新的做法（用 \\n 分隔步骤）：")
            新做法 = 新做法.replace("\\n", "\n")
            menu[菜名]["食材"] = 新食材列表
            menu[菜名]["做法"] = 新做法
            save_menu()
            print(f"✅ 【{菜名}】已更新！")

    elif 选择 == "5":
        ai_recommend()

    elif 选择 == "6":
        save_menu()
        print("📁 菜谱已保存，再见！")
        break

    else:
        print("❌ 无效选择，请输入 1-6")