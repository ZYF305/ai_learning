import streamlit as st
import pymysql
import os
from dotenv import load_dotenv
import dashscope
from dashscope import Generation
import datetime
import folium
from streamlit_folium import st_folium
import json
import re
import collections

load_dotenv()

# ==================== 数据库配置 ====================
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "75757575",   # 改成你实际的 root 密码
    "database": "menu_db",
    "charset": "utf8mb4"
}

# ==================== 菜谱相关函数 ====================
def load_menu():
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT name, ingredients, steps FROM recipes")
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_recipe(name, ingredients, steps):
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO recipes (name, ingredients, steps) VALUES (%s, %s, %s)",
        (name, ingredients, steps)
    )
    conn.commit()
    conn.close()

def delete_recipe(name):
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM recipes WHERE name = %s", (name,))
    conn.commit()
    conn.close()

def update_recipe(old_name, new_name, new_ingredients, new_steps):
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE recipes SET name = %s, ingredients = %s, steps = %s WHERE name = %s",
        (new_name, new_ingredients, new_steps, old_name)
    )
    conn.commit()
    conn.close()

def search_recipes_by_keyword(query):
    rows = load_menu()
    results = []
    query_lower = query.lower()
    for name, ingredients, steps in rows:
        combined = f"{name} {ingredients} {steps}".lower()
        if query_lower in combined:
            results.append({"name": name, "ingredients": ingredients, "steps": steps})
    return results

def ai_generate_recipes(taste, count=5):
    dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
    prompt = f"""你是一个厨艺高超的AI厨师。请根据以下要求生成 {count} 道菜谱：
口味要求：{taste}

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
（以此类推）
"""
    try:
        response = Generation.call(
            model="qwen-turbo",
            messages=[{"role": "user", "content": prompt}],
            result_format="message"
        )
        if response.status_code != 200:
            return None, f"❌ API 调用失败：{response.message}"
        content = response.output.choices[0].message.content
        recipes = parse_recipes(content)
        if not recipes:
            return None, "解析失败，AI 返回格式异常"
        return recipes, None
    except Exception as e:
        return None, f"❌ AI 服务暂时不可用：{e}"

def parse_recipes(content):
    recipes = []
    blocks = content.split("---")
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        name = ""
        ingredients = ""
        steps = ""
        is_steps = False
        for line in block.split("\n"):
            line = line.strip()
            if not line:
                continue
            if "菜名" in line:
                if "：" in line:
                    name = line.split("：")[-1].strip()
                elif ":" in line:
                    name = line.split(":")[-1].strip()
            elif "食材" in line:
                if "：" in line:
                    ingredients = line.split("：")[-1].strip()
                elif ":" in line:
                    ingredients = line.split(":")[-1].strip()
            elif "做法" in line:
                if "：" in line:
                    rest = line.split("：")[-1].strip()
                elif ":" in line:
                    rest = line.split(":")[-1].strip()
                else:
                    rest = ""
                if rest:
                    steps = rest
                else:
                    is_steps = True
            elif is_steps and line:
                if "菜名" in line or "食材" in line or "做法" in line:
                    continue
                if steps:
                    steps += "\n" + line
                else:
                    steps = line
        if name and ingredients and steps:
            recipes.append({"name": name, "ingredients": ingredients, "steps": steps})
    return recipes

