import pymysql

conn = pymysql.connect(
    host="localhost",
    user="root",
    password="75757575",  # 改成你设置的密码
    database="menu_db"
)

cursor = conn.cursor()
cursor.execute("SHOW TABLES;")
print(cursor.fetchall())

conn.close()