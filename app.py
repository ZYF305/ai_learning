import streamlit as st
import os
import json
import re
import collections
import datetime
import requests
import base64
import tempfile
from dotenv import load_dotenv

load_dotenv()

# ==================== 数据库配置 ====================
# MySQL 配置（工位本地用）
MYSQL_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "75757575",
    "database": "menu_db",
    "charset": "utf8mb4"
}

# Supabase 配置（云端部署用）- 直接硬编码，不依赖环境变量
SUPABASE_CONFIG = {
    "host": "jmltvpxrqzwjzhissibf.supabase.co",
    "database": "postgres",
    "user": "postgres",
    "password": "ssdyfssdwt0425.",
    "port": 5432
}


# ==================== 自动切换数据库连接 ====================
def get_db_connection():
    # 直接判断 st.secrets 里有没有标记
    is_cloud = False
    try:
        if st.secrets.get("ENV") == "cloud":
            is_cloud = True
    except:
        pass

    if is_cloud:
        # 连 Supabase
        try:
            import psycopg2
            conn = psycopg2.connect(
                host=SUPABASE_CONFIG["host"],
                database=SUPABASE_CONFIG["database"],
                user=SUPABASE_CONFIG["user"],
                password=SUPABASE_CONFIG["password"],
                port=SUPABASE_CONFIG["port"],
                connect_timeout=10
            )
            return conn
        except Exception as e:
            return None
    else:
        # 本地连 MySQL
        try:
            import pymysql
            return pymysql.connect(**MYSQL_CONFIG)
        except Exception as e:
            return None


def is_cloud():
    """判断是否在云端环境"""
    return os.getenv("STREAMLIT_CLOUD") is not None or os.getenv("STREAMLIT_SHARING") is not None


# ==================== 菜谱相关函数 ====================
def load_menu():
    conn = get_db_connection()
    if conn is None:
        return []
    cursor = conn.cursor()
    cursor.execute("SELECT name, ingredients, steps FROM recipes")
    rows = cursor.fetchall()
    conn.close()
    return rows


def add_recipe(name, ingredients, steps):
    conn = get_db_connection()
    if conn is None:
        return False
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO recipes (name, ingredients, steps) VALUES (%s, %s, %s)",
        (name, ingredients, steps)
    )
    conn.commit()
    conn.close()
    return True


def delete_recipe(name):
    conn = get_db_connection()
    if conn is None:
        return False
    cursor = conn.cursor()
    cursor.execute("DELETE FROM recipes WHERE name = %s", (name,))
    conn.commit()
    conn.close()
    return True


def update_recipe(old_name, new_name, new_ingredients, new_steps):
    conn = get_db_connection()
    if conn is None:
        return False
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE recipes SET name = %s, ingredients = %s, steps = %s WHERE name = %s",
        (new_name, new_ingredients, new_steps, old_name)
    )
    conn.commit()
    conn.close()
    return True


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
    import dashscope
    from dashscope import Generation
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