# ==================== 菜谱板块 ====================
def cook_page():
    import datetime
    import dashscope
    from dashscope import Generation
    import os
    import base64
    import re
    
    # ==================== 重置分类选中状态 ====================
    if "selected_category_id" not in st.session_state:
        st.session_state.selected_category_id = None
    else:
        if "from_category_click" not in st.session_state:
            st.session_state.selected_category_id = None
        else:
            st.session_state.from_category_click = False
    
    # ==================== 分类操作函数 ====================
    def get_categories():
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, icon, sort_order FROM categories ORDER BY sort_order, id")
        rows = cursor.fetchall()
        conn.close()
        return rows
    
    def add_category(name, icon="📋"):
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO categories (name, icon) VALUES (%s, %s)",
            (name, icon)
        )
        conn.commit()
        conn.close()
    
    def update_category(cat_id, new_name):
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE categories SET name = %s WHERE id = %s",
            (new_name, cat_id)
        )
        conn.commit()
        conn.close()
    
    def delete_category(cat_id):
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM categories WHERE id = %s", (cat_id,))
        conn.commit()
        conn.close()
    
    # ==================== 菜操作函数 ====================
    def get_recipes_by_category(category_id):
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, ingredients, steps, cook_count, time_estimate, difficulty FROM recipes WHERE category_id = %s ORDER BY name",
            (category_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return rows
    
    def add_recipe(name, ingredients, steps, category_id, time_estimate="", difficulty=""):
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO recipes (name, ingredients, steps, category_id, time_estimate, difficulty) VALUES (%s, %s, %s, %s, %s, %s)",
            (name, ingredients, steps, category_id, time_estimate, difficulty)
        )
        conn.commit()
        conn.close()
    
    def update_recipe(recipe_id, name, ingredients, steps, category_id, time_estimate="", difficulty=""):
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE recipes SET name = %s, ingredients = %s, steps = %s, category_id = %s, time_estimate = %s, difficulty = %s WHERE id = %s",
            (name, ingredients, steps, category_id, time_estimate, difficulty, recipe_id)
        )
        conn.commit()
        conn.close()
    
    def delete_recipe(recipe_id):
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM recipes WHERE id = %s", (recipe_id,))
        conn.commit()
        conn.close()
    
    def increment_cook_count(recipe_id):
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE recipes SET cook_count = cook_count + 1 WHERE id = %s",
            (recipe_id,)
        )
        conn.commit()
        conn.close()
    
    def get_category_name(cat_id):
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT name, icon FROM categories WHERE id = %s", (cat_id,))
        row = cursor.fetchone()
        conn.close()
        return row if row else (None, None)
    
    # ==================== 解析 AI 返回的内容（支持多道菜 + 类别） ====================
    def parse_multiple_recipes(content):
        recipes = []
        blocks = content.split("---")
        if len(blocks) == 1:
            blocks = [content]
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            lines = block.split("\n")
            name = ""
            ingredients = ""
            steps = ""
            category = ""
            current_section = None
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if "菜名" in line:
                    if "：" in line:
                        name = line.split("：")[-1].strip()
                    elif ":" in line:
                        name = line.split(":")[-1].strip()
                elif "类别" in line:
                    if "：" in line:
                        category = line.split("：")[-1].strip()
                    elif ":" in line:
                        category = line.split(":")[-1].strip()
                    current_section = "category"
                elif "食材" in line:
                    if "：" in line:
                        ingredients = line.split("：")[-1].strip()
                    elif ":" in line:
                        ingredients = line.split(":")[-1].strip()
                    else:
                        current_section = "ingredients_waiting"
                elif "做法" in line:
                    if "：" in line:
                        steps = line.split("：")[-1].strip()
                    elif ":" in line:
                        steps = line.split(":")[-1].strip()
                    else:
                        steps = line
                    current_section = "steps"
                elif current_section == "ingredients_waiting" and not ingredients:
                    ingredients = line
                    current_section = None
                elif current_section == "steps" and name and ingredients:
                    if steps:
                        steps += "\n" + line
                    else:
                        steps = line
            if name and ingredients and steps:
                if not category:
                    category = "未分类"
                recipes.append({
                    "name": name,
                    "ingredients": ingredients,
                    "steps": steps,
                    "category": category
                })
        return recipes
    
    # ==================== 页面标题 ====================
    st.markdown("# 📖 我们家的小饭桌")
    
    # ==================== 初始化 session_state ====================
    if "edit_category_id" not in st.session_state:
        st.session_state.edit_category_id = None
    if "edit_recipe_id" not in st.session_state:
        st.session_state.edit_recipe_id = None
    if "category_ai_result" not in st.session_state:
        st.session_state.category_ai_result = {}
    if "recommended_names" not in st.session_state:
        st.session_state.recommended_names = []  # 存储已推荐过的菜名（用于去重）
    if "ai_global_result" not in st.session_state:
        st.session_state.ai_global_result = []  # 当前推荐列表
    if "ai_global_raw" not in st.session_state:
        st.session_state.ai_global_raw = None
    if "ai_mode" not in st.session_state:
        st.session_state.ai_mode = "食材推荐"
    if "image_recog_result" not in st.session_state:
        st.session_state.image_recog_result = None
    if "editing_category_idx" not in st.session_state:
        st.session_state.editing_category_idx = None  # 用于记录当前正在修改类别的菜品索引
    if "prev_result_len" not in st.session_state:
        st.session_state.prev_result_len = 0  # 用于检测列表长度变化，重置编辑状态
    
    # ==================== 获取分类数据 ====================
    categories = get_categories()
    category_names = ["主食", "热菜", "凉菜", "汤类", "减肥专栏"]  # 默认分类列表，用于修改按钮
    
    # ==================== 检测列表长度变化，重置编辑状态 ====================
    current_len = len(st.session_state.ai_global_result)
    if st.session_state.prev_result_len != current_len:
        st.session_state.editing_category_idx = None
        st.session_state.prev_result_len = current_len
    
    # ==================== 左右两栏布局 ====================
    col_left, col_right = st.columns([1.2, 3])
    
    # ==================== 左侧：分类管理 ====================
    with col_left:
        st.markdown("**📋 分类管理**")
        
        if not categories:
            st.info("暂无分类，请先添加")
        else:
            for cat_id, cat_name, icon, sort_order in categories:
                conn = pymysql.connect(**DB_CONFIG)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM recipes WHERE category_id = %s", (cat_id,))
                count = cursor.fetchone()[0]
                conn.close()
                
                col_cat, col_btn1, col_btn2 = st.columns([3, 0.6, 0.6])
                with col_cat:
                    if st.button(f"{icon} {cat_name} ({count})", key=f"cat_{cat_id}", use_container_width=True):
                        st.session_state.selected_category_id = cat_id
                        st.session_state.from_category_click = True
                        st.rerun()
                with col_btn1:
                    if st.button("✏️", key=f"edit_cat_{cat_id}", help="修改分类名称"):
                        st.session_state.edit_category_id = cat_id
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️", key=f"del_cat_{cat_id}", help="删除分类及该分类下所有菜"):
                        if count > 0:
                            st.warning(f"该分类下有 {count} 道菜，删除分类将同时删除这些菜！")
                        if st.button(f"确认删除 {cat_name}", key=f"confirm_del_cat_{cat_id}"):
                            delete_category(cat_id)
                            if st.session_state.selected_category_id == cat_id:
                                st.session_state.selected_category_id = None
                            st.rerun()
                
                if st.session_state.edit_category_id == cat_id:
                    new_name = st.text_input("新分类名称", value=cat_name, key=f"new_cat_name_{cat_id}")
                    col_save, col_cancel = st.columns(2)
                    with col_save:
                        if st.button("保存", key=f"save_cat_{cat_id}"):
                            if new_name and new_name.strip():
                                update_category(cat_id, new_name.strip())
                                st.session_state.edit_category_id = None
                                st.rerun()
                            else:
                                st.error("分类名称不能为空")
                    with col_cancel:
                        if st.button("取消", key=f"cancel_cat_{cat_id}"):
                            st.session_state.edit_category_id = None
                            st.rerun()
                
                st.divider()
        
        # 新增分类
        st.markdown("**➕ 新增分类**")
        new_cat_name = st.text_input("分类名称", key="new_cat_name", placeholder="输入新分类名称")
        new_cat_icon = st.text_input("图标（选填）", key="new_cat_icon", placeholder="如：🍳", value="📋")
        if st.button("添加分类", key="add_category_btn"):
            if new_cat_name and new_cat_name.strip():
                add_category(new_cat_name.strip(), new_cat_icon or "📋")
                st.rerun()
            else:
                st.error("请输入分类名称")
    
    # ==================== 右侧：内容区 ====================
    with col_right:
        # ==================== 未选中分类 ====================
        if st.session_state.selected_category_id is None:
            # ===== AI 推荐菜 =====
            with st.expander("🤖 AI 推荐菜", expanded=False):
                ai_mode = st.radio(
                    "选择模式",
                    ["🧠 按食材推荐", "🔍 按菜名查询"],
                    horizontal=True,
                    key="ai_mode_radio"
                )
                st.session_state.ai_mode = "食材推荐" if ai_mode == "🧠 按食材推荐" else "菜名查询"
                
                # ===== 输入区 =====
                if st.session_state.ai_mode == "食材推荐":
                    count = st.slider("菜品数量", min_value=1, max_value=10, value=5, key="ai_count_right")
                    ai_input = st.text_input("输入食材（用中文逗号或空格分隔）", key="ai_ingredients_right", placeholder="例如：土豆,鸡蛋")
                else:
                    count = st.slider("菜品数量", min_value=1, max_value=5, value=1, key="ai_variant_count")
                    ai_input = st.text_input("输入菜名", key="ai_dish_name", placeholder="例如：番茄炒蛋")
                
                # ===== 推荐和换一批按钮 =====
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("推荐", key="ai_recommend_btn"):
                        if not ai_input.strip():
                            st.error("请输入内容")
                        else:
                            dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
                            if not dashscope.api_key:
                                st.error("未找到 API Key，请检查 .env 文件")
                            else:
                                # 清空旧的推荐列表
                                st.session_state.ai_global_result = []
                                st.session_state.recommended_names = []
                                st.session_state.editing_category_idx = None
                                with st.spinner("AI 正在思考..."):
                                    if st.session_state.ai_mode == "食材推荐":
                                        prompt = f"""你是一个厨艺高超的AI厨师。请根据以下食材推荐 {count} 道菜（必须严格生成 {count} 道，不要多也不要少）：
食材：{ai_input}

请按以下格式返回，每道菜之间用"---"分隔：
菜名：XXX（如果是变体请注明，如 番茄炒蛋 - 家常版）
类别：XXX（从以下选择：主食、热菜、凉菜、汤类、减肥专栏）
食材：XXX, XXX, XXX（请标注精确用量，按两人份，食材要详细到克、毫升、个等）
做法：
1. XXX（详细步骤，包括火候、时间、状态判断，越详细越好）
---
（下一道菜）
"""
                                    else:
                                        prompt = f"""请提供菜名《{ai_input}》的 {count} 个不同版本的详细做法（必须严格生成 {count} 个版本），每个版本可以有不同的口味变化，但菜名请统一为“{ai_input}”，后面加括号注明特色（如“（酸甜口味）”、“（少油版）”等），不要使用“家常版”、“快手版”等字样作为菜名后缀。要求每个版本都包含食材用量（按两人份）和详细步骤，并为每个版本指定一个类别（主食、热菜、凉菜、汤类、减肥专栏）。

请按以下格式返回，每个版本之间用"---"分隔：
菜名：{ai_input}（特色描述）
类别：XXX
食材：XXX, XXX, XXX（请标注精确用量，按两人份，食材要详细到克、毫升、个等）
做法：
1. XXX（详细步骤，包括火候、时间、状态判断，越详细越好）
---
菜名：{ai_input}（另一个特色描述）
类别：XXX
食材：XXX, XXX, XXX
做法：
1. XXX
---
（以此类推）
"""
                                    try:
                                        response = Generation.call(
                                            model="qwen-turbo",
                                            messages=[{"role": "user", "content": prompt}],
                                            result_format="message"
                                        )
                                        if response.status_code == 200:
                                            content = response.output.choices[0].message.content
                                            recipes = parse_multiple_recipes(content)
                                            if recipes:
                                                # 如果 AI 返回的数量多于 count，截取前 count 个
                                                if len(recipes) > count:
                                                    recipes = recipes[:count]
                                                # 记录所有菜名
                                                for r in recipes:
                                                    if r["name"] not in st.session_state.recommended_names:
                                                        st.session_state.recommended_names.append(r["name"])
                                                st.session_state.ai_global_result = recipes
                                                st.session_state.ai_global_raw = None
                                            else:
                                                st.session_state.ai_global_raw = content
                                            st.rerun()
                                        else:
                                            st.error(f"AI 推荐失败：{response.message}")
                                    except Exception as e:
                                        st.error(f"AI 推荐出错：{e}")
                
                with col_btn2:
                    if st.button("🔄 换一批", key="ai_refresh_btn"):
                        if not ai_input.strip():
                            st.error("请先输入内容")
                        else:
                            dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
                            if not dashscope.api_key:
                                st.error("未找到 API Key，请检查 .env 文件")
                            else:
                                with st.spinner("AI 正在思考..."):
                                    # 排除已推荐菜名
                                    exclude_names = st.session_state.recommended_names
                                    exclude_note = ""
                                    if exclude_names:
                                        exclude_note = f"\n请不要再推荐以下菜品：{', '.join(exclude_names)}"
                                    
                                    if st.session_state.ai_mode == "食材推荐":
                                        count = st.session_state.get("ai_count_right", 5)
                                        prompt = f"""你是一个厨艺高超的AI厨师。请根据以下食材推荐 {count} 道菜（必须严格生成 {count} 道，不要多也不要少）：
食材：{ai_input}{exclude_note}

请按以下格式返回，每道菜之间用"---"分隔：
菜名：XXX（如果是变体请注明，如 番茄炒蛋 - 家常版）
类别：XXX（从以下选择：主食、热菜、凉菜、汤类、减肥专栏）
食材：XXX, XXX, XXX（请标注精确用量，按两人份，食材要详细到克、毫升、个等）
做法：
1. XXX（详细步骤，包括火候、时间、状态判断，越详细越好）
---
（下一道菜）
"""
                                    else:
                                        count = st.session_state.get("ai_variant_count", 1)
                                        prompt = f"""请提供菜名《{ai_input}》的 {count} 个不同版本的详细做法（必须严格生成 {count} 个版本），每个版本可以有不同的口味变化，但菜名请统一为“{ai_input}”，后面加括号注明特色（如“（酸甜口味）”、“（少油版）”等），不要使用“家常版”、“快手版”等字样作为菜名后缀。要求每个版本都包含食材用量（按两人份）和详细步骤，并为每个版本指定一个类别（主食、热菜、凉菜、汤类、减肥专栏）。{exclude_note}

请按以下格式返回，每个版本之间用"---"分隔：
菜名：{ai_input}（特色描述）
类别：XXX
食材：XXX, XXX, XXX（请标注精确用量，按两人份，食材要详细到克、毫升、个等）
做法：
1. XXX（详细步骤，包括火候、时间、状态判断，越详细越好）
---
菜名：{ai_input}（另一个特色描述）
类别：XXX
食材：XXX, XXX, XXX
做法：
1. XXX
---
（以此类推）
"""
                                    try:
                                        response = Generation.call(
                                            model="qwen-turbo",
                                            messages=[{"role": "user", "content": prompt}],
                                            result_format="message"
                                        )
                                        if response.status_code == 200:
                                            content = response.output.choices[0].message.content
                                            recipes = parse_multiple_recipes(content)
                                            if recipes:
                                                # 如果 AI 返回的数量多于 count，截取前 count 个
                                                if len(recipes) > count:
                                                    recipes = recipes[:count]
                                                # 记录新菜名到推荐历史
                                                for r in recipes:
                                                    if r["name"] not in st.session_state.recommended_names:
                                                        st.session_state.recommended_names.append(r["name"])
                                                # 追加到现有列表
                                                if st.session_state.ai_global_result is None:
                                                    st.session_state.ai_global_result = []
                                                st.session_state.ai_global_result.extend(recipes)
                                                st.session_state.ai_global_raw = None
                                            else:
                                                st.session_state.ai_global_raw = content
                                            st.rerun()
                                        else:
                                            st.error(f"AI 推荐失败：{response.message}")
                                    except Exception as e:
                                        st.error(f"AI 推荐出错：{e}")
                
                # ===== 显示推荐结果 =====
                if st.session_state.ai_global_result:
                    result_list = st.session_state.ai_global_result
                    st.divider()
                    
                    # 标题和关闭按钮同一行
                    col_title, col_close = st.columns([5, 1])
                    with col_title:
                        st.subheader(f"📋 推荐结果（共 {len(result_list)} 道）")
                        if st.session_state.recommended_names and st.session_state.ai_mode == "食材推荐":
                            st.caption(f"已排除：{', '.join(st.session_state.recommended_names)}")
                    with col_close:
                        if st.button("❌ 关闭", key="close_ai_result"):
                            st.session_state.ai_global_result = []
                            st.session_state.ai_global_raw = None
                            st.session_state.editing_category_idx = None
                            st.rerun()
                    
                    # 遍历显示每道菜
                    for idx, recipe in enumerate(result_list):
                        with st.expander(f"**{recipe['name']}**"):
                            # 显示类别，带修改按钮
                            col_cat, col_edit = st.columns([3, 1])
                            with col_cat:
                                st.markdown(f"**类别：{recipe['category']}**")
                            with col_edit:
                                # 修改类别按钮，使用唯一 key
                                if st.button("✏️ 修改", key=f"edit_cat_{idx}_{recipe['name']}"):
                                    st.session_state.editing_category_idx = idx
                                    st.rerun()
                            
                            # 如果当前正在修改此菜的类别
                            if st.session_state.editing_category_idx == idx:
                                # 提供下拉选择新类别
                                new_cat = st.selectbox(
                                    "选择新类别",
                                    options=category_names,
                                    index=category_names.index(recipe['category']) if recipe['category'] in category_names else 0,
                                    key=f"new_cat_select_{idx}_{recipe['name']}"
                                )
                                col_save_cat, col_cancel_cat = st.columns(2)
                                with col_save_cat:
                                    if st.button("保存类别", key=f"save_cat_{idx}_{recipe['name']}"):
                                        # 更新当前菜品的类别
                                        st.session_state.ai_global_result[idx]['category'] = new_cat
                                        st.session_state.editing_category_idx = None
                                        st.rerun()
                                with col_cancel_cat:
                                    if st.button("取消", key=f"cancel_cat_{idx}_{recipe['name']}"):
                                        st.session_state.editing_category_idx = None
                                        st.rerun()
                            
                            st.markdown(f"**食材**：\n{recipe['ingredients']}")
                            st.markdown(f"**做法**：\n{recipe['steps']}")
                            
                            # 添加和跳过按钮
                            if categories:
                                col_confirm, col_skip = st.columns(2)
                                with col_confirm:
                                    if st.button(f"✅ 添加此菜", key=f"confirm_ai_{idx}_{recipe['name']}"):
                                        # 将类别名称转换为 category_id
                                        cat_name_to_id = {cat[1]: cat[0] for cat in categories}  # categories 是 (id, name, icon, sort_order)
                                        cat_id = cat_name_to_id.get(recipe['category'])
                                        if cat_id is None:
                                            st.error(f"类别“{recipe['category']}”不存在，请先在左侧添加该分类")
                                        else:
                                            add_recipe(recipe['name'], recipe['ingredients'], recipe['steps'], cat_id)
                                            st.session_state.ai_global_result.pop(idx)
                                            st.success(f"✅ 已添加 {recipe['name']}")
                                            st.rerun()
                                with col_skip:
                                    if st.button(f"❌ 跳过", key=f"skip_ai_{idx}_{recipe['name']}"):
                                        st.session_state.ai_global_result.pop(idx)
                                        st.rerun()
                            else:
                                st.warning("请先在左侧添加分类")
                
                elif st.session_state.ai_global_raw is not None:
                    raw = st.session_state.ai_global_raw
                    st.divider()
                    # 关闭按钮同样适用于原始内容
                    col_title, col_close = st.columns([5, 1])
                    with col_title:
                        st.warning("⚠️ AI 返回格式未能自动解析，以下是原始内容，您可以手动整理后添加")
                    with col_close:
                        if st.button("❌ 关闭", key="close_ai_raw"):
                            st.session_state.ai_global_raw = None
                            st.rerun()
                    st.code(raw, language="text")
                    with st.form("manual_add_from_ai"):
                        st.text_input("菜名", value=ai_input, key="manual_ai_name")
                        st.text_area("食材（含用量）", height=100, key="manual_ai_ingredients", placeholder="请从上方内容中提取食材")
                        st.text_area("做法", height=150, key="manual_ai_steps", value=raw, placeholder="做法内容")
                        time_est = st.text_input("预计用时（分钟）", placeholder="30", key="manual_ai_time")
                        difficulty = st.selectbox("难度", ["", "简单", "中等", "困难"], key="manual_ai_diff")
                        if categories:
                            cat_options = {cat_id: f"{icon} {name}" for cat_id, name, icon, _ in categories}
                            cat_choice = st.selectbox("所属分类", options=list(cat_options.keys()), format_func=lambda x: cat_options.get(x, "未分类"), key="manual_ai_cat")
                        else:
                            cat_choice = None
                            st.warning("请先在左侧添加分类")
                        submitted = st.form_submit_button("💾 手动添加此菜")
                        if submitted:
                            if cat_choice is None:
                                st.error("请先添加分类")
                            else:
                                name = st.session_state.get("manual_ai_name", "")
                                ingredients = st.session_state.get("manual_ai_ingredients", "")
                                steps = st.session_state.get("manual_ai_steps", "")
                                if not name or not ingredients or not steps:
                                    st.error("请填写完整信息（菜名、食材、做法）")
                                else:
                                    add_recipe(name, ingredients, steps, cat_choice, time_est, difficulty)
                                    st.session_state.ai_global_raw = None
                                    st.success(f"✅ 已添加 {name}")
                                    st.rerun()
            
            # ===== 新增菜 =====
            with st.expander("➕ 新增菜", expanded=True):
                input_mode = st.radio("选择输入方式", ["📝 手动输入", "📷 上传图片识别"], horizontal=True, key="input_mode")
                
                if input_mode == "📝 手动输入":
                    with st.form("add_recipe_right"):
                        name = st.text_input("菜名")
                        ingredients = st.text_area("食材（含用量）", height=120, placeholder="例如：土豆 300g\n鸡蛋 2个\n盐 5g\n生抽 10ml")
                        steps = st.text_area("做法", height=150, placeholder="1. 土豆去皮切丝...\n2. 热锅倒油...")
                        time_est = st.text_input("预计用时（分钟）", placeholder="30")
                        difficulty = st.selectbox("难度", ["", "简单", "中等", "困难"])
                        cat_options = {cat_id: f"{icon} {name}" for cat_id, name, icon, _ in categories}
                        if cat_options:
                            cat_choice = st.selectbox("所属分类", options=list(cat_options.keys()), format_func=lambda x: cat_options.get(x, "未分类"))
                        else:
                            cat_choice = None
                            st.warning("请先在左侧添加分类")
                        submitted = st.form_submit_button("添加")
                        if submitted:
                            if not name or not ingredients or not steps:
                                st.error("请填写完整信息")
                            elif cat_choice is None:
                                st.error("请先添加分类")
                            else:
                                add_recipe(name, ingredients, steps, cat_choice, time_est, difficulty)
                                st.success(f"✅ 已添加 {name}")
                                st.rerun()
                
                else:  # 图片识别模式
                    st.markdown("**上传包含菜名和做法的截图（如抖音截图）**")
                    uploaded_file = st.file_uploader("选择图片", type=["jpg", "jpeg", "png", "webp"], key="recipe_image_upload")
                    
                    if uploaded_file is not None:
                        st.image(uploaded_file, width=300)
                        
                        if st.button("🔍 识别图片", key="recognize_image"):
                            with st.spinner("AI 正在识别图片..."):
                                dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
                                if not dashscope.api_key:
                                    st.error("未找到 API Key，请检查 .env 文件")
                                else:
                                    img_bytes = uploaded_file.read()
                                    img_base64 = base64.b64encode(img_bytes).decode('utf-8')
                                    img_type = uploaded_file.type.split('/')[-1] if uploaded_file.type else 'jpeg'
                                    img_url = f"data:image/{img_type};base64,{img_base64}"
                                    
                                    prompt = """请识别这张图片中的菜谱信息。如果图片中包含菜名、食材和做法，请按以下格式返回：
菜名：XXX
类别：XXX（从以下选择：主食、热菜、凉菜、汤类、减肥专栏）
食材：XXX, XXX, XXX（请标注精确用量，按两人份，食材要详细到克、毫升、个等）
做法：
1. XXX（详细步骤，包括火候、时间、状态判断，越详细越好）

如果图片中没有菜谱信息，请返回：未识别到菜谱信息"""
                                    
                                    try:
                                        response = Generation.call(
                                            model="qwen-vl-plus",
                                            messages=[
                                                {
                                                    "role": "user",
                                                    "content": [
                                                        {"image": img_url},
                                                        {"text": prompt}
                                                    ]
                                                }
                                            ],
                                            result_format="message"
                                        )
                                        if response.status_code == 200:
                                            content = response.output.choices[0].message.content
                                            st.session_state.image_recog_result = content
                                            st.rerun()
                                        else:
                                            st.error(f"识别失败：{response.message}")
                                    except Exception as e:
                                        st.error(f"识别出错：{e}")
                        
                        if st.session_state.image_recog_result:
                            result_text = st.session_state.image_recog_result
                            st.divider()
                            st.subheader("📋 识别结果")
                            st.text(result_text)
                            
                            lines = result_text.strip().split("\n")
                            recog_name = ""
                            recog_ingredients = ""
                            recog_steps = ""
                            recog_category = ""
                            current_section = None
                            for line in lines:
                                line = line.strip()
                                if not line:
                                    continue
                                if "菜名" in line:
                                    if "：" in line:
                                        recog_name = line.split("：")[-1].strip()
                                    elif ":" in line:
                                        recog_name = line.split(":")[-1].strip()
                                elif "类别" in line:
                                    if "：" in line:
                                        recog_category = line.split("：")[-1].strip()
                                    elif ":" in line:
                                        recog_category = line.split(":")[-1].strip()
                                elif "食材" in line:
                                    if "：" in line:
                                        recog_ingredients = line.split("：")[-1].strip()
                                    elif ":" in line:
                                        recog_ingredients = line.split(":")[-1].strip()
                                    else:
                                        recog_ingredients = line
                                elif "做法" in line:
                                    if "：" in line:
                                        recog_steps = line.split("：")[-1].strip()
                                    elif ":" in line:
                                        recog_steps = line.split(":")[-1].strip()
                                    else:
                                        recog_steps = line
                                elif recog_steps and recog_name and recog_ingredients:
                                    recog_steps += "\n" + line
                            
                            if recog_name and recog_ingredients and recog_steps:
                                st.success("✅ 识别成功！请确认信息后点击「保存到菜单」")
                                with st.form("add_from_image"):
                                    st.text_input("菜名", value=recog_name, key="img_name")
                                    st.text_area("食材", value=recog_ingredients, height=120, key="img_ingredients")
                                    st.text_area("做法", value=recog_steps, height=150, key="img_steps")
                                    time_est = st.text_input("预计用时（分钟）", placeholder="30", key="img_time")
                                    difficulty = st.selectbox("难度", ["", "简单", "中等", "困难"], key="img_diff")
                                    # 类别选择
                                    cat_options = {cat_id: f"{icon} {name}" for cat_id, name, icon, _ in categories}
                                    if cat_options:
                                        # 如果识别出类别，尝试匹配
                                        if recog_category and recog_category in [name for _, name, _, _ in categories]:
                                            default_cat = next(cat_id for cat_id, name, _, _ in categories if name == recog_category)
                                        else:
                                            default_cat = list(cat_options.keys())[0] if cat_options else None
                                        cat_choice = st.selectbox("所属分类", options=list(cat_options.keys()), format_func=lambda x: cat_options.get(x, "未分类"), key="img_cat", index=list(cat_options.keys()).index(default_cat) if default_cat in cat_options else 0)
                                    else:
                                        cat_choice = None
                                        st.warning("请先在左侧添加分类")
                                    submitted = st.form_submit_button("💾 保存到菜单")
                                    if submitted:
                                        if cat_choice is None:
                                            st.error("请先添加分类")
                                        else:
                                            add_recipe(recog_name, recog_ingredients, recog_steps, cat_choice, time_est, difficulty)
                                            st.session_state.image_recog_result = None
                                            st.success(f"✅ 已添加 {recog_name}")
                                            st.rerun()
                            else:
                                st.info("识别结果中未找到完整的菜谱信息，请手动输入或重试")
        
        # ==================== 已选中分类 ====================
        else:
            cat_info = get_category_name(st.session_state.selected_category_id)
            if cat_info and cat_info[0]:
                cat_name, icon = cat_info
                st.markdown(f"### {icon} {cat_name}")
                
                if st.button("← 返回所有分类", key="back_to_categories"):
                    st.session_state.selected_category_id = None
                    st.session_state.from_category_click = False
                    st.rerun()
                
                recipes = get_recipes_by_category(st.session_state.selected_category_id)
                
                if recipes:
                    for recipe_id, name, ingredients, steps, cook_count, time_est, difficulty in recipes:
                        with st.expander(f"**{name}**"):
                            st.markdown(f"**食材**：\n{ingredients}")
                            st.markdown(f"**做法**：\n{steps}")
                            if time_est:
                                st.caption(f"⏱️ 约 {time_est} 分钟")
                            if difficulty:
                                st.caption(f"📊 难度：{difficulty}")
                            
                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                if st.button("✅ 做过", key=f"cook_{recipe_id}"):
                                    increment_cook_count(recipe_id)
                                    st.success("已记录")
                                    st.rerun()
                            with col2:
                                if st.button("✏️ 修改", key=f"edit_recipe_{recipe_id}"):
                                    st.session_state.edit_recipe_id = recipe_id
                                    st.rerun()
                            with col3:
                                if st.button("🗑️ 删除", key=f"del_recipe_{recipe_id}"):
                                    delete_recipe(recipe_id)
                                    st.rerun()
                            with col4:
                                if cook_count:
                                    st.caption(f"已做 {cook_count} 次")
                            
                            if st.session_state.edit_recipe_id == recipe_id:
                                st.divider()
                                st.subheader(f"✏️ 修改 {name}")
                                with st.form(f"edit_recipe_form_{recipe_id}"):
                                    new_name = st.text_input("菜名", value=name)
                                    new_ingredients = st.text_area("食材", value=ingredients, height=120)
                                    new_steps = st.text_area("做法", value=steps, height=150)
                                    new_time = st.text_input("预计用时", value=time_est or "")
                                    new_diff = st.selectbox("难度", ["", "简单", "中等", "困难"], index=0 if not difficulty else ["", "简单", "中等", "困难"].index(difficulty))
                                    cat_options = {cid: f"{cicon} {cname}" for cid, cname, cicon, _ in categories}
                                    if cat_options:
                                        new_cat = st.selectbox("所属分类", options=list(cat_options.keys()), 
                                                              format_func=lambda x: cat_options.get(x, "未分类"),
                                                              index=list(cat_options.keys()).index(st.session_state.selected_category_id) if st.session_state.selected_category_id in cat_options else 0)
                                    else:
                                        new_cat = st.session_state.selected_category_id
                                    col_save, col_cancel = st.columns(2)
                                    with col_save:
                                        if st.form_submit_button("保存修改"):
                                            if new_name and new_name.strip():
                                                update_recipe(recipe_id, new_name.strip(), new_ingredients, new_steps, new_cat, new_time, new_diff)
                                                st.session_state.edit_recipe_id = None
                                                st.success("✅ 已更新")
                                                st.rerun()
                                            else:
                                                st.error("菜名不能为空")
                                    with col_cancel:
                                        if st.form_submit_button("取消"):
                                            st.session_state.edit_recipe_id = None
                                            st.rerun()
                else:
                    st.info(f"📭 {cat_name} 分类下还没有菜，快来添加吧！")
            else:
                st.error("分类不存在，请重新选择")
                st.session_state.selected_category_id = None
                st.rerun()
    
    # ==================== 返回首页按钮（底部） ====================
    st.divider()
    if st.button("🏠 返回首页", key="back_home_cook"):
        st.session_state.page = "home"
        st.session_state.selected_category_id = None
        st.session_state.ai_global_result = []
        st.session_state.ai_global_raw = None
        st.session_state.recommended_names = []
        st.session_state.image_recog_result = None
        st.session_state.editing_category_idx = None
        st.rerun()

