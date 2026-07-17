import json
import os
from dotenv import load_dotenv
import dashscope
from dashscope import Generation

# ==================== 加载环境变量 ====================
load_dotenv()

# ==================== 路径处理 ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(BASE_DIR, "menu.json")

# ==================== 读取数据 ====================
try:
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        menu = json.load(f)
    print(f"📂 已加载 {len(menu)} 道菜")
except FileNotFoundError:
    menu = {}
    print("📂 未找到菜单文件，已创建空菜单")
except json.JSONDecodeError:
    menu = {}
    print("⚠️ 菜单文件格式错误，已重置为空菜单")

# ==================== 保存数据 ====================
def save_menu():
    """把 menu 字典保存到 JSON 文件"""
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(menu, f, ensure_ascii=False, indent=2)

# ==================== 辅助函数：提取冒号后的内容 ====================
def 提取冒号后的内容(文本):
    """从 '菜名：番茄炒蛋' 或 '菜名:番茄炒蛋' 中提取 '番茄炒蛋'"""
    文本 = 文本.strip()
    if "：" in 文本:
        return 文本.split("：")[-1].strip()
    elif ":" in 文本:
        return 文本.split(":")[-1].strip()
    return 文本

# ==================== 解析 AI 返回内容 ====================
def 解析AI内容(content):
    """从 AI 返回的文本中提取 菜名、食材、做法"""
    菜名 = ""
    食材 = []
    做法 = ""

    lines = content.strip().split("\n")

    # 1. 找“做法”在第几行
    做法索引 = -1
    for i, line in enumerate(lines):
        if "做法" in line:
            做法索引 = i
            break

    # 2. 提取菜名
    for line in lines:
        if "菜名" in line:
            菜名 = 提取冒号后的内容(line)
            break

    # 3. 提取食材（在“做法”之前找“食材”行）
    if 做法索引 > 0:
        for line in lines[1:做法索引]:
            if "食材" in line:
                食材部分 = 提取冒号后的内容(line)
                # 支持三种分隔符：中文逗号、英文逗号、顿号
                if "，" in 食材部分:
                    食材 = [x.strip() for x in 食材部分.split("，")]
                elif "、" in 食材部分:
                    食材 = [x.strip() for x in 食材部分.split("、")]
                else:
                    食材 = [x.strip() for x in 食材部分.split(",")]
                # 去掉空字符串
                食材 = [x for x in 食材 if x != ""]
                break

    # 4. 提取做法（从“做法”行开始，到末尾）
    if 做法索引 >= 0:
        做法 = 提取冒号后的内容(lines[做法索引])
        for line in lines[做法索引 + 1:]:
            line = line.strip()
            if line:
                # 如果做法末尾不是换行，先补一个换行再拼接
                if not 做法.endswith("\n"):
                    做法 += "\n"
                做法 += line

    return 菜名, 食材, 做法

# ==================== AI 推荐功能 ====================
def ai_recommend():
    dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")

    食材输入 = input("请输入你有的食材（用中文逗号或空格分隔）：")
    if not 食材输入.strip():
        print("❌ 食材不能为空！")
        return

    prompt = f"""你是一个厨艺高超的AI厨师。请根据以下食材推荐一道菜：
食材：{食材输入}

请按以下格式返回：
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

        if response.status_code != 200:
            print("❌ API 调用失败：", response.message)
            return

        content = response.output.choices[0].message.content
        print("\n" + "=" * 40)
        print("🍳 AI 推荐菜谱：")
        print(content)
        print("=" * 40 + "\n")

        菜名, 食材, 做法 = 解析AI内容(content)

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
            print("AI 返回的内容：")
            print(content)

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
            for 菜名 in menu:
                print(f"【{菜名}】")
                print(f"  食材：{', '.join(menu[菜名]['食材'])}")
                print(f"  做法：{menu[菜名]['做法']}")
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