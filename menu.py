import os
from dotenv import load_dotenv
import dashscope
from dashscope import Generation
import pymysql

load_dotenv()

# ==================== 数据库配置 ====================
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "75757575",   # 改成你实际的 root 密码
    "database": "menu_db",
    "charset": "utf8mb4"
}

# ==================== 从 MySQL 加载数据 ====================
def load_menu_from_db():
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT name, ingredients, steps FROM recipes")
    rows = cursor.fetchall()
    conn.close()
    menu = {}
    for name, ingredients, steps in rows:
        menu[name] = {
            "食材": ingredients.split(",") if ingredients else [],
            "做法": steps
        }
    return menu

menu = load_menu_from_db()
print(f"📂 已从 MySQL 加载 {len(menu)} 道菜")

# ==================== 数据库操作辅助函数 ====================
def insert_recipe(name, ingredients, steps):
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    ingredients_str = ",".join(ingredients)
    cursor.execute(
        "INSERT INTO recipes (name, ingredients, steps) VALUES (%s, %s, %s)",
        (name, ingredients_str, steps)
    )
    conn.commit()
    conn.close()

def delete_recipe(name):
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM recipes WHERE name = %s", (name,))
    conn.commit()
    conn.close()

def update_recipe(name, new_ingredients, new_steps):
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    ingredients_str = ",".join(new_ingredients)
    cursor.execute(
        "UPDATE recipes SET ingredients = %s, steps = %s WHERE name = %s",
        (ingredients_str, new_steps, name)
    )
    conn.commit()
    conn.close()

# ==================== 提取冒号后的内容 ====================
def 提取冒号后的内容(文本):
    文本 = 文本.strip()
    if "：" in 文本:
        return 文本.split("：")[-1].strip()
    elif ":" in 文本:
        return 文本.split(":")[-1].strip()
    return 文本

# ==================== 解析 AI 返回内容 ====================
def 解析AI内容(content):
    菜名 = ""
    食材 = []
    做法 = ""

    lines = content.strip().split("\n")

    做法索引 = -1
    for i, line in enumerate(lines):
        if "做法" in line:
            做法索引 = i
            break

    for line in lines:
        if "菜名" in line:
            菜名 = 提取冒号后的内容(line)
            break

    if 做法索引 > 0:
        for line in lines[1:做法索引]:
            if "食材" in line:
                食材部分 = 提取冒号后的内容(line)
                if "，" in 食材部分:
                    食材 = [x.strip() for x in 食材部分.split("，")]
                elif "、" in 食材部分:
                    食材 = [x.strip() for x in 食材部分.split("、")]
                else:
                    食材 = [x.strip() for x in 食材部分.split(",")]
                食材 = [x for x in 食材 if x != ""]
                break

    if 做法索引 >= 0:
        做法 = 提取冒号后的内容(lines[做法索引])
        for line in lines[做法索引 + 1:]:
            line = line.strip()
            if line:
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
                insert_recipe(菜名, 食材, 做法)
                menu[菜名] = {"食材": 食材, "做法": 做法}
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
            insert_recipe(菜名, 食材列表, 做法输入)
            menu[菜名] = {"食材": 食材列表, "做法": 做法输入}
            print(f"✅ 已添加【{菜名}】！")

    elif 选择 == "3":
        菜名 = input("请输入要删除的菜名：")
        if 菜名 in menu:
            delete_recipe(菜名)
            del menu[菜名]
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
            update_recipe(菜名, 新食材列表, 新做法)
            menu[菜名]["食材"] = 新食材列表
            menu[菜名]["做法"] = 新做法
            print(f"✅ 【{菜名}】已更新！")

    elif 选择 == "5":
        ai_recommend()

    elif 选择 == "6":
        print("📁 数据已保存在 MySQL 中，再见！")
        break

    else:
        print("❌ 无效选择，请输入 1-6")