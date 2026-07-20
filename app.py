import streamlit as st
import pymysql
import os
from dotenv import load_dotenv
import dashscope
from dashscope import Generation

load_dotenv()

# ==================== 数据库配置 ====================
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "75757575",   # 改成你实际的 root 密码
    "database": "menu_db",
    "charset": "utf8mb4"
}

# ==================== 加载数据 ====================
def load_menu():
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT name, ingredients, steps FROM recipes")
    rows = cursor.fetchall()
    conn.close()
    return rows

# ==================== 增删改 ====================
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

# ==================== 关键词检索 ====================
def search_recipes_by_keyword(query):
    rows = load_menu()
    results = []
    query_lower = query.lower()
    
    for name, ingredients, steps in rows:
        combined = f"{name} {ingredients} {steps}".lower()
        if query_lower in combined:
            results.append({
                "name": name,
                "ingredients": ingredients,
                "steps": steps
            })
    
    return results

# ==================== AI 生成菜谱（批量） ====================
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
            recipes.append({
                "name": name,
                "ingredients": ingredients,
                "steps": steps
            })
    
    return recipes

# ==================== 页面设置 ====================
st.set_page_config(page_title="家庭菜谱", page_icon="🍳")
st.title("🍳 家庭菜谱管理系统")

# ==================== 初始化状态 ====================
if "show_menu" not in st.session_state:
    st.session_state.show_menu = False
if "generated_recipes" not in st.session_state:
    st.session_state.generated_recipes = []
if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "add_success" not in st.session_state:
    st.session_state.add_success = None
if "current_taste" not in st.session_state:
    st.session_state.current_taste = ""
if "current_count" not in st.session_state:
    st.session_state.current_count = 5

# ==================== 侧边栏 ====================
with st.sidebar:
    st.header("➕ 新增菜")
    with st.form("add_form"):
        new_name = st.text_input("菜名")
        new_ingredients = st.text_input("食材（用英文逗号分隔）")
        new_steps = st.text_area("做法（每步换行）")
        submitted = st.form_submit_button("添加")
        if submitted:
            if not new_name or not new_ingredients or not new_steps:
                st.error("请填写完整信息")
            else:
                add_recipe(new_name, new_ingredients, new_steps)
                st.success(f"✅ 已添加【{new_name}】")
                st.rerun()

# ==================== AI 智能推荐 ====================
st.subheader("🤖 AI 智能推荐")

tab1, tab2 = st.tabs(["📋 从菜单里找", "✨ AI 生成新菜"])

# ---------- Tab 1: 从菜单里找 ----------
with tab1:
    taste = st.text_input("你想吃什么口味的？（例如：清淡的、辣的、快速的、家常的）", key="search_taste")
    if st.button("🔍 在菜单里找", key="search_btn"):
        if not taste.strip():
            st.error("请输入你想吃的类型")
        else:
            with st.spinner("正在检索你的菜单..."):
                results = search_recipes_by_keyword(taste)
                if results:
                    st.session_state.search_results = results
                    st.success(f"找到 {len(results)} 道菜")
                else:
                    st.info("你的菜单里暂时没有符合这个口味的菜，试试「AI 生成新菜」吧！")

    if st.session_state.search_results:
        for dish in st.session_state.search_results:
            with st.expander(f"**{dish['name']}**"):
                st.markdown(f"**食材**：{dish['ingredients']}")
                st.text(f"做法：{dish['steps']}")