# ==================== 首页 ====================
def home_page():
    from datetime import datetime, timedelta
    
    CONFIG_FILE = "home_config.json"
    
    def load_config():
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    date_str = data.get("next_meeting_date")
                    if date_str:
                        return datetime.fromisoformat(date_str).date()
            except:
                pass
        return None
    
    def save_config(date_obj):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "next_meeting_date": date_obj.isoformat() if date_obj else None
            }, f, ensure_ascii=False, indent=2)
    
    HEFENG_WEATHER_KEY = "90cf2b0c3ed843adb8a902e23f0684bd"
    
    def get_weather_by_city_code(city_code):
        if not HEFENG_WEATHER_KEY:
            return None
        url = f"https://devapi.qweather.com/v7/weather/now?location={city_code}&key={HEFENG_WEATHER_KEY}"
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == "200":
                    return {
                        "temp": data["now"]["temp"],
                        "text": data["now"]["text"],
                        "icon": data["now"]["icon"],
                        "wind_dir": data["now"]["windDir"],
                        "humidity": data["now"]["humidity"]
                    }
            return None
        except:
            return None
    
    def get_weather_by_lat_lon(lat, lon):
        if not HEFENG_WEATHER_KEY:
            return None
        url = f"https://devapi.qweather.com/v7/weather/now?location={lat},{lon}&key={HEFENG_WEATHER_KEY}"
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == "200":
                    return {
                        "temp": data["now"]["temp"],
                        "text": data["now"]["text"],
                        "icon": data["now"]["icon"],
                        "wind_dir": data["now"]["windDir"],
                        "humidity": data["now"]["humidity"]
                    }
            return None
        except:
            return None
    
    HANGZHOU_CODE = "101210101"
    HANCHENG_LAT = "35.48"
    HANCHENG_LON = "110.45"
    
    weather_hz = get_weather_by_city_code(HANGZHOU_CODE)
    weather_hc = get_weather_by_lat_lon(HANCHENG_LAT, HANCHENG_LON)
    
    weather_icons = {
        "100": "☀️", "101": "⛅", "102": "⛅", "103": "☁️", "104": "☁️",
        "150": "🌧️", "151": "🌧️", "152": "🌧️", "153": "🌧️",
        "300": "🌧️", "301": "🌧️", "302": "🌧️", "303": "🌧️", "304": "⛈️",
        "305": "🌧️", "306": "🌧️", "307": "🌧️", "308": "🌧️", "309": "🌧️",
        "310": "🌧️", "311": "🌧️", "312": "🌧️", "313": "🌨️", "314": "🌨️",
        "315": "🌧️", "316": "🌧️", "317": "🌧️", "318": "🌧️",
        "400": "❄️", "401": "❄️", "402": "❄️", "403": "❄️",
        "404": "🌨️", "405": "🌨️", "406": "🌨️", "407": "🌨️",
        "500": "🌫️", "501": "🌫️", "502": "🌫️", "503": "🌫️", "504": "🌫️",
        "507": "🌪️", "508": "🌪️", "509": "🌫️", "510": "🌫️",
        "511": "🌫️", "512": "🌫️", "513": "🌫️", "514": "🌫️", "515": "🌫️",
        "900": "🌞", "901": "🥶", "999": "❓",
    }
    
    def get_weather_icon(icon_code):
        return weather_icons.get(str(icon_code), "🌤️")
    
    def get_countdown():
        target_date = st.session_state.get("next_meeting_date")
        if not target_date:
            return None
        today = datetime.now().date()
        delta = target_date - today
        return delta.days
    
    st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(135deg, #FFF8F0 0%, #FDF6EC 100%) !important;
    }
    h1, h2, h3, h4, h5, h6, p, .stMarkdown {
        color: #4A3728 !important;
    }
    .home-card {
        background: rgba(255, 255, 255, 0.85);
        backdrop-filter: blur(10px);
        border-radius: 20px;
        padding: 25px 30px;
        box-shadow: 0 8px 32px rgba(245, 166, 35, 0.12);
        border: 1px solid rgba(255, 255, 255, 0.6);
        transition: transform 0.2s ease;
        margin-bottom: 20px;
    }
    .home-card:hover {
        transform: translateY(-2px);
    }
    .countdown-number {
        font-size: 72px;
        font-weight: 700;
        background: linear-gradient(135deg, #FF6B6B, #F5A623);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        line-height: 1.2;
        text-align: center;
    }
    .countdown-label {
        font-size: 20px;
        color: #4A3728;
        text-align: center;
        margin-top: -5px;
    }
    .countdown-days {
        font-size: 18px;
        color: #8B7A6B;
        text-align: center;
        margin-top: 5px;
    }
    .weather-card {
        background: rgba(255, 255, 255, 0.7);
        border-radius: 16px;
        padding: 20px 25px;
        text-align: center;
        border: 1px solid rgba(245, 166, 35, 0.15);
    }
    .weather-icon {
        font-size: 48px;
        display: block;
        margin-bottom: 5px;
    }
    .weather-temp {
        font-size: 32px;
        font-weight: 600;
        color: #4A3728;
    }
    .weather-text {
        font-size: 16px;
        color: #8B7A6B;
    }
    .weather-city {
        font-size: 14px;
        color: #A8947F;
        margin-bottom: 8px;
    }
    .weather-detail {
        font-size: 12px;
        color: #A8947F;
        margin-top: 4px;
    }
    .entry-card {
        background: rgba(255, 255, 255, 0.75);
        border-radius: 24px;
        padding: 40px 20px;
        text-align: center;
        border: 2px solid rgba(245, 166, 35, 0.12);
        transition: all 0.3s ease;
        cursor: pointer;
        box-shadow: 0 4px 20px rgba(245, 166, 35, 0.06);
        min-height: 220px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
    }
    .entry-card:hover {
        transform: translateY(-4px) scale(1.01);
        border-color: rgba(245, 166, 35, 0.3);
        box-shadow: 0 8px 40px rgba(245, 166, 35, 0.12);
    }
    .entry-card .emoji {
        font-size: 56px;
        margin-bottom: 12px;
    }
    .entry-card .title {
        font-size: 24px;
        font-weight: 600;
        color: #4A3728;
    }
    .entry-card .subtitle {
        font-size: 14px;
        color: #A8947F;
        margin-top: 4px;
    }
    .greeting {
        font-size: 28px;
        font-weight: 600;
        color: #4A3728;
        margin-bottom: 2px;
    }
    .date-display {
        font-size: 16px;
        color: #A8947F;
        margin-bottom: 10px;
    }
    .weather-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 16px;
        margin-top: 10px;
    }
    .picker-container {
        background: rgba(255,255,255,0.7);
        border-radius: 16px;
        padding: 20px;
        border: 1px solid rgba(245,166,35,0.15);
        margin-bottom: 15px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    if "next_meeting_date" not in st.session_state or st.session_state.next_meeting_date is None:
        loaded_date = load_config()
        if loaded_date:
            st.session_state.next_meeting_date = loaded_date
        else:
            st.session_state.next_meeting_date = None
    
    if "show_date_picker" not in st.session_state:
        st.session_state.show_date_picker = False
    
    col_greeting, col_setting = st.columns([4, 1])
    with col_greeting:
        now = datetime.now()
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
        
        st.markdown(f'<div class="greeting">{greeting}，欢迎回家 ❤️</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="date-display">📅 {now.strftime("%Y年%m月%d日")}</div>', unsafe_allow_html=True)
    
    with col_setting:
        if st.button("⚙️ 设置见面日", key="set_meeting_date"):
            st.session_state.show_date_picker = not st.session_state.get("show_date_picker", False)
            st.rerun()
    
    if st.session_state.get("show_date_picker", False):
        with st.container():
            col_picker1, col_picker2, col_picker3 = st.columns([1, 2, 1])
            with col_picker2:
                st.markdown('<div class="picker-container">', unsafe_allow_html=True)
                default_date = st.session_state.next_meeting_date or datetime.now().date() + timedelta(days=7)
                new_date = st.date_input(
                    "📅 选择下一次见面的日期",
                    value=default_date,
                    min_value=datetime.now().date(),
                    key="date_picker_input"
                )
                col_btn1, col_btn2, col_btn3 = st.columns(3)
                with col_btn2:
                    if st.button("✅ 确认", key="confirm_date"):
                        st.session_state.next_meeting_date = new_date
                        save_config(new_date)
                        st.session_state.show_date_picker = False
                        st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
    
    countdown_days = get_countdown()
    if countdown_days is not None and countdown_days >= 0:
        st.markdown(f"""
        <div class="home-card" style="text-align:center; padding: 30px 20px;">
            <div class="countdown-number">{countdown_days}</div>
            <div class="countdown-label">❤️ 天后见面 ❤️</div>
            <div class="countdown-days">距离 {st.session_state.next_meeting_date.strftime('%Y年%m月%d日')}</div>
        </div>
        """, unsafe_allow_html=True)
    elif countdown_days is not None and countdown_days < 0:
        st.markdown(f"""
        <div class="home-card" style="text-align:center; padding: 30px 20px; border: 2px solid #FF6B6B;">
            <div style="font-size: 48px;">🎉</div>
            <div style="font-size: 24px; font-weight: 600; color: #FF6B6B;">今天就是见面日！</div>
            <div style="font-size: 16px; color: #8B7A6B; margin-top: 5px;">已过 {abs(countdown_days)} 天，珍惜在一起的时光 ❤️</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="home-card" style="text-align:center; padding: 30px 20px; border: 2px dashed rgba(245,166,35,0.3);">
            <div style="font-size: 24px; color: #A8947F;">💕 点击「设置见面日」记录下次见面的时间吧</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown('<div class="weather-grid">', unsafe_allow_html=True)
    
    if weather_hz:
        icon_hz = get_weather_icon(weather_hz["icon"])
        st.markdown(f"""
        <div class="weather-card">
            <div class="weather-city">🏠 杭州 · 他</div>
            <span class="weather-icon">{icon_hz}</span>
            <div class="weather-temp">{weather_hz["temp"]}°C</div>
            <div class="weather-text">{weather_hz["text"]}</div>
            <div class="weather-detail">💨 {weather_hz.get("wind_dir", "")} · 💧 {weather_hz.get("humidity", "")}%</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="weather-card">
            <div class="weather-city">🏠 杭州 · 他</div>
            <div style="color:#A8947F; padding:20px 0;">🌤️ 天气数据获取中...</div>
        </div>
        """, unsafe_allow_html=True)
    
    if weather_hc:
        icon_hc = get_weather_icon(weather_hc["icon"])
        st.markdown(f"""
        <div class="weather-card">
            <div class="weather-city">🏠 韩城 · 她</div>
            <span class="weather-icon">{icon_hc}</span>
            <div class="weather-temp">{weather_hc["temp"]}°C</div>
            <div class="weather-text">{weather_hc["text"]}</div>
            <div class="weather-detail">💨 {weather_hc.get("wind_dir", "")} · 💧 {weather_hc.get("humidity", "")}%</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="weather-card">
            <div class="weather-city">🏠 韩城 · 她</div>
            <div style="color:#A8947F; padding:20px 0;">🌤️ 天气数据获取中...</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✈️ 旅行", key="go_travel_home", use_container_width=True):
            st.session_state.page = "travel"
            st.rerun()
    with col2:
        if st.button("📖 做菜", key="go_cook_home", use_container_width=True):
            st.session_state.page = "cook"
            st.rerun()


# ==================== 做菜板块 ====================
def cook_page():
    import datetime
    import dashscope
    from dashscope import Generation, MultiModalConversation
    import os
    import base64
    import re
    import json
    import tempfile

    if "cook_detail" in st.query_params:
        try:
            detail_data = st.query_params["cook_detail"]
            detail_info = json.loads(detail_data)

            st.markdown("# 📖 我们家的小饭桌")

            with st.form(key="detail_edit_form"):
                new_name = st.text_input("菜名", value=detail_info.get("name", ""))
                cat_list = [cat[1] for cat in get_categories()]
                current_cat = detail_info.get("category", "未分类")
                if current_cat not in cat_list:
                    cat_list.append(current_cat)
                cat_index = cat_list.index(current_cat) if current_cat in cat_list else 0
                new_category = st.selectbox("类别", options=cat_list, index=cat_index)
                new_ingredients = st.text_area("食材", value=detail_info.get("ingredients", ""), height=150)
                new_steps = st.text_area("做法", value=detail_info.get("steps", ""), height=200)

                submitted = st.form_submit_button("💾 保存修改")

                if submitted:
                    if not new_name.strip():
                        st.error("菜名不能为空")
                    else:
                        existing = recipe_exists(new_name.strip())
                        if existing and new_name.strip() != detail_info.get("name", "").strip():
                            st.error(f"❌ 菜名“{new_name}”已存在，请修改")
                        else:
                            cat_id = None
                            for cid, cname, _, _ in get_categories():
                                if cname == new_category:
                                    cat_id = cid
                                    break
                            if cat_id is None:
                                st.error(f"分类“{new_category}”不存在，请先在左侧添加")
                            else:
                                if "id" in detail_info and detail_info["id"]:
                                    update_recipe(
                                        detail_info["id"],
                                        new_name.strip(),
                                        new_ingredients,
                                        new_steps,
                                        cat_id
                                    )
                                    st.success("✅ 菜谱已更新")
                                else:
                                    if recipe_exists(new_name.strip()):
                                        st.error(f"❌ 菜名“{new_name}”已存在，无法新增")
                                    else:
                                        add_recipe(new_name.strip(), new_ingredients, new_steps, cat_id)
                                        st.success(f"✅ 已添加 {new_name}")
                                st.rerun()

            if st.button("← 返回推荐列表"):
                if "cook_detail" in st.query_params:
                    del st.query_params["cook_detail"]
                st.rerun()

            st.stop()
        except Exception as e:
            st.error(f"加载详情失败：{e}")
            st.query_params.clear()
            st.rerun()

    if "selected_category_id" not in st.session_state:
        st.session_state.selected_category_id = None
    else:
        if "from_category_click" not in st.session_state:
            st.session_state.selected_category_id = None
        else:
            st.session_state.from_category_click = False

    if "back_category_id" in st.query_params:
        try:
            st.session_state.selected_category_id = int(st.query_params["back_category_id"])
            st.session_state.from_category_click = True
        except:
            pass

    if "back_search_mode" in st.query_params:
        mode = st.query_params["back_search_mode"]
        st.session_state.ai_mode = mode

        if "back_search_keyword" in st.query_params:
            keyword = st.query_params["back_search_keyword"]
            if mode == "从菜单中按菜名查询":
                st.session_state["search_name"] = keyword
                st.session_state.search_display = search_menu_by_name(keyword)
            elif mode == "从菜单中按食材查询":
                st.session_state["search_ingredient"] = keyword
                st.session_state.search_display = search_menu_by_ingredient(keyword)

        del st.query_params["back_search_mode"]
        if "back_search_keyword" in st.query_params:
            del st.query_params["back_search_keyword"]
        st.rerun()

    def get_categories():
        conn = get_db_connection()
        if conn is None:
            return []
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, icon, sort_order FROM categories ORDER BY sort_order, id")
        rows = cursor.fetchall()
        conn.close()
        return rows

    def add_category(name, icon="📋"):
        conn = get_db_connection()
        if conn is None:
            return False
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO categories (name, icon) VALUES (%s, %s)",
            (name, icon)
        )
        conn.commit()
        conn.close()
        return True

    def update_category(cat_id, new_name):
        conn = get_db_connection()
        if conn is None:
            return False
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE categories SET name = %s WHERE id = %s",
            (new_name, cat_id)
        )
        conn.commit()
        conn.close()
        return True

    def delete_category(cat_id):
        conn = get_db_connection()
        if conn is None:
            return False
        cursor = conn.cursor()
        cursor.execute("DELETE FROM categories WHERE id = %s", (cat_id,))
        conn.commit()
        conn.close()
        return True

    def get_recipes_by_category(category_id):
        conn = get_db_connection()
        if conn is None:
            return []
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, ingredients, steps, cook_count FROM recipes WHERE category_id = %s ORDER BY name",
            (category_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return rows

    def add_recipe(name, ingredients, steps, category_id):
        conn = get_db_connection()
        if conn is None:
            return False
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO recipes (name, ingredients, steps, category_id) VALUES (%s, %s, %s, %s)",
            (name, ingredients, steps, category_id)
        )
        conn.commit()
        conn.close()
        return True

    def update_recipe(recipe_id, name, ingredients, steps, category_id):
        conn = get_db_connection()
        if conn is None:
            return False
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE recipes SET name = %s, ingredients = %s, steps = %s, category_id = %s WHERE id = %s",
            (name, ingredients, steps, category_id, recipe_id)
        )
        conn.commit()
        conn.close()
        return True

    def delete_recipe(recipe_id):
        conn = get_db_connection()
        if conn is None:
            return False
        cursor = conn.cursor()
        cursor.execute("DELETE FROM recipes WHERE id = %s", (recipe_id,))
        conn.commit()
        conn.close()
        return True

    def increment_cook_count(recipe_id):
        conn = get_db_connection()
        if conn is None:
            return False
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE recipes SET cook_count = cook_count + 1 WHERE id = %s",
            (recipe_id,)
        )
        conn.commit()
        conn.close()
        return True

    def get_category_name(cat_id):
        conn = get_db_connection()
        if conn is None:
            return (None, None)
        cursor = conn.cursor()
        cursor.execute("SELECT name, icon FROM categories WHERE id = %s", (cat_id,))
        row = cursor.fetchone()
        conn.close()
        return row if row else (None, None)

    def recipe_exists(name):
        conn = get_db_connection()
        if conn is None:
            return False
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM recipes WHERE TRIM(name) = %s", (name.strip(),))
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0

    def search_menu_by_ingredient(keyword):
        SYNONYM_MAP = {
            "西红柿": "番茄",
            "马铃薯": "土豆",
            "洋芋": "土豆",
        }
        keywords = [k.strip() for k in re.split('[,，、\\s]+', keyword) if k.strip()]
        if not keywords:
            return []
        normalized = [SYNONYM_MAP.get(k, k) for k in keywords]
        normalized = list(set(normalized))

        conn = get_db_connection()
        if conn is None:
            return []
        cursor = conn.cursor()
        conditions = " AND ".join(["ingredients LIKE %s"] * len(normalized))
        sql = f"""
            SELECT id, name, ingredients, steps, cook_count, category_id 
            FROM recipes 
            WHERE {conditions} 
            ORDER BY name
        """
        params = [f"%{k}%" for k in normalized]
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        result = []
        for row in rows:
            cat_name = "未分类"
            for cid, cname, _, _ in get_categories():
                if cid == row[5]:
                    cat_name = cname
                    break
            result.append({
                "id": row[0],
                "name": row[1],
                "ingredients": row[2],
                "steps": row[3],
                "cook_count": row[4],
                "category": cat_name,
                "category_id": row[5]
            })
        return result

    def search_menu_by_name(keyword):
        keywords = [k.strip() for k in re.split('[,，、\\s]+', keyword) if k.strip()]
        if not keywords:
            return []
        conn = get_db_connection()
        if conn is None:
            return []
        cursor = conn.cursor()
        conditions = " AND ".join(["name LIKE %s"] * len(keywords))
        sql = f"""
            SELECT id, name, ingredients, steps, cook_count, category_id 
            FROM recipes 
            WHERE {conditions} 
            ORDER BY name
        """
        params = [f"%{k}%" for k in keywords]
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        result = []
        for row in rows:
            cat_name = "未分类"
            for cid, cname, _, _ in get_categories():
                if cid == row[5]:
                    cat_name = cname
                    break
            result.append({
                "id": row[0],
                "name": row[1],
                "ingredients": row[2],
                "steps": row[3],
                "cook_count": row[4],
                "category": cat_name,
                "category_id": row[5]
            })
        return result

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

    col_title, col_btn = st.columns([5, 1])
    with col_title:
        st.markdown("# 📖 我们家的小饭桌")
    with col_btn:
        if st.button("🏠 返回首页", key="back_home_top"):
            st.session_state.page = "home"
            st.session_state.selected_category_id = None
            st.session_state.ai_global_result = []
            st.session_state.ai_global_raw = None
            st.session_state.recommended_names = []
            st.session_state.image_recog_result = None
            st.session_state.editing_category_idx = None
            st.session_state.search_display = []
            st.rerun()

    if "edit_category_id" not in st.session_state:
        st.session_state.edit_category_id = None
    if "edit_recipe_id" not in st.session_state:
        st.session_state.edit_recipe_id = None
    if "category_ai_result" not in st.session_state:
        st.session_state.category_ai_result = {}
    if "recommended_names" not in st.session_state:
        st.session_state.recommended_names = []
    if "ai_global_result" not in st.session_state:
        st.session_state.ai_global_result = []
    if "ai_global_raw" not in st.session_state:
        st.session_state.ai_global_raw = None
    if "ai_mode" not in st.session_state:
        st.session_state.ai_mode = "按食材推荐"
    if "image_recog_result" not in st.session_state:
        st.session_state.image_recog_result = None
    if "editing_category_idx" not in st.session_state:
        st.session_state.editing_category_idx = None
    if "prev_result_len" not in st.session_state:
        st.session_state.prev_result_len = 0
    if "search_result" not in st.session_state:
        st.session_state.search_result = None
    if "search_display" not in st.session_state:
        st.session_state.search_display = []
    if "upload_counter" not in st.session_state:
        st.session_state.upload_counter = 0
    if "ai_expander_state" not in st.session_state:
        st.session_state.ai_expander_state = {}
    if "search_category_expander_state" not in st.session_state:
        st.session_state.search_category_expander_state = {}

    categories = get_categories()
    category_names = ["主食", "热菜", "凉菜", "汤类", "减肥专栏"]

    current_len = len(st.session_state.ai_global_result)
    if st.session_state.prev_result_len != current_len:
        st.session_state.editing_category_idx = None
        st.session_state.prev_result_len = current_len
        new_keys = set()
        for idx, recipe in enumerate(st.session_state.ai_global_result):
            base_key = f"{idx}_{recipe['name']}"
            new_keys.add(f"ai_expander_{base_key}")
        for key in list(st.session_state.ai_expander_state.keys()):
            if key not in new_keys:
                del st.session_state.ai_expander_state[key]
        for key in new_keys:
            if key not in st.session_state.ai_expander_state:
                st.session_state.ai_expander_state[key] = False

    col_left, col_right = st.columns([1.2, 3])

    with col_left:
        st.markdown("**📋 分类管理**")
        if not categories:
            st.info("暂无分类，请先添加")
        else:
            for cat_id, cat_name, icon, sort_order in categories:
                conn = get_db_connection()
                if conn is None:
                    count = 0
                else:
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
        st.markdown("**➕ 新增分类**")
        new_cat_name = st.text_input("分类名称", key="new_cat_name", placeholder="输入新分类名称")
        new_cat_icon = st.text_input("图标（选填）", key="new_cat_icon", placeholder="如：🍳", value="📋")
        if st.button("添加分类", key="add_category_btn"):
            if new_cat_name and new_cat_name.strip():
                add_category(new_cat_name.strip(), new_cat_icon or "📋")
                st.rerun()
            else:
                st.error("请输入分类名称")

    with col_right:
        if st.session_state.selected_category_id is None:
            mode_list = ["按食材推荐", "按菜名推荐", "从菜单中按食材查询", "从菜单中按菜名查询"]
            try:
                radio_index = mode_list.index(st.session_state.ai_mode)
            except ValueError:
                radio_index = 0

            with st.expander("🤖 AI 推荐菜", expanded=True):
                ai_mode = st.radio(
                    "选择模式",
                    mode_list,
                    horizontal=False,
                    key="ai_mode_radio",
                    index=radio_index
                )
                st.session_state.ai_mode = ai_mode

                # ---------- 模式1 ----------
                if st.session_state.ai_mode == "按食材推荐":
                    count = st.slider("菜品数量", min_value=1, max_value=5, value=3, key="ai_count_right")
                    ai_input = st.text_input("输入食材（用中文逗号或空格分隔）", key="ai_ingredients_right", placeholder="例如：土豆,鸡蛋")
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("推荐", key="ai_recommend_btn"):
                            if not ai_input.strip():
                                st.error("请输入食材")
                            else:
                                dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
                                if not dashscope.api_key:
                                    st.error("未找到 API Key，请检查 .env 文件")
                                else:
                                    st.session_state.ai_global_result = []
                                    st.session_state.recommended_names = []
                                    st.session_state.editing_category_idx = None
                                    with st.spinner("AI 正在思考..."):
                                        prompt = f"""你是一个厨艺高超的AI厨师。请根据以下食材推荐 {count} 道菜：
食材：{ai_input}
请按以下格式返回，每道菜之间用"---"分隔：
菜名：XXX
类别：XXX
食材：XXX, XXX, XXX
做法：
1. XXX
2. XXX
3. XXX
---
（下一道菜）
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
                                                    if len(recipes) > count:
                                                        recipes = recipes[:count]
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
                                st.error("请先输入食材")
                            else:
                                dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
                                if not dashscope.api_key:
                                    st.error("未找到 API Key，请检查 .env 文件")
                                else:
                                    with st.spinner("AI 正在思考..."):
                                        exclude_names = st.session_state.recommended_names
                                        exclude_note = ""
                                        if exclude_names:
                                            exclude_note = f"\n请不要再推荐以下菜品：{', '.join(exclude_names)}"
                                        count = st.session_state.get("ai_count_right", 3)
                                        prompt = f"""你是一个厨艺高超的AI厨师。请根据以下食材推荐 {count} 道菜：