# ==================== 旅行板块 ====================
def travel_page():
    import folium
    from streamlit_folium import st_folium
    import datetime
    import collections
    
    # ==================== 如果正在查看城市详情，直接渲染详情页 ====================
    if "city_detail" in st.query_params:
        city_name = st.query_params["city_detail"]
        
        st.markdown(f"# 📋 {city_name} 详情")
        st.caption("点击下方「返回旅行地图」回到地图页面")
        
        if st.button("← 返回旅行地图", key="back_to_map_from_detail"):
            st.query_params.clear()
            st.rerun()
        
        # 加载城市基本信息
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT province, visit_date, plan_date FROM travel_records WHERE city_name = %s", (city_name,))
        record = cursor.fetchone()
        conn.close()
        
        if record:
            province, visit_date, plan_date = record
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**省份**：{province}")
                if visit_date:
                    st.write(f"**旅行日期**：{visit_date.strftime('%Y-%m-%d')}")
            with col2:
                if plan_date:
                    st.write(f"**计划日期**：{plan_date.strftime('%Y-%m-%d')}")
                st.write(f"**状态**：{'已去' if visit_date else '计划中'}")
        
        # 实际游玩路线
        st.subheader("🗺️ 实际游玩路线")
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT route FROM city_details WHERE city_name = %s", (city_name,))
        route_row = cursor.fetchone()
        conn.close()
        current_route = route_row[0] if route_row and route_row[0] else ""
        
        new_route = st.text_area("编辑游玩路线", value=current_route, height=150, placeholder="记录你的实际行程...")
        if st.button("保存路线", key="save_route_detail"):
            conn = pymysql.connect(**DB_CONFIG)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO city_details (city_name, route) VALUES (%s, %s) ON DUPLICATE KEY UPDATE route = %s",
                (city_name, new_route, new_route)
            )
            conn.commit()
            conn.close()
            st.success("✅ 路线已保存")
            st.rerun()
        
        # 照片墙
        st.subheader("📸 照片墙")
        upload_option = st.radio("选择上传方式", ["本地文件", "图片链接"], horizontal=True, key="detail_upload_option")
        if upload_option == "本地文件":
            uploaded_files = st.file_uploader("选择照片", type=["jpg", "jpeg", "png", "gif"], accept_multiple_files=True, key="detail_file_uploader")
            if uploaded_files and st.button("上传照片", key="detail_upload_local"):
                import os
                upload_dir = "static/uploads"
                if not os.path.exists(upload_dir):
                    os.makedirs(upload_dir)
                for file in uploaded_files:
                    file_path = os.path.join(upload_dir, f"{city_name}_{file.name}")
                    with open(file_path, "wb") as f:
                        f.write(file.getbuffer())
                    conn = pymysql.connect(**DB_CONFIG)
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO city_photos (city_name, photo_path, photo_type, shoot_date) VALUES (%s, %s, %s, %s)",
                        (city_name, file_path, "local", datetime.date.today())
                    )
                    conn.commit()
                    conn.close()
                st.success("✅ 照片已上传")
                st.rerun()
        else:
            photo_url = st.text_input("图片链接（URL）", key="detail_photo_url")
            shoot_date = st.date_input("拍摄日期", value=datetime.date.today(), key="detail_shoot_date")
            if photo_url and st.button("添加照片", key="detail_add_url_photo"):
                conn = pymysql.connect(**DB_CONFIG)
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO city_photos (city_name, photo_path, photo_type, shoot_date) VALUES (%s, %s, %s, %s)",
                    (city_name, photo_url, "url", shoot_date)
                )
                conn.commit()
                conn.close()
                st.success("✅ 照片已添加")
                st.rerun()
        
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT photo_path, photo_type, shoot_date FROM city_photos WHERE city_name = %s ORDER BY shoot_date DESC", (city_name,))
        photos = cursor.fetchall()
        conn.close()
        
        if photos:
            grouped = collections.defaultdict(list)
            for path, ptype, date in photos:
                grouped[date.strftime("%Y-%m-%d") if date else "未分类"].append((path, ptype))
            for date_str, items in sorted(grouped.items(), reverse=True):
                st.caption(f"📅 {date_str}")
                cols = st.columns(4)
                for idx, (path, ptype) in enumerate(items):
                    with cols[idx % 4]:
                        if ptype == "local":
                            st.image(path, use_container_width=True)
                        else:
                            st.image(path, use_container_width=True)
                        if st.button(f"🔍 查看大图", key=f"detail_img_{date_str}_{idx}_{path}"):
                            st.session_state["large_image"] = path
                            st.session_state["large_image_type"] = ptype
                            st.rerun()
        else:
            st.info("暂无照片")
        
        if "large_image" in st.session_state and st.session_state["large_image"]:
            st.divider()
            st.subheader("🖼️ 大图查看")
            st.image(st.session_state["large_image"], use_container_width=True)
            if st.button("关闭大图", key="detail_close_large_image"):
                st.session_state["large_image"] = None
                st.rerun()
        
        if st.button("← 返回旅行地图", key="back_to_map_from_detail_bottom"):
            st.query_params.clear()
            st.rerun()
        
        st.stop()
    
    # ==================== 旅行地图页面 ====================
    col_title, col_btn = st.columns([6, 1])
    with col_title:
        st.markdown("# ✈️ 我们的旅行地图")
    with col_btn:
        if st.button("🏠 返回首页", key="back_home_travel"):
            st.session_state.page = "home"
            st.rerun()
    
    # ==================== 城市坐标 + 省份映射 ====================
    city_coords = {
        "北京": [39.9042, 116.4074, "北京"],
        "天津": [39.0842, 117.2009, "天津"],
        "上海": [31.2304, 121.4737, "上海"],
        "重庆": [29.4316, 106.9123, "重庆"],
        "石家庄": [38.0423, 114.5149, "河北省"],
        "唐山": [39.6300, 118.1800, "河北省"],
        "秦皇岛": [39.9354, 119.5897, "河北省"],
        "邯郸": [36.6000, 114.4900, "河北省"],
        "保定": [38.8700, 115.4800, "河北省"],
        "张家口": [40.7600, 114.8800, "河北省"],
        "承德": [40.9700, 117.9300, "河北省"],
        "沧州": [38.3100, 116.8600, "河北省"],
        "廊坊": [39.5200, 116.7000, "河北省"],
        "衡水": [37.7300, 115.6800, "河北省"],
        "邢台": [37.0700, 114.4900, "河北省"],
        "太原": [37.8706, 112.5489, "山西省"],
        "大同": [40.0900, 113.2900, "山西省"],
        "阳泉": [37.8500, 113.5800, "山西省"],
        "长治": [36.1800, 113.1000, "山西省"],
        "晋城": [35.4900, 112.8500, "山西省"],
        "朔州": [39.3300, 112.4300, "山西省"],
        "晋中": [37.6800, 112.7500, "山西省"],
        "运城": [35.0300, 110.9800, "山西省"],
        "忻州": [38.4200, 112.7300, "山西省"],
        "临汾": [36.0800, 111.5100, "山西省"],
        "吕梁": [37.5200, 111.1400, "山西省"],
        "韩城": [35.4800, 110.4500, "山西省"],
        "呼和浩特": [40.8424, 111.7490, "内蒙古自治区"],
        "包头": [40.6500, 109.8300, "内蒙古自治区"],
        "乌海": [39.6700, 106.8200, "内蒙古自治区"],
        "赤峰": [42.2700, 118.9600, "内蒙古自治区"],
        "通辽": [43.6500, 122.2700, "内蒙古自治区"],
        "鄂尔多斯": [39.6000, 109.7800, "内蒙古自治区"],
        "呼伦贝尔": [49.2100, 119.7700, "内蒙古自治区"],
        "巴彦淖尔": [40.7400, 107.3800, "内蒙古自治区"],
        "乌兰察布": [40.9300, 113.1200, "内蒙古自治区"],
        "沈阳": [41.8057, 123.4315, "辽宁省"],
        "大连": [38.9140, 121.6147, "辽宁省"],
        "鞍山": [41.1100, 122.9900, "辽宁省"],
        "抚顺": [41.8700, 123.9700, "辽宁省"],
        "本溪": [41.3000, 123.7600, "辽宁省"],
        "丹东": [40.1300, 124.3800, "辽宁省"],
        "锦州": [41.1200, 121.1400, "辽宁省"],
        "营口": [40.6700, 122.2300, "辽宁省"],
        "阜新": [42.0100, 121.6600, "辽宁省"],
        "辽阳": [41.2600, 123.1800, "辽宁省"],
        "盘锦": [41.1200, 122.0600, "辽宁省"],
        "铁岭": [42.2800, 123.7200, "辽宁省"],
        "朝阳": [41.5700, 120.4500, "辽宁省"],
        "葫芦岛": [40.7100, 120.8300, "辽宁省"],
        "长春": [43.8868, 125.3245, "吉林省"],
        "吉林": [43.8700, 126.5500, "吉林省"],
        "四平": [43.1600, 124.3700, "吉林省"],
        "辽源": [42.9000, 125.1400, "吉林省"],
        "通化": [41.7200, 125.9300, "吉林省"],
        "白山": [41.9400, 126.4200, "吉林省"],
        "松原": [45.1400, 124.8200, "吉林省"],
        "白城": [45.6200, 122.8300, "吉林省"],
        "哈尔滨": [45.8038, 126.5350, "黑龙江省"],
        "齐齐哈尔": [47.3500, 123.9700, "黑龙江省"],
        "鸡西": [45.3000, 130.9800, "黑龙江省"],
        "鹤岗": [47.3500, 130.2900, "黑龙江省"],
        "双鸭山": [46.6300, 131.1500, "黑龙江省"],
        "大庆": [46.5800, 125.0300, "黑龙江省"],
        "伊春": [47.7200, 128.8300, "黑龙江省"],
        "佳木斯": [46.8100, 130.3600, "黑龙江省"],
        "七台河": [45.7700, 131.0000, "黑龙江省"],
        "牡丹江": [44.5800, 129.6000, "黑龙江省"],
        "黑河": [50.2400, 127.4800, "黑龙江省"],
        "绥化": [46.6300, 126.9900, "黑龙江省"],
        "南京": [32.0603, 118.7969, "江苏省"],
        "苏州": [31.2990, 120.5853, "江苏省"],
        "无锡": [31.4912, 120.3119, "江苏省"],
        "常州": [31.8100, 119.9700, "江苏省"],
        "徐州": [34.2600, 117.1800, "江苏省"],
        "南通": [32.0100, 120.8600, "江苏省"],
        "连云港": [34.5900, 119.1700, "江苏省"],
        "淮安": [33.5800, 119.0100, "江苏省"],
        "盐城": [33.3700, 120.1500, "江苏省"],
        "扬州": [32.4100, 119.4100, "江苏省"],
        "镇江": [32.2000, 119.4500, "江苏省"],
        "泰州": [32.4500, 119.9200, "江苏省"],
        "宿迁": [33.9600, 118.2900, "江苏省"],
        "杭州": [30.2741, 120.1551, "浙江省"],
        "宁波": [29.8683, 121.5439, "浙江省"],
        "温州": [27.9949, 120.6984, "浙江省"],
        "嘉兴": [30.7628, 120.7550, "浙江省"],
        "湖州": [30.8943, 120.0868, "浙江省"],
        "绍兴": [30.0303, 120.5802, "浙江省"],
        "金华": [29.0781, 119.6476, "浙江省"],
        "衢州": [28.9359, 118.8594, "浙江省"],
        "舟山": [30.0160, 122.2072, "浙江省"],
        "台州": [28.6564, 121.4208, "浙江省"],
        "丽水": [28.4676, 119.9231, "浙江省"],
        "合肥": [31.8206, 117.2272, "安徽省"],
        "芜湖": [31.3500, 118.3700, "安徽省"],
        "蚌埠": [32.9400, 117.3600, "安徽省"],
        "淮南": [32.6200, 116.9900, "安徽省"],
        "马鞍山": [31.7000, 118.4800, "安徽省"],
        "淮北": [33.9500, 116.7900, "安徽省"],
        "铜陵": [30.9400, 117.8100, "安徽省"],
        "安庆": [30.5300, 117.0400, "安徽省"],
        "黄山": [29.7100, 118.3100, "安徽省"],
        "滁州": [32.3200, 118.3100, "安徽省"],
        "阜阳": [32.8900, 115.8100, "安徽省"],
        "宿州": [33.6300, 116.9800, "安徽省"],
        "六安": [31.7300, 116.4900, "安徽省"],
        "亳州": [33.8400, 115.7700, "安徽省"],
        "池州": [30.6600, 117.4800, "安徽省"],
        "宣城": [30.9400, 118.7500, "安徽省"],
        "福州": [26.0745, 119.2965, "福建省"],
        "厦门": [24.4798, 118.0894, "福建省"],
        "莆田": [25.4300, 119.0100, "福建省"],
        "三明": [26.2600, 117.6300, "福建省"],
        "泉州": [24.8739, 118.6759, "福建省"],
        "漳州": [24.5100, 117.6500, "福建省"],
        "南平": [26.6400, 118.1700, "福建省"],
        "龙岩": [25.0700, 117.0100, "福建省"],
        "宁德": [26.6600, 119.5200, "福建省"],
        "南昌": [28.6820, 115.8579, "江西省"],
        "景德镇": [29.2700, 117.1900, "江西省"],
        "萍乡": [27.6200, 113.8500, "江西省"],
        "九江": [29.7100, 116.0000, "江西省"],
        "新余": [27.8000, 114.9300, "江西省"],
        "鹰潭": [28.2600, 117.0300, "江西省"],
        "赣州": [25.8200, 114.9300, "江西省"],
        "吉安": [27.1100, 114.9900, "江西省"],
        "宜春": [27.8100, 114.3800, "江西省"],
        "抚州": [27.9800, 116.3500, "江西省"],
        "上饶": [28.4500, 117.9700, "江西省"],
        "济南": [36.6512, 117.1201, "山东省"],
        "青岛": [36.0671, 120.3826, "山东省"],
        "淄博": [36.8131, 118.0550, "山东省"],
        "枣庄": [34.8100, 117.3200, "山东省"],
        "东营": [37.4300, 118.4900, "山东省"],
        "烟台": [37.4638, 121.4479, "山东省"],
        "潍坊": [36.7063, 119.1618, "山东省"],
        "济宁": [35.4148, 116.5872, "山东省"],
        "泰安": [36.2000, 117.0800, "山东省"],
        "威海": [37.5100, 122.1100, "山东省"],
        "日照": [35.3900, 119.5300, "山东省"],
        "临沂": [35.1049, 118.3564, "山东省"],
        "德州": [37.4500, 116.2900, "山东省"],
        "聊城": [36.4500, 115.9800, "山东省"],
        "滨州": [37.3800, 118.0300, "山东省"],
        "菏泽": [35.2300, 115.4800, "山东省"],
        "郑州": [34.7470, 113.6250, "河南省"],
        "开封": [34.7900, 114.3400, "河南省"],
        "洛阳": [34.6100, 112.4500, "河南省"],
        "平顶山": [33.7300, 113.2900, "河南省"],
        "安阳": [36.1000, 114.3500, "河南省"],
        "鹤壁": [35.8900, 114.2900, "河南省"],
        "新乡": [35.3000, 113.8700, "河南省"],
        "焦作": [35.2100, 113.2400, "河南省"],
        "濮阳": [35.7600, 115.0300, "河南省"],
        "许昌": [34.0300, 113.8500, "河南省"],
        "漯河": [33.5800, 114.0300, "河南省"],
        "三门峡": [34.7700, 111.2000, "河南省"],
        "南阳": [32.9900, 112.5200, "河南省"],
        "商丘": [34.4100, 115.6500, "河南省"],
        "信阳": [32.1200, 114.0700, "河南省"],
        "周口": [33.6300, 114.6500, "河南省"],
        "驻马店": [32.9800, 114.0200, "河南省"],
        "武汉": [30.5928, 114.3055, "湖北省"],
        "黄石": [30.2200, 115.0800, "湖北省"],
        "十堰": [32.6300, 110.7800, "湖北省"],
        "宜昌": [30.6900, 111.2800, "湖北省"],
        "襄阳": [32.0200, 112.1200, "湖北省"],
        "鄂州": [30.3900, 114.8800, "湖北省"],
        "荆门": [31.0300, 112.1900, "湖北省"],
        "孝感": [30.9200, 113.9100, "湖北省"],
        "荆州": [30.3300, 112.2300, "湖北省"],
        "黄冈": [30.4500, 114.8700, "湖北省"],
        "咸宁": [29.8300, 114.3200, "湖北省"],
        "随州": [31.6900, 113.3700, "湖北省"],
        "恩施": [30.2900, 109.4800, "湖北省"],
        "长沙": [28.2282, 112.9388, "湖南省"],
        "株洲": [27.8300, 113.1500, "湖南省"],
        "湘潭": [27.8200, 112.9700, "湖南省"],
        "衡阳": [26.8900, 112.5800, "湖南省"],
        "邵阳": [27.2400, 111.4600, "湖南省"],
        "岳阳": [29.3700, 113.1200, "湖南省"],
        "常德": [29.0400, 111.6800, "湖南省"],
        "张家界": [29.1200, 110.4700, "湖南省"],
        "益阳": [28.5900, 112.3300, "湖南省"],
        "郴州": [25.7700, 113.0300, "湖南省"],
        "永州": [26.4200, 111.6000, "湖南省"],
        "怀化": [27.5400, 109.9500, "湖南省"],
        "娄底": [27.7200, 111.9900, "湖南省"],
        "广州": [23.1291, 113.2644, "广东省"],
        "韶关": [24.8000, 113.6000, "广东省"],
        "深圳": [22.5431, 114.0579, "广东省"],
        "珠海": [22.2700, 113.5700, "广东省"],
        "汕头": [23.3700, 116.6700, "广东省"],
        "佛山": [23.0215, 113.1214, "广东省"],
        "江门": [22.5800, 113.0800, "广东省"],
        "湛江": [21.2100, 110.3600, "广东省"],
        "茂名": [21.6600, 110.9200, "广东省"],
        "肇庆": [23.0500, 112.4500, "广东省"],
        "惠州": [23.1100, 114.4100, "广东省"],
        "梅州": [24.2800, 116.1100, "广东省"],
        "汕尾": [22.7800, 115.3600, "广东省"],
        "河源": [23.7400, 114.6900, "广东省"],
        "阳江": [21.8500, 111.9700, "广东省"],
        "清远": [23.7000, 113.0100, "广东省"],
        "东莞": [23.0207, 113.7518, "广东省"],
        "中山": [22.5200, 113.3800, "广东省"],
        "潮州": [23.6600, 116.6300, "广东省"],
        "揭阳": [23.5400, 116.3700, "广东省"],
        "云浮": [22.9300, 112.0300, "广东省"],
        "南宁": [22.8170, 108.3665, "广西壮族自治区"],
        "柳州": [24.3200, 109.4100, "广西壮族自治区"],
        "桂林": [25.2700, 110.2900, "广西壮族自治区"],
        "梧州": [23.4800, 111.2700, "广西壮族自治区"],
        "北海": [21.4800, 109.1100, "广西壮族自治区"],
        "防城港": [21.6800, 108.3500, "广西壮族自治区"],
        "钦州": [21.9500, 108.6200, "广西壮族自治区"],
        "贵港": [23.1100, 109.5900, "广西壮族自治区"],
        "玉林": [22.6300, 110.1500, "广西壮族自治区"],
        "百色": [23.9000, 106.6100, "广西壮族自治区"],
        "贺州": [24.4100, 111.5400, "广西壮族自治区"],
        "河池": [24.6900, 108.0600, "广西壮族自治区"],
        "来宾": [23.7500, 109.2200, "广西壮族自治区"],
        "崇左": [22.4000, 107.3600, "广西壮族自治区"],
        "海口": [20.0174, 110.3492, "海南省"],
        "三亚": [18.2528, 109.5119, "海南省"],
        "儋州": [19.5200, 109.5800, "海南省"],
        "文昌": [19.6200, 110.7700, "海南省"],
        "琼海": [19.2400, 110.4800, "海南省"],
        "万宁": [18.8000, 110.3900, "海南省"],
        "东方": [19.1000, 108.6400, "海南省"],
        "成都": [30.5728, 104.0668, "四川省"],
        "自贡": [29.3500, 104.7700, "四川省"],
        "攀枝花": [26.5800, 101.7100, "四川省"],
        "泸州": [28.8700, 105.4300, "四川省"],
        "德阳": [31.1200, 104.3900, "四川省"],
        "绵阳": [31.4600, 104.7500, "四川省"],
        "广元": [32.4300, 105.8100, "四川省"],
        "遂宁": [30.5500, 105.5600, "四川省"],
        "内江": [29.5800, 105.0800, "四川省"],
        "乐山": [29.5800, 103.7600, "四川省"],
        "南充": [30.7900, 106.0800, "四川省"],
        "眉山": [30.0700, 103.8400, "四川省"],
        "宜宾": [28.7600, 104.6300, "四川省"],
        "广安": [30.4600, 106.6300, "四川省"],
        "达州": [31.2100, 107.5000, "四川省"],
        "雅安": [29.9800, 103.0000, "四川省"],
        "巴中": [31.8600, 106.7500, "四川省"],
        "资阳": [30.1100, 104.6400, "四川省"],
        "贵阳": [26.6477, 106.6302, "贵州省"],
        "六盘水": [26.5900, 104.8200, "贵州省"],
        "遵义": [27.7200, 106.9200, "贵州省"],
        "安顺": [26.2500, 105.9300, "贵州省"],
        "毕节": [27.3000, 105.2800, "贵州省"],
        "铜仁": [27.7300, 109.1900, "贵州省"],
        "昆明": [24.8801, 102.8329, "云南省"],
        "曲靖": [25.4900, 103.7900, "云南省"],
        "玉溪": [24.3500, 102.5200, "云南省"],
        "保山": [25.1200, 99.1600, "云南省"],
        "昭通": [27.3400, 103.7100, "云南省"],
        "丽江": [26.8600, 100.2300, "云南省"],
        "普洱": [22.7800, 100.9700, "云南省"],
        "临沧": [23.8800, 100.0800, "云南省"],
        "大理": [25.6100, 100.2800, "云南省"],
        "楚雄": [25.0400, 101.5400, "云南省"],
        "红河": [23.3600, 103.3600, "云南省"],
        "文山": [23.4000, 104.2100, "云南省"],
        "西双版纳": [21.9900, 100.7900, "云南省"],
        "拉萨": [29.6500, 91.1000, "西藏自治区"],
        "日喀则": [29.2700, 88.8800, "西藏自治区"],
        "昌都": [31.1400, 97.1800, "西藏自治区"],
        "林芝": [29.6700, 94.3600, "西藏自治区"],
        "山南": [29.2400, 91.7600, "西藏自治区"],
        "那曲": [31.4800, 92.0500, "西藏自治区"],
        "西安": [34.3416, 108.9398, "陕西省"],
        "铜川": [34.9000, 108.9800, "陕西省"],
        "宝鸡": [34.3700, 107.1500, "陕西省"],
        "咸阳": [34.3300, 108.7000, "陕西省"],
        "渭南": [34.5000, 109.5000, "陕西省"],
        "延安": [36.5900, 109.4800, "陕西省"],
        "汉中": [33.0700, 107.0200, "陕西省"],
        "榆林": [38.2800, 109.7300, "陕西省"],
        "安康": [32.6800, 109.0200, "陕西省"],
        "商洛": [33.8600, 109.9400, "陕西省"],
        "兰州": [36.0611, 103.8343, "甘肃省"],
        "嘉峪关": [39.7800, 98.2800, "甘肃省"],
        "金昌": [38.5000, 102.1800, "甘肃省"],
        "白银": [36.5400, 104.1700, "甘肃省"],
        "天水": [34.5800, 105.7200, "甘肃省"],
        "武威": [37.9300, 102.6400, "甘肃省"],
        "张掖": [38.9300, 100.4500, "甘肃省"],
        "平凉": [35.5400, 106.6800, "甘肃省"],
        "酒泉": [39.7400, 98.4900, "甘肃省"],
        "庆阳": [35.7300, 107.6300, "甘肃省"],
        "定西": [35.5800, 104.6200, "甘肃省"],
        "陇南": [33.3900, 104.9200, "甘肃省"],
        "西宁": [36.6171, 101.7782, "青海省"],
        "海东": [36.5000, 102.1000, "青海省"],
        "海北": [36.9500, 100.9000, "青海省"],
        "黄南": [35.5200, 102.0200, "青海省"],
        "海南": [36.2800, 100.6200, "青海省"],
        "果洛": [34.4700, 100.2400, "青海省"],
        "玉树": [33.0000, 97.0100, "青海省"],
        "海西": [37.3700, 97.3700, "青海省"],
        "银川": [38.4872, 106.2309, "宁夏回族自治区"],
        "石嘴山": [39.0400, 106.3800, "宁夏回族自治区"],
        "吴忠": [37.9900, 106.1900, "宁夏回族自治区"],
        "固原": [36.0000, 106.2800, "宁夏回族自治区"],
        "中卫": [37.5000, 105.1800, "宁夏回族自治区"],
        "乌鲁木齐": [43.8256, 87.6168, "新疆维吾尔自治区"],
        "克拉玛依": [45.5800, 84.8800, "新疆维吾尔自治区"],
        "吐鲁番": [42.9500, 89.1800, "新疆维吾尔自治区"],
        "哈密": [42.8300, 93.5100, "新疆维吾尔自治区"],
        "昌吉": [44.0100, 87.3000, "新疆维吾尔自治区"],
        "博尔塔拉": [44.9000, 82.0600, "新疆维吾尔自治区"],
        "巴音郭楞": [41.7200, 86.1300, "新疆维吾尔自治区"],
        "阿克苏": [41.1700, 80.2600, "新疆维吾尔自治区"],
        "克孜勒苏": [39.7100, 76.1700, "新疆维吾尔自治区"],
        "喀什": [39.4600, 75.9900, "新疆维吾尔自治区"],
        "和田": [37.1100, 79.9200, "新疆维吾尔自治区"],
        "伊犁": [43.9200, 81.3200, "新疆维吾尔自治区"],
        "塔城": [46.7500, 82.9700, "新疆维吾尔自治区"],
        "阿勒泰": [47.8400, 88.1300, "新疆维吾尔自治区"],
        "石河子": [44.3000, 86.0300, "新疆维吾尔自治区"],
        "五家渠": [44.1600, 87.5400, "新疆维吾尔自治区"],
        "台北": [25.0330, 121.5654, "台湾省"],
        "高雄": [22.6300, 120.3100, "台湾省"],
        "台中": [24.1400, 120.6800, "台湾省"],
        "台南": [22.9900, 120.2100, "台湾省"],
        "基隆": [25.1300, 121.7400, "台湾省"],
        "新竹": [24.8100, 120.9700, "台湾省"],
        "嘉义": [23.4800, 120.4500, "台湾省"],
        "香港": [22.3193, 114.1694, "香港特别行政区"],
        "澳门": [22.1987, 113.5439, "澳门特别行政区"],
    }
    
    # ==================== 从数据库加载数据 ====================
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT id, city_name, province, status, description, visit_date, plan_date FROM travel_records")
    rows = cursor.fetchall()
    conn.close()
    
    visited = []
    planned = []
    visited_details = {}
    planned_details = {}
    
    for record_id, city, province, status, desc, date, plan_date in rows:
        detail = {
            "id": record_id,
            "province": province,
            "date": date,
            "desc": desc,
            "plan_date": plan_date
        }
        if status.strip().lower() == "visited":
            visited.append(city)
            visited_details[city] = detail
        else:
            planned.append(city)
            planned_details[city] = detail
    
    def get_province(city):
        if city in city_coords and len(city_coords[city]) >= 3:
            return city_coords[city][2]
        return "未知"
    
    province_groups = {}
    for city in visited:
        prov = get_province(city)
        if prov not in province_groups:
            province_groups[prov] = []
        province_groups[prov].append(city)
    
    # ==================== 创建地图 ====================
    m = folium.Map(
        location=[35.0, 105.0],
        zoom_start=4,
        tiles='https://wprd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=9&x={x}&y={y}&z={z}',
        attr='高德地图'
    )
    
    # 已去城市：粉色圆点（#FF69B47F）
    for city in visited:
        if city in city_coords:
            lat, lon = city_coords[city][0], city_coords[city][1]
            folium.CircleMarker(
                location=[lat, lon],
                radius=8,
                color="#FF69B47F",
                fill=True,
                fill_color="#FF69B47F",
                fill_opacity=0.9,
                popup=folium.Popup(f"{city}<br/>已去 ✓", max_width=200),
                tooltip=city
            ).add_to(m)
    
    # 计划城市：亮绿色圆点（#6EEE19E6）
    for city in planned:
        if city in city_coords:
            lat, lon = city_coords[city][0], city_coords[city][1]
            folium.CircleMarker(
                location=[lat, lon],
                radius=8,
                color="#6EEE19E6",
                fill=True,
                fill_color="#6EEE19E6",
                fill_opacity=0.9,
                popup=folium.Popup(f"{city}<br/>计划中 ⏳", max_width=200),
                tooltip=city
            ).add_to(m)
    
    # 统计卡片
    col1, col2 = st.columns(2)
    with col1:
        st.metric("🏙️ 已点亮", len(visited))
    with col2:
        st.metric("📌 计划中", len(planned))
    
    # ==================== 地图 ====================
    st_data = st_folium(m, width=2300, height=800)
    
    # ==================== 已去城市（按省份折叠） ====================
    st.divider()
    
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.markdown("**❤️ 已去城市**")
        if province_groups:
            special_regions = ["北京", "天津", "上海", "重庆", "香港特别行政区", "澳门特别行政区"]
            display_groups = {}
            for prov, cities in province_groups.items():
                if prov in special_regions:
                    display_groups[prov] = cities
                else:
                    display_groups[f"{prov}（{len(cities)}）"] = cities
            sorted_keys = sorted(display_groups.keys())
             # 将 expander 放在窄列中，缩短宽度
            col_exp_blank1, col_exp_mid, col_exp_blank2 = st.columns([0.00001, 1, 0.5])
            with col_exp_mid:
                for key in sorted_keys:
                    cities = display_groups[key]
                    cities_sorted = sorted(cities, key=lambda c: visited_details.get(c, {}).get("date") or datetime.date(1970,1,1), reverse=True)
                    with st.expander(key):
                        for city in cities_sorted:
                            detail = visited_details.get(city, {})
                            date_str = detail.get("date").strftime("%Y-%m-%d") if detail.get("date") else "未知日期"
                            
                            # 城市名 + 日期占左列
                            col_name, col_btns = st.columns([3, 0.6])
                            with col_name:
                                st.write(f"{city}  {date_str}")
                            with col_btns:
                                # 三个按钮紧凑排列
                                btn_col1, btn_col2, btn_col3 = st.columns(3)
                                with btn_col1:
                                    if st.button("🔄", key=f"toggle_{city}", help="点击切换城市状态"):
                                        st.query_params["toggle_city"] = city
                                        st.rerun()
                                with btn_col2:
                                    if st.button("✏️", key=f"edit_{city}", help="点击修改城市信息"):
                                        st.session_state["edit_city"] = city
                                        st.rerun()
                                with btn_col3:
                                    if st.button("🗑️", key=f"del_{city}", help="点击删除城市"):
                                        st.query_params["delete_city"] = city
                                        st.rerun()
                            
                            # 修改编辑表单
                            if st.session_state.get("edit_city") == city:
                                with st.container():
                                    st.divider()
                                    st.caption(f"✏️ 修改 {city}")
                                    col_e1, col_e2 = st.columns(2)
                                    with col_e1:
                                        new_visit_date = st.date_input("旅行日期", value=detail.get("date") or datetime.date.today(), key=f"edit_date_{city}")
                                    with col_e2:
                                        new_status = st.selectbox("状态", ["visited", "planned"], 
                                                                index=0 if detail.get("plan_date") is None else 1,
                                                                format_func=lambda x: "已去" if x == "visited" else "计划中",
                                                                key=f"edit_status_{city}")
                                    col_save, col_cancel = st.columns(2)
                                    with col_save:
                                        if st.button("💾 保存修改", key=f"save_edit_{city}"):
                                            conn = pymysql.connect(**DB_CONFIG)
                                            cursor = conn.cursor()
                                            if new_status == "visited":
                                                cursor.execute(
                                                    "UPDATE travel_records SET visit_date = %s, plan_date = NULL, status = %s WHERE city_name = %s",
                                                    (new_visit_date, new_status, city)
                                                )
                                            else:
                                                cursor.execute(
                                                    "UPDATE travel_records SET visit_date = NULL, plan_date = %s, status = %s WHERE city_name = %s",
                                                    (new_visit_date, new_status, city)
                                                )
                                            conn.commit()
                                            conn.close()
                                            st.session_state["edit_city"] = None
                                            st.success(f"✅ {city} 已更新")
                                            st.rerun()
                                    with col_cancel:
                                        if st.button("取消", key=f"cancel_edit_{city}"):
                                            st.session_state["edit_city"] = None
                                            st.rerun()
                            
                            # 查看详情按钮
                            if st.button(f"查看 {city} 详情", key=f"detail_{city}"):
                                st.query_params["city_detail"] = city
                                st.rerun()
        else:
                st.write("暂无已去城市")
    
    # ==================== 计划城市 ====================
    with col_right:
        st.markdown("**💚 计划城市**")
        if planned:
            planned_sorted = sorted(planned, key=lambda c: planned_details.get(c, {}).get("plan_date") or datetime.date(2099,12,31))
            for city in planned_sorted:
                detail = planned_details.get(city, {})
                plan_date_str = detail.get("plan_date").strftime("%Y-%m-%d") if detail.get("plan_date") else "未定"
                
                col_name, col_btns = st.columns([3, 0.6])
                with col_name:
                    st.write(f"{city}  📅 {plan_date_str}")
                with col_btns:
                    btn_col1, btn_col2, btn_col3 = st.columns(3)
                    with btn_col1:
                        if st.button("🔄", key=f"toggle_planned_{city}", help="点击切换城市状态"):
                            st.query_params["toggle_city"] = city
                            st.rerun()
                    with btn_col2:
                        if st.button("✏️", key=f"edit_planned_{city}", help="点击修改城市信息"):
                            st.session_state["edit_city"] = city
                            st.rerun()
                    with btn_col3:
                        if st.button("🗑️", key=f"del_planned_{city}", help="点击删除城市"):
                            st.query_params["delete_city"] = city
                            st.rerun()
                
                # 修改编辑表单（计划城市同样支持）
                if st.session_state.get("edit_city") == city:
                    with st.container():
                        st.divider()
                        st.caption(f"✏️ 修改 {city}")
                        col_e1, col_e2 = st.columns(2)
                        with col_e1:
                            new_plan_date = st.date_input("计划日期", value=detail.get("plan_date") or datetime.date.today(), key=f"edit_plan_date_{city}")
                        with col_e2:
                            new_status = st.selectbox("状态", ["visited", "planned"], 
                                                      index=1 if detail.get("plan_date") else 0,
                                                      format_func=lambda x: "已去" if x == "visited" else "计划中",
                                                      key=f"edit_plan_status_{city}")
                        col_save, col_cancel = st.columns(2)
                        with col_save:
                            if st.button("💾 保存修改", key=f"save_edit_plan_{city}"):
                                conn = pymysql.connect(**DB_CONFIG)
                                cursor = conn.cursor()
                                if new_status == "visited":
                                    cursor.execute(
                                        "UPDATE travel_records SET visit_date = %s, plan_date = NULL, status = %s WHERE city_name = %s",
                                        (new_plan_date, new_status, city)
                                    )
                                else:
                                    cursor.execute(
                                        "UPDATE travel_records SET visit_date = NULL, plan_date = %s, status = %s WHERE city_name = %s",
                                        (new_plan_date, new_status, city)
                                    )
                                conn.commit()
                                conn.close()
                                st.session_state["edit_city"] = None
                                st.success(f"✅ {city} 已更新")
                                st.rerun()
                        with col_cancel:
                            if st.button("取消", key=f"cancel_edit_plan_{city}"):
                                st.session_state["edit_city"] = None
                                st.rerun()
        else:
            st.write("暂无计划城市")
    
    # ==================== 添加旅行记录表单 ====================
    st.divider()
    st.subheader("📝 添加旅行记录")
    
    with st.form("travel_form"):
        col1, col2 = st.columns(2)
        with col1:
            city_input = st.text_input("城市名", key="city_input")
            province_input = st.text_input("省份", key="province_input")
        with col2:
            # 状态：使用占位选项，不默认选中
            status_options = ["", "visited", "planned"]
            status_labels = {"": "请选择状态", "visited": "已去", "planned": "计划中"}
            status_select = st.selectbox(
                "状态", 
                status_options, 
                format_func=lambda x: status_labels.get(x, x),
                key="status_select"
            )
            # 日期：不显示默认值，使用 None 让用户自己选择
            date_input = st.date_input("日期", value=None, key="date_input")
        submitted = st.form_submit_button("保存")
        
        if submitted:
            if not city_input or not province_input:
                st.error("请填写城市和省份")
            elif not status_select:
                st.error("请选择状态")
            elif date_input is None:
                st.error("请选择日期")
            else:
                # 自动填充省份
                if not province_input and city_input in city_coords and len(city_coords[city_input]) >= 3:
                    province_input = city_coords[city_input][2]
                if status_select == "visited":
                    visit_date = date_input
                    plan_date = None
                else:
                    visit_date = None
                    plan_date = date_input
                conn = pymysql.connect(**DB_CONFIG)
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO travel_records (city_name, province, visit_date, plan_date, status, description) VALUES (%s, %s, %s, %s, %s, %s)",
                    (city_input, province_input, visit_date, plan_date, status_select, "")
                )
                conn.commit()
                conn.close()
                st.success(f"✅ 已添加 {city_input}")
                for key in ["city_input", "province_input"]:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
    
    # ==================== 处理删除/切换操作 ====================
    if "delete_city" in st.query_params:
        city_to_delete = st.query_params["delete_city"]
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM travel_records WHERE city_name = %s", (city_to_delete,))
        conn.commit()
        conn.close()
        st.query_params.clear()
        st.rerun()
    
    if "toggle_city" in st.query_params:
        city_to_toggle = st.query_params["toggle_city"]
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM travel_records WHERE city_name = %s", (city_to_toggle,))
        current = cursor.fetchone()
        if current:
            new_status = "planned" if current[0] == "visited" else "visited"
            cursor.execute("UPDATE travel_records SET status = %s WHERE city_name = %s", (new_status, city_to_toggle))
            conn.commit()
        conn.close()
        st.query_params.clear()
        st.rerun()

