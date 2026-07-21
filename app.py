import streamlit as st
import pymysql
import os
from dotenv import load_dotenv
import dashscope
from dashscope import Generation
import datetime

load_dotenv()

# ==================== 数据库配置 ====================
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "75757575",   # 改成你实际的 root 密码
    "database": "menu_db",
    "charset": "utf8mb4"
}

# ==================== 菜谱相关函数（保持不变） ====================
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

# ==================== 菜谱板块页面 ====================
def cook_page():
    st.title("📖 我们家的小饭桌")
    
    # 初始化状态
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

    # 侧边栏 - 新增菜
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
                    recipes, err = ai_generate_recipes(ai_ingredients, 3)
                    if err:
                        st.error(err)
                    elif recipes:
                        st.session_state.generated_recipes = recipes
                        st.success(f"✅ AI 生成了 {len(recipes)} 道菜！")
                    else:
                        st.error("生成失败，请重试")

    # AI 推荐结果展示
    if "ai_result" in st.session_state and st.session_state.ai_result:
        result = st.session_state.ai_result
        st.subheader("🤖 AI 推荐结果")
        st.markdown(f"**菜名：{result['name']}**")
        st.markdown(f"**食材：{result['ingredients']}**")
        st.text(f"做法：{result['steps']}")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 保存到菜单"):
                add_recipe(result["name"], result["ingredients"], result["steps"])
                st.success(f"✅ 已保存【{result['name']}】")
                st.session_state.ai_result = None
                st.rerun()
        with col2:
            if st.button("🗑️ 丢弃"):
                st.session_state.ai_result = None
                st.rerun()
        st.divider()

    # 显示菜单
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
                            if st.button("✅ 确认", key=f"confirm_{name}"):
                                delete_recipe(name)
                                st.success(f"已删除 {name}")
                                st.rerun()
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

    # 返回首页按钮
    if st.button("🏠 返回首页"):
        st.session_state.page = "home"
        st.rerun()