食材：{ai_input}{exclude_note}
请按以下格式返回，每道菜之间用"---"分隔：
菜名：XXX
类别：XXX
食材：XXX, XXX, XXX
做法：
1. XXX
2. XXX
3. XXX
---
（下一道菜）
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
                                                    if len(recipes) > count:
                                                        recipes = recipes[:count]
                                                    for r in recipes:
                                                        if r["name"] not in st.session_state.recommended_names:
                                                            st.session_state.recommended_names.append(r["name"])
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

                # ---------- 模式2 ----------
                elif st.session_state.ai_mode == "按菜名推荐":
                    count = st.slider("菜品数量", min_value=1, max_value=5, value=1, key="ai_variant_count")
                    ai_input = st.text_input("输入菜名", key="ai_dish_name", placeholder="例如：番茄炒蛋")
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("推荐", key="ai_recommend_btn"):
                            if not ai_input.strip():
                                st.error("请输入菜名")
                            else:
                                dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
                                if not dashscope.api_key:
                                    st.error("未找到 API Key，请检查 .env 文件")
                                else:
                                    st.session_state.ai_global_result = []
                                    st.session_state.recommended_names = []
                                    st.session_state.editing_category_idx = None
                                    with st.spinner("AI 正在思考..."):
                                        prompt = f"""请提供菜名《{ai_input}》的 {count} 个不同版本的详细做法。
请按以下格式返回，每个版本之间用"---"分隔：
菜名：{ai_input}（特色描述）
类别：XXX
食材：XXX, XXX, XXX
做法：
1. XXX
2. XXX
3. XXX
---
（下一道菜）
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
                                                    if len(recipes) > count:
                                                        recipes = recipes[:count]
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
                                st.error("请先输入菜名")
                            else:
                                dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
                                if not dashscope.api_key:
                                    st.error("未找到 API Key，请检查 .env 文件")
                                else:
                                    with st.spinner("AI 正在查询..."):
                                        exclude_names = st.session_state.recommended_names
                                        exclude_note = ""
                                        if exclude_names:
                                            exclude_note = f"\n请不要再推荐以下菜品：{', '.join(exclude_names)}"
                                        count = st.session_state.get("ai_variant_count", 1)
                                        prompt = f"""请提供菜名《{ai_input}》的 {count} 个不同版本的详细做法。{exclude_note}