# ==================== 主页面 ====================
def home_page():
    now = datetime.datetime.now()
    hour = now.hour
    if hour < 6:
        greeting = "夜深了 🌙"
    elif hour < 12:
        greeting = "早上好 ☀️"
    elif hour < 14:
        greeting = "中午好 🌤️"
    elif hour < 18:
        greeting = "下午好 🌅"
    elif hour < 22:
        greeting = "晚上好 🌙"
    else:
        greeting = "夜深了 🌙"
    
    st.title(f"🏠 {greeting}，欢迎回家")
    st.caption(f"📅 {now.strftime('%Y年%m月%d日')}")
    st.divider()
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        <div style="background: #FFF5E6; border-radius: 20px; padding: 30px; text-align: center; border: 2px solid #FFD699;">
            <div style="font-size: 60px;">✈️</div>
            <div style="font-size: 24px; font-weight: bold; margin-top: 10px;">旅行</div>
            <div style="color: #888; font-size: 14px;">记录我们走过的路</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("进入旅行", key="go_travel", use_container_width=True):
            st.session_state.page = "travel"
            st.rerun()
    
    with col2:
        st.markdown("""
        <div style="background: #E8F5E9; border-radius: 20px; padding: 30px; text-align: center; border: 2px solid #A5D6A7;">
            <div style="font-size: 60px;">📖</div>
            <div style="font-size: 24px; font-weight: bold; margin-top: 10px;">做菜</div>
            <div style="color: #888; font-size: 14px;">吃好每一顿饭</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("进入做菜", key="go_cook", use_container_width=True):
            st.session_state.page = "cook"
            st.rerun()

# ==================== 主程序 ====================
def main():
    st.set_page_config(page_title="宇帆&韬韬之家", page_icon="🏠", layout="wide")
    
    if "page" not in st.session_state:
        st.session_state.page = "home"
    
    if st.session_state.page == "home":
        home_page()
    elif st.session_state.page == "travel":
        travel_page()
    elif st.session_state.page == "cook":
        cook_page()

if __name__ == "__main__":
    main()