# ==================== 旅行板块页面（占位） ====================
def travel_page():
    import folium
    from streamlit_folium import st_folium
    import datetime
    
    st.title("✈️ 我们的旅行地图")
    
    # 从数据库加载旅行数据
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT id, city_name, province, status, description, visit_date FROM travel_records")
    rows = cursor.fetchall()
    conn.close()
    
    # 城市坐标（已补充渭南）
    city_coords = {
        "北京": [39.9042, 116.4074],
        "上海": [31.2304, 121.4737],
        "天津": [39.0842, 117.2009],
        "重庆": [29.4316, 106.9123],
        "石家庄": [38.0423, 114.5149],
        "太原": [37.8706, 112.5489],
        "呼和浩特": [40.8424, 111.7490],
        "沈阳": [41.8057, 123.4315],
        "大连": [38.9140, 121.6147],
        "长春": [43.8868, 125.3245],
        "哈尔滨": [45.8038, 126.5350],
        "南京": [32.0603, 118.7969],
        "苏州": [31.2990, 120.5853],
        "无锡": [31.4912, 120.3119],
        "杭州": [30.2741, 120.1551],
        "宁波": [29.8683, 121.5439],
        "温州": [27.9949, 120.6984],
        "合肥": [31.8206, 117.2272],
        "福州": [26.0745, 119.2965],
        "厦门": [24.4798, 118.0894],
        "泉州": [24.8739, 118.6759],
        "南昌": [28.6820, 115.8579],
        "济南": [36.6512, 117.1201],
        "青岛": [36.0671, 120.3826],
        "淄博": [36.8131, 118.0550],
        "烟台": [37.4638, 121.4479],
        "潍坊": [36.7063, 119.1618],
        "临沂": [35.1049, 118.3564],
        "郑州": [34.7470, 113.6250],
        "洛阳": [34.6100, 112.4500],
        "武汉": [30.5928, 114.3055],
        "长沙": [28.2282, 112.9388],
        "广州": [23.1291, 113.2644],
        "深圳": [22.5431, 114.0579],
        "珠海": [22.2700, 113.5700],
        "佛山": [23.0215, 113.1214],
        "东莞": [23.0207, 113.7518],
        "南宁": [22.8170, 108.3665],
        "桂林": [25.2700, 110.2900],
        "海口": [20.0174, 110.3492],
        "三亚": [18.2528, 109.5119],
        "成都": [30.5728, 104.0668],
        "绵阳": [31.4600, 104.7500],
        "贵阳": [26.6477, 106.6302],
        "昆明": [24.8801, 102.8329],
        "丽江": [26.8600, 100.2300],
        "大理": [25.6100, 100.2800],
        "拉萨": [29.6500, 91.1000],
        "西安": [34.3416, 108.9398],
        "兰州": [36.0611, 103.8343],
        "西宁": [36.6171, 101.7782],
        "银川": [38.4872, 106.2309],
        "乌鲁木齐": [43.8256, 87.6168],
        "台北": [25.0330, 121.5654],
        "高雄": [22.6300, 120.3100],
        "香港": [22.3193, 114.1694],
        "澳门": [22.1987, 113.5439],
        # 新增
        "渭南": [34.5000, 109.5000],
    }
    
    # 分类数据
    visited = []
    planned = []
    city_details = {}
    
    for record_id, city, province, status, desc, date in rows:
        city_details[city] = {"id": record_id, "province": province, "date": date, "desc": desc}
        if status.strip().lower() == "visited":
            visited.append(city)
        else:
            planned.append(city)
    
    # ========== 删除和修改功能 ==========
    # 删除城市
    if "delete_city" in st.query_params:
        city_to_delete = st.query_params["delete_city"]
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM travel_records WHERE city_name = %s", (city_to_delete,))
        conn.commit()
        conn.close()
        st.query_params.clear()
        st.rerun()
    
    # 修改城市状态
    if "toggle_city" in st.query_params:
        city_to_toggle = st.query_params["toggle_city"]
        # 获取当前状态
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM travel_records WHERE city_name = %s", (city_to_toggle,))
        current = cursor.fetchone()[0]
        new_status = "planned" if current == "visited" else "visited"
        cursor.execute("UPDATE travel_records SET status = %s WHERE city_name = %s", (new_status, city_to_toggle))
        conn.commit()
        conn.close()
        st.query_params.clear()
        st.rerun()
    
    # 创建地图
    m = folium.Map(
        location=[35.0, 105.0],
        zoom_start=4,
        tiles='https://wprd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=9&x={x}&y={y}&z={z}',
        attr='高德地图'
    )
    
    # 已去城市：粉色圆点
    for city in visited:
        if city in city_coords:
            lat, lon = city_coords[city]
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
    
    # 计划城市：亮绿色圆点
    for city in planned:
        if city in city_coords:
            lat, lon = city_coords[city]
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
    
    # 地图
    st_data = st_folium(m, width=2300, height=800)
    
    # ========== 城市列表（带删除和修改按钮） ==========
    st.divider()
    st.subheader("📍 城市管理")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**❤️ 已去城市**")
        if visited:
            for city in visited:
                detail = city_details.get(city, {})
                col_a, col_b, col_c = st.columns([3, 1, 1])
                with col_a:
                    st.write(f"{city}（{detail.get('province', '')}）")
                with col_b:
                    # 修改按钮：切换状态（已去 ↔ 计划中）
                    if st.button(f"🔄", key=f"toggle_{city}"):
                        st.query_params["toggle_city"] = city
                        st.rerun()
                with col_c:
                    if st.button(f"🗑️", key=f"del_{city}"):
                        st.query_params["delete_city"] = city
                        st.rerun()
        else:
            st.write("暂无")
    
    with col2:
        st.markdown("**💚 计划城市**")
        if planned:
            for city in planned:
                detail = city_details.get(city, {})
                col_a, col_b, col_c = st.columns([3, 1, 1])
                with col_a:
                    st.write(f"{city}（{detail.get('province', '')}）")
                with col_b:
                    if st.button(f"🔄", key=f"toggle_{city}"):
                        st.query_params["toggle_city"] = city
                        st.rerun()
                with col_c:
                    if st.button(f"🗑️", key=f"del_{city}"):
                        st.query_params["delete_city"] = city
                        st.rerun()
        else:
            st.write("暂无")
    
    # ========== 添加旅行记录表单 ==========
    st.divider()
    st.subheader("📝 添加旅行记录")
    with st.form("travel_form"):
        col1, col2 = st.columns(2)
        with col1:
            city = st.text_input("城市名")
            province = st.text_input("省份")
        with col2:
            date = st.date_input("旅行日期")
            status = st.selectbox("状态", ["visited", "planned"], format_func=lambda x: "已去" if x == "visited" else "计划中")
        description = st.text_area("游记/备注")
        submitted = st.form_submit_button("保存")
        
        if submitted:
            if not city or not province:
                st.error("请填写城市和省份")
            else:
                conn = pymysql.connect(**DB_CONFIG)
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO travel_records (city_name, province, visit_date, description, status) VALUES (%s, %s, %s, %s, %s)",
                    (city, province, date, description, status)
                )
                conn.commit()
                conn.close()
                st.success(f"✅ 已添加 {city}")
                st.rerun()
    
    # ========== 返回首页 ==========
    if st.button("🏠 返回首页"):
        st.session_state.page = "home"
        st.rerun()

# ==================== 主页面 ====================
def home_page():
    # 动态欢迎语
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
    
    # 板块入口
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        <div style="background: #FFF5E6; border-radius: 20px; padding: 30px; text-align: center; border: 2px solid #FFD699; cursor: pointer;">
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
        <div style="background: #E8F5E9; border-radius: 20px; padding: 30px; text-align: center; border: 2px solid #A5D6A7; cursor: pointer;">
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