请按以下格式返回，每个版本之间用"---"分隔：
菜名：{ai_input}（特色描述）
类别：XXX
食材：XXX, XXX, XXX
做法：
1. XXX
2. XXX
3. XXX
---
（下一道菜）
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
                                                    if len(recipes) > count:
                                                        recipes = recipes[:count]
                                                    for r in recipes:
                                                        if r["name"] not in st.session_state.recommended_names:
                                                            st.session_state.recommended_names.append(r["name"])
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

                # ---------- 模式3 ----------
                elif st.session_state.ai_mode == "从菜单中按食材查询":
                    default_keyword = st.session_state.get("search_ingredient", "")
                    search_keyword = st.text_input("输入食材关键词（多个用逗号/空格分隔）", key="search_ingredient", placeholder="例如：土豆,牛肉", value=default_keyword)
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("🔍 搜索", key="search_ingredient_btn"):
                            if not search_keyword.strip():
                                st.error("请输入关键词")
                            else:
                                st.session_state.search_display = search_menu_by_ingredient(search_keyword.strip())
                                st.session_state.search_category_expander_state = {}
                                st.rerun()
                    with col_btn2:
                        if st.button("🗑️ 清空", key="clear_search_ingredient"):
                            st.session_state.search_display = []
                            if "search_ingredient" in st.session_state:
                                del st.session_state["search_ingredient"]
                            st.rerun()

                    if st.session_state.search_display:
                        result_list = st.session_state.search_display
                        st.divider()
                        col_title, col_close = st.columns([5, 1])
                        with col_title:
                            st.subheader(f"📋 搜索结果（共 {len(result_list)} 道）")
                        with col_close:
                            if st.button("❌ 关闭", key="close_search_result"):
                                st.session_state.search_display = []
                                st.rerun()

                        grouped = {}
                        for item in result_list:
                            cat = item.get("category", "未分类")
                            if cat not in grouped:
                                grouped[cat] = []
                            grouped[cat].append(item)

                        for cat_name, items in grouped.items():
                            cat_expander_key = f"search_cat_{cat_name}"
                            if cat_expander_key not in st.session_state.search_category_expander_state:
                                st.session_state.search_category_expander_state[cat_expander_key] = True

                            with st.expander(f"{cat_name}（{len(items)}）", expanded=st.session_state.search_category_expander_state[cat_expander_key]):
                                for idx, item in enumerate(items):
                                    base_key = f"search_{item['id']}_{idx}"

                                    st.markdown(f"**{item['name']}**")
                                    new_name = st.text_input(
                                        "菜名",
                                        value=item['name'],
                                        key=f"search_name_{base_key}",
                                        placeholder="修改菜名",
                                        label_visibility="collapsed"
                                    )
                                    cat_list = [cat[1] for cat in categories]
                                    current_cat_index = cat_list.index(item['category']) if item['category'] in cat_list else 0
                                    new_category = st.selectbox(
                                        "类别",
                                        options=cat_list,
                                        index=current_cat_index,
                                        key=f"search_cat_{base_key}",
                                        label_visibility="collapsed"
                                    )
                                    new_ingredients = st.text_area(
                                        "食材",
                                        value=item['ingredients'],
                                        key=f"search_ing_{base_key}",
                                        height=100,
                                        label_visibility="collapsed"
                                    )
                                    new_steps = st.text_area(
                                        "做法",
                                        value=item['steps'],
                                        key=f"search_step_{base_key}",
                                        height=150,
                                        label_visibility="collapsed"
                                    )

                                    col_update1, col_update2 = st.columns(2)
                                    with col_update1:
                                        if st.button("💾 更新当前菜", key=f"update_search_{base_key}"):
                                            if not new_name.strip():
                                                st.error("菜名不能为空")
                                            elif not new_ingredients.strip():
                                                st.error("食材不能为空")
                                            elif not new_steps.strip():
                                                st.error("做法不能为空")
                                            else:
                                                if new_name.strip() != item['name'] and recipe_exists(new_name.strip()):
                                                    st.error(f"❌ 菜名“{new_name}”已存在，请修改")
                                                else:
                                                    item['name'] = new_name.strip()
                                                    item['category'] = new_category
                                                    item['ingredients'] = new_ingredients.strip()
                                                    item['steps'] = new_steps.strip()
                                                    st.rerun()
                                    with col_update2:
                                        if st.button("🔄 恢复默认", key=f"reset_search_{base_key}"):
                                            st.warning("请重新搜索以恢复原始数据")

                                    st.divider()

                                    col_confirm, col_skip = st.columns(2)
                                    with col_confirm:
                                        if st.button(f"✅ 添加", key=f"confirm_search_{base_key}"):
                                            cat_name_to_id = {cat[1]: cat[0] for cat in categories}
                                            cat_id = cat_name_to_id.get(item['category'])
                                            if cat_id is None:
                                                st.error(f"类别“{item['category']}”不存在，请先在左侧添加该分类")
                                            elif recipe_exists(item['name']):
                                                st.error(f"❌ 菜名“{item['name']}”已存在，请修改菜名后再添加")
                                            else:
                                                add_recipe(item['name'], item['ingredients'], item['steps'], cat_id)
                                                st.session_state.search_display = [it for it in st.session_state.search_display if it['id'] != item['id']]
                                                st.success(f"✅ 已添加 {item['name']}")
                                                st.rerun()
                                    with col_skip:
                                        if st.button(f"❌ 跳过", key=f"skip_search_{base_key}"):
                                            st.session_state.search_display = [it for it in st.session_state.search_display if it['id'] != item['id']]
                                            st.rerun()
                                    st.divider()
                    else:
                        if st.session_state.get("search_ingredient"):
                            st.info("未找到匹配的菜品，试试其他关键词")

                # ---------- 模式4 ----------
                elif st.session_state.ai_mode == "从菜单中按菜名查询":
                    default_keyword = st.session_state.get("search_name", "")
                    search_keyword = st.text_input("输入菜名关键词（多个用逗号/空格分隔）", key="search_name", placeholder="例如：土豆,牛肉", value=default_keyword)
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("🔍 搜索", key="search_name_btn"):
                            if not search_keyword.strip():
                                st.error("请输入关键词")
                            else:
                                st.session_state.search_display = search_menu_by_name(search_keyword.strip())
                                st.session_state.search_category_expander_state = {}
                                st.rerun()
                    with col_btn2:
                        if st.button("🗑️ 清空", key="clear_search_name"):
                            st.session_state.search_display = []
                            if "search_name" in st.session_state:
                                del st.session_state["search_name"]
                            st.rerun()

                    if st.session_state.search_display:
                        result_list = st.session_state.search_display
                        st.divider()
                        col_title, col_close = st.columns([5, 1])
                        with col_title:
                            st.subheader(f"📋 搜索结果（共 {len(result_list)} 道）")
                        with col_close:
                            if st.button("❌ 关闭", key="close_search_result"):
                                st.session_state.search_display = []
                                st.rerun()

                        grouped = {}
                        for item in result_list:
                            cat = item.get("category", "未分类")
                            if cat not in grouped:
                                grouped[cat] = []
                            grouped[cat].append(item)

                        for cat_name, items in grouped.items():
                            cat_expander_key = f"search_cat_{cat_name}"
                            if cat_expander_key not in st.session_state.search_category_expander_state:
                                st.session_state.search_category_expander_state[cat_expander_key] = True

                            with st.expander(f"{cat_name}（{len(items)}）", expanded=st.session_state.search_category_expander_state[cat_expander_key]):
                                for idx, item in enumerate(items):
                                    base_key = f"search_{item['id']}_{idx}"

                                    st.markdown(f"**{item['name']}**")
                                    new_name = st.text_input(
                                        "菜名",
                                        value=item['name'],
                                        key=f"search_name_{base_key}",
                                        placeholder="修改菜名",
                                        label_visibility="collapsed"
                                    )
                                    cat_list = [cat[1] for cat in categories]
                                    current_cat_index = cat_list.index(item['category']) if item['category'] in cat_list else 0
                                    new_category = st.selectbox(
                                        "类别",
                                        options=cat_list,
                                        index=current_cat_index,
                                        key=f"search_cat_{base_key}",
                                        label_visibility="collapsed"
                                    )
                                    new_ingredients = st.text_area(
                                        "食材",
                                        value=item['ingredients'],
                                        key=f"search_ing_{base_key}",
                                        height=100,
                                        label_visibility="collapsed"
                                    )
                                    new_steps = st.text_area(
                                        "做法",
                                        value=item['steps'],
                                        key=f"search_step_{base_key}",
                                        height=150,
                                        label_visibility="collapsed"
                                    )

                                    col_update1, col_update2 = st.columns(2)
                                    with col_update1:
                                        if st.button("💾 更新当前菜", key=f"update_search_{base_key}"):
                                            if not new_name.strip():
                                                st.error("菜名不能为空")
                                            elif not new_ingredients.strip():
                                                st.error("食材不能为空")
                                            elif not new_steps.strip():
                                                st.error("做法不能为空")
                                            else:
                                                if new_name.strip() != item['name'] and recipe_exists(new_name.strip()):
                                                    st.error(f"❌ 菜名“{new_name}”已存在，请修改")
                                                else:
                                                    item['name'] = new_name.strip()
                                                    item['category'] = new_category
                                                    item['ingredients'] = new_ingredients.strip()
                                                    item['steps'] = new_steps.strip()
                                                    st.rerun()
                                    with col_update2:
                                        if st.button("🔄 恢复默认", key=f"reset_search_{base_key}"):
                                            st.warning("请重新搜索以恢复原始数据")

                                    st.divider()

                                    col_confirm, col_skip = st.columns(2)
                                    with col_confirm:
                                        if st.button(f"✅ 添加", key=f"confirm_search_{base_key}"):
                                            cat_name_to_id = {cat[1]: cat[0] for cat in categories}
                                            cat_id = cat_name_to_id.get(item['category'])
                                            if cat_id is None:
                                                st.error(f"类别“{item['category']}”不存在，请先在左侧添加该分类")
                                            elif recipe_exists(item['name']):
                                                st.error(f"❌ 菜名“{item['name']}”已存在，请修改菜名后再添加")
                                            else:
                                                add_recipe(item['name'], item['ingredients'], item['steps'], cat_id)
                                                st.session_state.search_display = [it for it in st.session_state.search_display if it['id'] != item['id']]
                                                st.success(f"✅ 已添加 {item['name']}")
                                                st.rerun()
                                    with col_skip:
                                        if st.button(f"❌ 跳过", key=f"skip_search_{base_key}"):
                                            st.session_state.search_display = [it for it in st.session_state.search_display if it['id'] != item['id']]
                                            st.rerun()
                                    st.divider()
                    else:
                        if st.session_state.get("search_name"):
                            st.info("未找到匹配的菜品，试试其他关键词")

                # ---------- 显示 AI 推荐结果（模式1&2） ----------
                if st.session_state.ai_mode in ["按食材推荐", "按菜名推荐"]:
                    if st.session_state.ai_global_result:
                        result_list = st.session_state.ai_global_result
                        st.divider()

                        col_title, col_close = st.columns([5, 1])
                        with col_title:
                            st.subheader(f"📋 推荐结果（共 {len(result_list)} 道）")
                            if st.session_state.recommended_names and st.session_state.ai_mode == "按食材推荐":
                                st.caption(f"已排除：{', '.join(st.session_state.recommended_names)}")
                        with col_close:
                            if st.button("❌ 关闭", key="close_ai_result"):
                                st.session_state.ai_global_result = []
                                st.session_state.ai_global_raw = None
                                st.session_state.editing_category_idx = None
                                st.rerun()

                        for idx, recipe in enumerate(result_list):
                            base_key = f"{idx}_{recipe['name']}"
                            expander_key = f"ai_expander_{base_key}"
                            if expander_key not in st.session_state.ai_expander_state:
                                st.session_state.ai_expander_state[expander_key] = False

                            with st.expander(f"**{recipe['name']}**", expanded=st.session_state.ai_expander_state[expander_key]):
                                new_name = st.text_input(
                                    "菜名",
                                    value=recipe['name'],
                                    key=f"ai_name_{base_key}",
                                    placeholder="修改菜名"
                                )
                                cat_list = [cat[1] for cat in categories]
                                current_cat_index = cat_list.index(recipe['category']) if recipe['category'] in cat_list else 0
                                new_category = st.selectbox(
                                    "类别",
                                    options=cat_list,
                                    index=current_cat_index,
                                    key=f"ai_cat_{base_key}"
                                )
                                new_ingredients = st.text_area(
                                    "食材",
                                    value=recipe['ingredients'],
                                    key=f"ai_ing_{base_key}",
                                    height=100
                                )
                                new_steps = st.text_area(
                                    "做法",
                                    value=recipe['steps'],
                                    key=f"ai_step_{base_key}",
                                    height=150
                                )

                                col_update1, col_update2 = st.columns(2)
                                with col_update1:
                                    if st.button("💾 更新当前菜", key=f"update_ai_{base_key}"):
                                        if not new_name.strip():
                                            st.error("菜名不能为空")
                                        elif not new_ingredients.strip():
                                            st.error("食材不能为空")
                                        elif not new_steps.strip():
                                            st.error("做法不能为空")
                                        else:
                                            if new_name.strip() != recipe['name'] and recipe_exists(new_name.strip()):
                                                st.error(f"❌ 菜名“{new_name}”已存在，请修改")
                                            else:
                                                result_list[idx]['name'] = new_name.strip()
                                                result_list[idx]['category'] = new_category
                                                result_list[idx]['ingredients'] = new_ingredients.strip()
                                                result_list[idx]['steps'] = new_steps.strip()
                                                st.session_state.ai_expander_state[expander_key] = True
                                                st.rerun()
                                with col_update2:
                                    if st.button("🔄 恢复默认", key=f"reset_ai_{base_key}"):
                                        st.warning("此功能暂未实现，如需恢复请重新生成推荐")

                                st.divider()

                                col_confirm, col_skip = st.columns(2)
                                with col_confirm:
                                    final_name = st.session_state.get(f"ai_name_{base_key}", recipe['name']).strip()
                                    if not final_name:
                                        final_name = recipe['name']
                                    final_category = st.session_state.get(f"ai_cat_{base_key}", recipe['category'])
                                    final_ingredients = st.session_state.get(f"ai_ing_{base_key}", recipe['ingredients']).strip()
                                    final_steps = st.session_state.get(f"ai_step_{base_key}", recipe['steps']).strip()

                                    if st.button(f"✅ 添加", key=f"confirm_ai_{base_key}"):
                                        cat_name_to_id = {cat[1]: cat[0] for cat in categories}
                                        cat_id = cat_name_to_id.get(final_category)
                                        if cat_id is None:
                                            st.error(f"类别“{final_category}”不存在，请先在左侧添加该分类")
                                        elif recipe_exists(final_name):
                                            st.error(f"❌ 菜名“{final_name}”已存在，请修改菜名后再添加")
                                        else:
                                            add_recipe(final_name, final_ingredients, final_steps, cat_id)
                                            st.session_state.ai_global_result.pop(idx)
                                            st.success(f"✅ 已添加 {final_name}")
                                            st.rerun()
                                with col_skip:
                                    if st.button(f"❌ 跳过", key=f"skip_ai_{base_key}"):
                                        st.session_state.ai_global_result.pop(idx)
                                        st.rerun()

                    elif st.session_state.ai_global_raw is not None:
                        raw = st.session_state.ai_global_raw
                        st.divider()
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
                                    elif recipe_exists(name):
                                        st.error(f"❌ 菜名“{name}”已存在，请修改菜名后再添加")
                                    else:
                                        add_recipe(name, ingredients, steps, cat_choice)
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
                            elif recipe_exists(name):
                                st.error(f"❌ 菜名“{name}”已存在，请修改菜名后再添加")
                            else:
                                add_recipe(name, ingredients, steps, cat_choice)
                                st.success(f"✅ 已添加 {name}")
                                st.rerun()

                else:
                    st.markdown("**上传包含菜名和做法的截图（如抖音截图）**")
                    file_key = f"recipe_image_upload_{st.session_state.upload_counter}"
                    uploaded_file = st.file_uploader("选择图片", type=["jpg", "jpeg", "png", "webp"], key=file_key)

                    if uploaded_file is not None:
                        st.image(uploaded_file, width=300)

                        if st.button("🔍 识别图片", key="recognize_image"):
                            with st.spinner("AI 正在识别图片..."):
                                dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
                                if not dashscope.api_key:
                                    st.error("未找到 API Key，请检查 .env 文件")
                                else:
                                    prompt = """请识别这张图片中的菜谱信息。如果图片中包含菜名、食材和做法，请按以下格式返回：
菜名：XXX
类别：XXX（从以下选择：主食、热菜、凉菜、汤类、减肥专栏）
食材：XXX, XXX, XXX（请标注精确用量，按两人份，食材要详细到克、毫升、个等）
做法：
1. XXX（详细步骤，包括火候、时间、状态判断，越详细越好）

如果图片中没有菜谱信息，请返回：未识别到菜谱信息"""
                                    temp_path = None
                                    try:
                                        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
                                            tmp_file.write(uploaded_file.getvalue())
                                            temp_path = tmp_file.name
                                        response = MultiModalConversation.call(
                                            model="qwen-vl-plus",
                                            messages=[
                                                {
                                                    "role": "user",
                                                    "content": [
                                                        {"image": temp_path},
                                                        {"text": prompt}
                                                    ]
                                                }
                                            ]
                                        )
                                        if response.status_code == 200:
                                            raw_content = response.output.choices[0].message.content
                                            if isinstance(raw_content, list):
                                                text_parts = []
                                                for item in raw_content:
                                                    if isinstance(item, dict) and "text" in item:
                                                        text_parts.append(item["text"])
                                                    elif isinstance(item, str):
                                                        text_parts.append(item)
                                                content = "".join(text_parts)
                                            else:
                                                content = raw_content
                                            st.session_state.image_recog_result = content
                                            st.rerun()
                                        else:
                                            st.error(f"识别失败：{response.message}")
                                    except Exception as e:
                                        st.error(f"识别出错：{e}")
                                    finally:
                                        if temp_path and os.path.exists(temp_path):
                                            try:
                                                os.unlink(temp_path)
                                            except:
                                                pass

                        if st.session_state.image_recog_result:
                            result_text = st.session_state.image_recog_result
                            st.divider()
                            st.subheader("📋 识别结果")
                            st.text(result_text)

                            lines = result_text.strip().split('\n')
                            recog_name = ""
                            recog_ingredients = ""
                            recog_steps = ""
                            recog_category = ""
                            current_section = None
                            ingredients_lines = []
                            steps_lines = []

                            for line in lines:
                                line = line.strip()
                                if not line:
                                    continue
                                if "菜名" in line:
                                    if "：" in line:
                                        recog_name = line.split("：")[-1].strip()
                                    elif ":" in line:
                                        recog_name = line.split(":")[-1].strip()
                                    continue
                                if "类别" in line:
                                    if "：" in line:
                                        recog_category = line.split("：")[-1].strip()
                                    elif ":" in line:
                                        recog_category = line.split(":")[-1].strip()
                                    continue
                                if "食材" in line:
                                    if "：" in line:
                                        rest = line.split("：")[-1].strip()
                                        if rest and rest != "XXX" and "克" not in rest:
                                            recog_ingredients = rest
                                            current_section = None
                                        else:
                                            current_section = 'ingredients'
                                    elif ":" in line:
                                        rest = line.split(":")[-1].strip()
                                        if rest and rest != "XXX" and "克" not in rest:
                                            recog_ingredients = rest
                                            current_section = None
                                        else:
                                            current_section = 'ingredients'
                                    else:
                                        current_section = 'ingredients'
                                    continue
                                if "做法" in line:
                                    if "：" in line:
                                        rest = line.split("：")[-1].strip()
                                        if rest and rest != "XXX" and "1." not in rest:
                                            recog_steps = rest
                                            current_section = None
                                        else:
                                            current_section = 'steps'
                                    elif ":" in line:
                                        rest = line.split(":")[-1].strip()
                                        if rest and rest != "XXX" and "1." not in rest:
                                            recog_steps = rest
                                            current_section = None
                                        else:
                                            current_section = 'steps'
                                    else:
                                        current_section = 'steps'
                                    continue
                                if current_section == 'ingredients':
                                    cleaned = re.sub(r'^[\s\-•*\d.]+', '', line).strip()
                                    if cleaned:
                                        ingredients_lines.append(cleaned)
                                    continue
                                if current_section == 'steps':
                                    if line:
                                        steps_lines.append(line)
                                    continue

                            if ingredients_lines and not recog_ingredients:
                                recog_ingredients = "，".join(ingredients_lines)
                            if steps_lines and not recog_steps:
                                recog_steps = "\n".join(steps_lines)

                            if recog_name and recog_ingredients and recog_steps:
                                st.success("✅ 识别成功！请确认信息后点击「保存到菜单」")
                                with st.form("add_from_image"):
                                    st.text_input("菜名", value=recog_name, key="img_name")
                                    st.text_area("食材", value=recog_ingredients, height=120, key="img_ingredients")
                                    st.text_area("做法", value=recog_steps, height=150, key="img_steps")
                                    cat_options = {cat_id: f"{icon} {name}" for cat_id, name, icon, _ in categories}
                                    if cat_options:
                                        if recog_category and recog_category in [name for _, name, _, _ in categories]:
                                            default_cat = next(cat_id for cat_id, name, _, _ in categories if name == recog_category)
                                        else:
                                            default_cat = list(cat_options.keys())[0] if cat_options else None
                                        cat_choice = st.selectbox(
                                            "所属分类",
                                            options=list(cat_options.keys()),
                                            format_func=lambda x: cat_options.get(x, "未分类"),
                                            key="img_cat",
                                            index=list(cat_options.keys()).index(default_cat) if default_cat in cat_options else 0
                                        )
                                    else:
                                        cat_choice = None
                                        st.warning("请先在左侧添加分类")
                                    submitted = st.form_submit_button("💾 保存到菜单")
                                    if submitted:
                                        if cat_choice is None:
                                            st.error("请先添加分类")
                                        elif recipe_exists(recog_name):
                                            st.error(f"❌ 菜名“{recog_name}”已存在，请修改菜名后再添加")
                                        else:
                                            add_recipe(recog_name, recog_ingredients, recog_steps, cat_choice)
                                            st.session_state.image_recog_result = None
                                            st.session_state.upload_counter += 1
                                            st.success(f"✅ 已添加 {recog_name}")
                                            st.rerun()
                                if st.button("❌ 放弃保存", key="discard_image_recog"):
                                    st.session_state.image_recog_result = None
                                    st.session_state.upload_counter += 1
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
                    for recipe_id, name, ingredients, steps, cook_count in recipes:
                        with st.expander(f"**{name}**"):
                            st.markdown(f"**食材**：\n{ingredients}")
                            st.markdown(f"**做法**：\n{steps}")

                            col1, col2, col3 = st.columns(3)
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

                            if st.session_state.edit_recipe_id == recipe_id:
                                st.divider()
                                st.subheader(f"✏️ 修改 {name}")
                                with st.form(f"edit_recipe_form_{recipe_id}"):
                                    new_name = st.text_input("菜名", value=name)
                                    new_ingredients = st.text_area("食材", value=ingredients, height=120)
                                    new_steps = st.text_area("做法", value=steps, height=150)
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
                                                update_recipe(recipe_id, new_name.strip(), new_ingredients, new_steps, new_cat)
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

