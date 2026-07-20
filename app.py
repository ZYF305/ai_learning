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

# ==================== 新增菜 ====================
def add_recipe(name, ingredients, steps):
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO recipes (name, ingredients, steps) VALUES (%s, %s, %s)",
        (name, ingredients, steps)
    )
    conn.commit()
    conn.close()

# ==================== 删除菜 ====================
def delete_recipe(name):
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM recipes WHERE name = %s", (name,))
    conn.commit()
    conn.close()

# ==================== 修改菜 ====================
def update_recipe(old_name, new_name, new_ingredients, new_steps):
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE recipes SET name = %s, ingredients = %s, steps = %s WHERE name = %s",
        (new_name, new_ingredients, new_steps, old_name)
    )
    conn.commit()
    conn.close()

# ==================== AI 推荐 ====================
def ai_recommend(ingredients_input):
    dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
    
    prompt = f"""你是一个厨艺高超的AI厨师。请根据以下食材推荐一道菜：
食材：{ingredients_input}

请按以下格式返回（严格按这个格式）：
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
            return None, f"❌ API 调用失败：{response.message}"
        
        content = response.output.choices[0].message.content
        
        lines = content.strip().split("\n")
        name = ""
        ingredients = ""
        steps = ""
        is_steps = False
        
        for line in lines:
            line = line.strip()
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
            return {
                "name": name,
                "ingredients": ingredients,
                "steps": steps
            }, content
        else:
            return None, content
            
    except Exception as e:
        return None, f"❌ AI 服务暂时不可用：{e}"

# ==================== 页面设置 ====================
st.set_page_config(page_title="家庭菜谱", page_icon="🍳")
st.title("🍳 家庭菜谱管理系统")

# ==================== 初始化状态 ====================
if "show_menu" not in st.session_state:
    st.session_state.show_menu = False

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

    st.divider()
    st.header("🤖 AI 推荐菜")
    ai_ingredients = st.text_input("请输入食材（用中文逗号或空格分隔）")
    if st.button("推荐"):
        if not ai_ingredients.strip():
            st.error("请输入食材")
        else:
            with st.spinner("AI 正在思考..."):
                result, raw = ai_recommend(ai_ingredients)
                if result:
                    st.session_state["ai_result"] = result
                    st.session_state["ai_raw"] = raw
                    st.success("✅ 推荐成功！请查看主页面")
                else:
                    st.error("❌ 推荐失败，请重试")
                    st.text("原始返回：")
                    st.text(raw)

# ==================== 主页面 ====================
# 显示 AI 推荐结果
if "ai_result" in st.session_state and st.session_state["ai_result"]:
    result = st.session_state["ai_result"]
    st.subheader("🤖 AI 推荐结果")
    st.markdown(f"**菜名：{result['name']}**")
    st.markdown(f"**食材：{result['ingredients']}**")
    st.text(f"做法：{result['steps']}")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 保存到菜单"):
            add_recipe(result["name"], result["ingredients"], result["steps"])
            st.success(f"✅ 已保存【{result['name']}】到菜单")
            st.session_state["ai_result"] = None
            st.rerun()
    with col2:
        if st.button("🗑️ 丢弃"):
            st.session_state["ai_result"] = None
            st.rerun()
    st.divider()

# ==================== 菜单显示（按钮控制） ====================
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
                    # 使用 popover 实现删除确认
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