# ---------- Tab 2: AI 生成新菜 ----------
with tab2:
    # 显示添加成功消息
    if st.session_state.add_success:
        st.success(st.session_state.add_success)
        st.session_state.add_success = None
    
    taste2 = st.text_input("你想生成什么口味的菜？（例如：清淡的、辣的、快速的、家常的）", key="gen_taste")
    count = st.slider("生成数量", min_value=3, max_value=10, value=5, key="gen_count")
    
    col_gen1, col_gen2 = st.columns(2)
    with col_gen1:
        if st.button("✨ 生成菜谱", key="gen_btn"):
            if not taste2.strip():
                st.error("请输入你想吃的类型")
            else:
                with st.spinner(f"AI 正在生成 {count} 道菜..."):
                    recipes, err = ai_generate_recipes(taste2, count)
                    if err:
                        st.error(err)
                    elif recipes:
                        st.session_state.generated_recipes = recipes
                        st.session_state.current_taste = taste2
                        st.session_state.current_count = count
                        st.success(f"✅ AI 生成了 {len(recipes)} 道菜！")
                    else:
                        st.error("生成失败，请重试")
    
    with col_gen2:
        if st.button("🔄 换一批", key="refresh_btn"):
            if not st.session_state.current_taste:
                st.warning("请先生成菜谱")
            else:
                with st.spinner(f"AI 正在生成 {st.session_state.current_count} 道菜..."):
                    recipes, err = ai_generate_recipes(st.session_state.current_taste, st.session_state.current_count)
                    if err:
                        st.error(err)
                    elif recipes:
                        st.session_state.generated_recipes = recipes
                        st.success(f"✅ 已换一批！生成了 {len(recipes)} 道菜")
                    else:
                        st.error("生成失败，请重试")

    if st.session_state.generated_recipes:
        st.divider()
        st.subheader(f"📝 AI 生成的菜谱（共 {len(st.session_state.generated_recipes)} 道）")
        
        col_all1, col_all2 = st.columns(2)
        with col_all1:
            if st.button("✅ 全部加入菜单"):
                for dish in st.session_state.generated_recipes:
                    add_recipe(dish["name"], dish["ingredients"], dish["steps"])
                st.session_state.add_success = f"✅ 成功添加 {len(st.session_state.generated_recipes)} 道菜到菜单！"
                st.session_state.generated_recipes = []
                st.rerun()
        with col_all2:
            if st.button("🗑️ 全部丢弃"):
                st.session_state.generated_recipes = []
                st.rerun()
        
        st.divider()
        
        for i, dish in enumerate(st.session_state.generated_recipes):
            with st.expander(f"**{i+1}. {dish['name']}**"):
                st.markdown(f"**食材**：{dish['ingredients']}")
                st.text(f"做法：{dish['steps']}")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"✅ 加入菜单", key=f"add_{i}"):
                        add_recipe(dish["name"], dish["ingredients"], dish["steps"])
                        st.session_state.add_success = f"✅ 成功添加【{dish['name']}】到菜单！"
                        st.session_state.generated_recipes.pop(i)
                        st.rerun()
                with col2:
                    if st.button(f"⏭️ 跳过", key=f"skip_{i}"):
                        st.session_state.generated_recipes.pop(i)
                        st.rerun()

# ==================== 菜单显示 ====================
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    if st.button("🍽️ 打开菜单", use_container_width=True):
        st.session_state.show_menu = not st.session_state.show_menu

if st.session_state.show_menu:
    menu_data = load_menu()
    if menu_data:
        st.subheader(f"📋 当前菜单（共 {len(menu_data)} 道菜）")
        for name, ingredients, steps in menu_data:
            with st.expander(f"**{name}**"):
                st.markdown(f"**食材**：{ingredients}")
                st.text(f"做法：{steps}")
                col1, col2 = st.columns(2)
                with col1:
                    with st.popover(f"🗑️ 删除 {name}", use_container_width=True):
                        st.warning(f"确定要删除【{name}】吗？")
                        col_yes, col_no = st.columns(2)
                        with col_yes:
                            if st.button("✅ 确认", key=f"confirm_{name}"):
                                delete_recipe(name)
                                st.success(f"已删除 {name}")
                                st.rerun()
                        with col_no:
                            if st.button("❌ 取消", key=f"cancel_{name}"):
                                st.rerun()
                with col2:
                    if st.button(f"✏️ 修改 {name}"):
                        st.session_state["edit_name"] = name
                        st.session_state["edit_ingredients"] = ingredients
                        st.session_state["edit_steps"] = steps

                if st.session_state.get("edit_name") == name:
                    st.divider()
                    st.subheader(f"✏️ 修改【{name}】")
                    new_name = st.text_input("新菜名", value=name, key=f"new_name_{name}")
                    new_ingredients = st.text_input("新食材（用英文逗号分隔）", value=ingredients, key=f"new_ingredients_{name}")
                    new_steps = st.text_area("新做法（每步换行）", value=steps, key=f"new_steps_{name}")
                    if st.button("💾 保存修改", key=f"save_{name}"):
                        update_recipe(name, new_name, new_ingredients, new_steps)
                        st.success(f"✅ 【{name}】已修改为【{new_name}】")
                        st.session_state["edit_name"] = None
                        st.rerun()
    else:
        st.info("📭 菜单是空的，请添加菜谱！")
else:
    st.caption("👆 点击上方按钮查看菜单")