# def travel_page():
#     st.write("🔍 1. travel_page 开始执行")
    
#     conn = get_db_connection()
#     st.write(f"🔍 2. conn = {conn}")
    
#     if conn is None:
#         st.error("❌ 数据库连接失败，请检查 Supabase 配置")
#         return
    
#     st.write("🔍 3. 数据库连接成功，继续执行...")
    
#     import folium
#     from streamlit_folium import st_folium
    
#     # 简单地图测试
#     m = folium.Map(location=[35.0, 105.0], zoom_start=4)
#     st_data = st_folium(m, width=700, height=500)
    
#     st.write("🔍 4. 地图渲染完成")
#==================== 旅行板块 ====================
def travel_page():
    import folium
    from streamlit_folium import st_folium
    import datetime
    import collections
    import os
    import hashlib

    if "delete_mode" not in st.session_state:
        st.session_state.delete_mode = False
    if "selected_photos" not in st.session_state:
        st.session_state.selected_photos = set()
    if "select_all_dates" not in st.session_state:
        st.session_state.select_all_dates = set()

    def toggle_photo_selection(photo_path):
        if photo_path in st.session_state.selected_photos:
            st.session_state.selected_photos.remove(photo_path)
        else:
            st.session_state.selected_photos.add(photo_path)

    def toggle_date_selection(date_str, photo_paths):
        all_selected = all(p in st.session_state.selected_photos for p in photo_paths)
        if all_selected:
            for p in photo_paths:
                st.session_state.selected_photos.discard(p)
        else:
            for p in photo_paths:
                st.session_state.selected_photos.add(p)

    if "city_detail" in st.query_params:
        city_name = st.query_params["city_detail"]

        st.markdown(f"# 📋 {city_name} 详情")
        st.caption("点击下方「返回旅行地图」回到地图页面")

        if st.button("← 返回旅行地图", key="back_to_map_from_detail"):
            st.session_state.delete_mode = False
            st.session_state.selected_photos = set()
            st.session_state.select_all_dates = set()
            st.query_params.clear()
            st.rerun()

        conn = get_db_connection()
        if conn is None:
            st.error("数据库连接失败，请稍后重试")
        else:
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

        st.subheader("🗺️ 实际游玩路线")
        conn = get_db_connection()
        if conn is None:
            st.error("数据库连接失败")
        else:
            cursor = conn.cursor()
            cursor.execute("SELECT route FROM city_details WHERE city_name = %s", (city_name,))
            route_row = cursor.fetchone()
            conn.close()
            current_route = route_row[0] if route_row and route_row[0] else ""

            new_route = st.text_area("编辑游玩路线", value=current_route, height=150, placeholder="记录你的实际行程...")
            if st.button("保存路线", key="save_route_detail"):
                conn = get_db_connection()
                if conn is not None:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO city_details (city_name, route) VALUES (%s, %s) ON CONFLICT (city_name) DO UPDATE SET route = %s",
                        (city_name, new_route, new_route)
                    )
                    conn.commit()
                    conn.close()
                    st.success("✅ 路线已保存")
                    st.rerun()

        st.subheader("📸 照片墙")

        col_action1, col_action2, col_action3 = st.columns([2, 2, 1])
        with col_action1:
            if st.button("🗑️ 批量删除" if not st.session_state.delete_mode else "❌ 取消选择", key="toggle_delete_mode"):
                st.session_state.delete_mode = not st.session_state.delete_mode
                if not st.session_state.delete_mode:
                    st.session_state.selected_photos = set()
                    st.session_state.select_all_dates = set()
                st.rerun()
        with col_action2:
            if st.session_state.delete_mode and st.session_state.selected_photos:
                if st.button(f"✅ 确认删除 ({len(st.session_state.selected_photos)}张)", key="confirm_batch_delete"):
                    conn = get_db_connection()
                    if conn is not None:
                        cursor = conn.cursor()
                        deleted_paths = set()
                        for photo_path in list(st.session_state.selected_photos):
                            try:
                                cursor.execute("DELETE FROM city_photos WHERE city_name = %s AND photo_path = %s", (city_name, photo_path))
                                if cursor.rowcount > 0:
                                    deleted_paths.add(photo_path)
                                    if os.path.exists(photo_path):
                                        try:
                                            os.remove(photo_path)
                                        except:
                                            pass
                            except Exception as e:
                                st.error(f"删除 {photo_path} 失败：{e}")
                        conn.commit()
                        conn.close()
                        st.session_state.selected_photos.difference_update(deleted_paths)
                        if not st.session_state.selected_photos:
                            st.session_state.delete_mode = False
                        st.success(f"✅ 已删除 {len(deleted_paths)} 张照片")
                        st.rerun()
        with col_action3:
            if st.session_state.delete_mode:
                st.caption(f"已选 {len(st.session_state.selected_photos)} 张")

        upload_option = st.radio("选择上传方式", ["本地文件", "图片链接"], horizontal=True, key="detail_upload_option")

        if "upload_counter" not in st.session_state:
            st.session_state.upload_counter = 0

        if upload_option == "本地文件":
            file_key = f"detail_file_uploader_{st.session_state.upload_counter}"
            uploaded_files = st.file_uploader(
                "选择照片",
                type=["jpg", "jpeg", "png", "gif"],
                accept_multiple_files=True,
                key=file_key
            )
            if uploaded_files and st.button("上传照片", key="detail_upload_local"):
                import os
                upload_dir = "static/uploads"
                if not os.path.exists(upload_dir):
                    os.makedirs(upload_dir)
                for file in uploaded_files:
                    base_name, ext = os.path.splitext(file.name)
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    unique_name = f"{city_name}_{timestamp}_{base_name}{ext}"
                    file_path = os.path.join(upload_dir, unique_name)
                    with open(file_path, "wb") as f:
                        f.write(file.getbuffer())
                    conn = get_db_connection()
                    if conn is not None:
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT INTO city_photos (city_name, photo_path, photo_type, shoot_date) VALUES (%s, %s, %s, %s)",
                            (city_name, file_path, "local", datetime.date.today())
                        )
                        conn.commit()
                        conn.close()
                st.success("✅ 照片已上传")
                st.session_state.upload_counter += 1
                st.rerun()
        else:
            photo_url = st.text_input("图片链接（URL）", key="detail_photo_url")
            shoot_date = st.date_input("拍摄日期", value=datetime.date.today(), key="detail_shoot_date")
            if photo_url and st.button("添加照片", key="detail_add_url_photo"):
                conn = get_db_connection()
                if conn is not None:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO city_photos (city_name, photo_path, photo_type, shoot_date) VALUES (%s, %s, %s, %s)",
                        (city_name, photo_url, "url", shoot_date)
                    )
                    conn.commit()
                    conn.close()
                    st.success("✅ 照片已添加")
                    st.rerun()

        conn = get_db_connection()
        if conn is not None:
            cursor = conn.cursor()
            cursor.execute("SELECT photo_path, photo_type, shoot_date FROM city_photos WHERE city_name = %s ORDER BY shoot_date DESC", (city_name,))
            photos = cursor.fetchall()
            conn.close()

            if photos:
                grouped = collections.defaultdict(list)
                for path, ptype, date in photos:
                    date_str = date.strftime("%Y-%m-%d") if date else "未分类"
                    grouped[date_str].append((path, ptype))

                for date_str, items in sorted(grouped.items(), reverse=True):
                    col_date, col_select_all = st.columns([5, 1])
                    with col_date:
                        st.caption(f"📅 {date_str}（{len(items)}张）")
                    with col_select_all:
                        if st.session_state.delete_mode:
                            date_photo_paths = [path for path, _ in items]
                            all_selected = all(p in st.session_state.selected_photos for p in date_photo_paths)
                            st.checkbox(
                                "全选",
                                key=f"select_all_date_{date_str}",
                                value=all_selected,
                                on_change=toggle_date_selection,
                                args=(date_str, date_photo_paths)
                            )

                    cols = st.columns(4)
                    for idx, (path, ptype) in enumerate(items):
                        path_hash = hashlib.md5(path.encode('utf-8')).hexdigest()[:8]
                        with cols[idx % 4]:
                            st.image(path, use_container_width=True)

                            if st.session_state.delete_mode:
                                checkbox_key = f"select_photo_{date_str}_{idx}_{path_hash}"
                                is_checked = path in st.session_state.selected_photos
                                st.checkbox(
                                    "选择",
                                    key=checkbox_key,
                                    value=is_checked,
                                    on_change=toggle_photo_selection,
                                    args=(path,)
                                )
                            else:
                                if st.button("🔍 查看大图", key=f"detail_img_{date_str}_{idx}_{path_hash}"):
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
            st.session_state.delete_mode = False
            st.session_state.selected_photos = set()
            st.session_state.select_all_dates = set()
            st.query_params.clear()
            st.rerun()

        st.stop()

    # ==================== 旅行地图页面 ====================
    col_title, col_btn = st.columns([6, 1])
    with col_title:
        st.markdown("# ✈️ 我们的旅行地图")
    with col_btn:
        if st.button("🏠 返回首页", key="back_home_travel"):
            st.session_state.delete_mode = False
            st.session_state.selected_photos = set()
            st.session_state.select_all_dates = set()
            st.session_state.page = "home"
            st.rerun()

    # ==================== 城市坐标 ====================
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

    conn = get_db_connection()
    if conn is not None:
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

        m = folium.Map(
            location=[35.0, 105.0],
            zoom_start=4,
            tiles='https://wprd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=9&x={x}&y={y}&z={z}',
            attr='高德地图'
        )

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

        col1, col2 = st.columns(2)
        with col1:
            st.metric("🏙️ 已点亮", len(visited))
        with col2:
            st.metric("📌 计划中", len(planned))

        st_data = st_folium(m, width=2300, height=800)

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
                col_exp_blank1, col_exp_mid, col_exp_blank2 = st.columns([0.00001, 1, 0.5])
                with col_exp_mid:
                    for key in sorted_keys:
                        cities = display_groups[key]
                        cities_sorted = sorted(cities, key=lambda c: visited_details.get(c, {}).get("date") or datetime.date(1970,1,1), reverse=True)
                        with st.expander(key):
                            for city in cities_sorted:
                                detail = visited_details.get(city, {})
                                date_str = detail.get("date").strftime("%Y-%m-%d") if detail.get("date") else "未知日期"

                                col_name, col_btns = st.columns([3, 0.6])
                                with col_name:
                                    st.write(f"{city}  {date_str}")
                                with col_btns:
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
                                                conn = get_db_connection()
                                                if conn is not None:
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

                                if st.button(f"查看 {city} 详情", key=f"detail_{city}"):
                                    st.session_state.selected_photos = set()
                                    st.session_state.select_all_dates = set()
                                    st.session_state.delete_mode = False
                                    st.query_params["city_detail"] = city
                                    st.rerun()
            else:
                    st.write("暂无已去城市")

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
                                    conn = get_db_connection()
                                    if conn is not None:
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

        st.divider()
        st.subheader("📝 添加旅行记录")

        with st.form("travel_form"):
            col1, col2 = st.columns(2)
            with col1:
                city_input = st.text_input("城市名", key="city_input")
                province_input = st.text_input("省份", key="province_input")
            with col2:
                status_options = ["", "visited", "planned"]
                status_labels = {"": "请选择状态", "visited": "已去", "planned": "计划中"}
                status_select = st.selectbox(
                    "状态",
                    status_options,
                    format_func=lambda x: status_labels.get(x, x),
                    key="status_select"
                )
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
                    if not province_input and city_input in city_coords and len(city_coords[city_input]) >= 3:
                        province_input = city_coords[city_input][2]
                    if status_select == "visited":
                        visit_date = date_input
                        plan_date = None
                    else:
                        visit_date = None
                        plan_date = date_input
                    conn = get_db_connection()
                    if conn is not None:
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

        if "delete_city" in st.query_params:
            city_to_delete = st.query_params["delete_city"]
            conn = get_db_connection()
            if conn is not None:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM travel_records WHERE city_name = %s", (city_to_delete,))
                conn.commit()
                conn.close()
            st.query_params.clear()
            st.rerun()

        if "toggle_city" in st.query_params:
            city_to_toggle = st.query_params["toggle_city"]
            conn = get_db_connection()
            if conn is not None:
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