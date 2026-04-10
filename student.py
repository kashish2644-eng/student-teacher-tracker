import streamlit as st
import sqlite3
import pandas as pd
import hashlib
import plotly.express as px
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

# ------------------ CONFIG ------------------
st.set_page_config(page_title="EduTrack Pro", layout="wide")

# ------------------ UI ------------------
st.markdown("""
<style>
[data-testid="stSidebar"] {display:none;}
[data-testid="collapsedControl"] {display:none;}

body {
    background: linear-gradient(135deg, #eef2ff, #f8fafc);
}

.stButton>button {
    border-radius: 12px;
    background: linear-gradient(90deg, #6366f1, #4f46e5);
    color: white;
}

.card {
    padding: 20px;
    border-radius: 16px;
    background: white;
    box-shadow: 0px 6px 20px rgba(0,0,0,0.08);
    text-align: center;
}
</style>
""", unsafe_allow_html=True)

# ------------------ DB ------------------
conn = sqlite3.connect("tracker_v2.db", check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users (
id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, password TEXT, role TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS students (
id INTEGER PRIMARY KEY,
name TEXT,
grade TEXT,
stream TEXT,
language TEXT,
optional_subject TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS attendance (
id INTEGER PRIMARY KEY, student_id INTEGER, subject TEXT, date TEXT, status TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS engagement (
id INTEGER PRIMARY KEY, student_id INTEGER, subject TEXT, date TEXT, tag TEXT)''')

conn.commit()

# ------------------ HELPERS ------------------
def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def get_students():
    return pd.read_sql("SELECT * FROM students", conn)

def tag_score(tag):
    return {"Excellent":4,"Active":3,"Late":2,"Needs Improvement":1}.get(tag,0)

def get_subjects(grade, stream, language, optional):
    if grade in [str(i) for i in range(5,11)]:
        base = ["Maths","Science","English","Hindi","Social Science","Computer"]
        return base + ([language] if language else [])
    if grade in ["11","12"]:
        if stream=="Commerce":
            base=["Accounts","English","Micro-Economics","Macro-Economics","Business Studies"]
        elif stream=="Science":
            base=["Physics","Chemistry","English","Mathematics","Biology"]
        else:
            base=["History","Geography","Political Science","Sociology","English"]
        return base + ([optional] if optional else [])
    return []

# ------------------ PDF ------------------
def generate_low_attendance_pdf(df):
    file = "low_attendance_report.pdf"
    doc = SimpleDocTemplate(file)

    data = [["Name", "Grade", "Attendance %"]]

    for _, row in df.iterrows():
        data.append([row["name"], row["grade"], f"{row['attendance']:.2f}"])

    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.grey),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('GRID',(0,0),(-1,-1),1,colors.black)
    ]))

    doc.build([table])
    return open(file,"rb").read()

def generate_student_pdf(name, att, eng, final):
    doc = SimpleDocTemplate("report.pdf")
    styles = getSampleStyleSheet()
    content = [
        Paragraph(f"{name} Report", styles['Title']),
        Spacer(1,10),
        Paragraph(f"Attendance: {att:.2f}%", styles['Normal']),
        Paragraph(f"Engagement: {eng:.2f}", styles['Normal']),
        Paragraph(f"Final Score: {final:.2f}", styles['Normal'])
    ]
    doc.build(content)
    return open("report.pdf","rb").read()

# ------------------ SESSION ------------------
if "login" not in st.session_state:
    st.session_state.login=False
if "user" not in st.session_state:
    st.session_state.user=None
if "page" not in st.session_state:
    st.session_state.page="login"

# ------------------ AUTH ------------------
def auth():
    st.title("🎓 EduTrack Pro")

    c1, c2 = st.columns(2)
    if c1.button("Login", key="login_tab"):
        st.session_state.page = "login"
    if c2.button("Signup", key="signup_tab"):
        st.session_state.page = "signup"

    if st.session_state.page == "login":
        email = st.text_input("Email")
        pwd = st.text_input("Password", type="password")

        if st.button("Login", key="login_button"):
            user = c.execute(
                "SELECT * FROM users WHERE email=? AND password=?",
                (email, hash_password(pwd))
            ).fetchone()

            if user:
                st.session_state.login = True
                st.session_state.user = user

                # ✅ store user_id
                st.session_state.user_id = user[0]

                st.rerun()
            else:
                st.error("Invalid credentials")

    else:
        name = st.text_input("Name")
        email = st.text_input("Email")
        pwd = st.text_input("Password", type="password")
        role = st.selectbox("Role", ["student", "faculty"])

        grade = stream = language = optional = None

        if role == "student":
            grade = st.selectbox("Grade", [str(i) for i in range(5,13)])

            if grade in [str(i) for i in range(5,11)]:
                language = st.selectbox("Language", ["Gujarati","French","Sanskrit"])

            if grade in ["11","12"]:
                stream = st.selectbox("Stream", ["Commerce","Science","Arts"])
                optional = st.selectbox(
                    "Optional",
                    ["Computer Science","Psychology","Physical Education","Entrepreneurship"]
                )

        if st.button("Create Account", key="signup_button"):
            try:
                # ✅ Insert into users
                c.execute(
                    "INSERT INTO users VALUES(NULL,?,?,?,?)",
                    (name, email, hash_password(pwd), role)
                )

                # ✅ Get generated user_id
                user_id = c.lastrowid

                # ✅ Insert into students (linked via SAME ID)
                if role == "student":

                    # 🔥 FIX: removed unnecessary existing check (was breaking ID sync)
                    c.execute(
                        "INSERT INTO students VALUES(?,?,?,?,?,?)",
                        (
                            user_id,   # SAME ID as users table
                            name,
                            grade,
                            stream or "",
                            language or "",
                            optional or ""
                        )
                    )

                conn.commit()
                st.success("✅ Account Created Successfully")

            except Exception as e:
                st.error(f"❌ {e}")

# ------------------ STUDENT DASHBOARD ------------------
def student_dashboard():
    user_id = st.session_state.user[0]
    name = st.session_state.user[1]   # ✅ added (for proper display)

    col1, col2 = st.columns([8,1])
    col1.title(f"🎓 Welcome {name}")   # ✅ FIXED (was showing ID)

    if col2.button("Logout", key="student_logout"):
        st.session_state.login = False
        st.session_state.user = None
        st.rerun()

    df = pd.read_sql(
        "SELECT * FROM attendance WHERE student_id=?",
        conn,
        params=(user_id,)
    )

    # ✅ HANDLE EMPTY DATA (IMPORTANT FIX)
    if df.empty:
        total = 0
        present = 0
        percent = 0

        st.info("📊 No attendance data yet")

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Classes", total)
        c2.metric("Present", present)
        c3.metric("Attendance %", f"{percent:.2f}")

        # Empty chart
        empty_df = pd.DataFrame({"subject": [], "status": []})
        fig = px.bar(empty_df, x="subject", y="status")
        st.plotly_chart(fig, use_container_width=True)

        return

    # ---------------- NORMAL FLOW ----------------
    df["date"] = pd.to_datetime(df["date"])

    total = len(df)
    present = len(df[df["status"] == "present"])
    percent = present / total * 100

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Classes", total)
    c2.metric("Present", present)
    c3.metric("Attendance %", f"{percent:.2f}")

    # 🚨 ALERT
    if percent < 75:
        st.error(f"🚨 Attendance below 75% ({percent:.2f}%)")
    else:
        st.success("✅ Attendance Safe")

    # 📊 Subject-wise
    st.subheader("📊 Subject-wise Attendance")
    fig1 = px.histogram(df, x="subject", color="status", barmode="group")
    st.plotly_chart(fig1, use_container_width=True)

    # 📈 Monthly trend
    st.subheader("📈 Monthly Trend")
    monthly = df.groupby(df["date"].dt.to_period("M"))["status"].apply(
        lambda x: (x == "present").mean() * 100
    )
    monthly.index = monthly.index.astype(str)

    fig2 = px.line(x=monthly.index, y=monthly.values, markers=True)
    st.plotly_chart(fig2, use_container_width=True)



# ------------------ FACULTY DASHBOARD ------------------
def faculty_dashboard():

    col1, col2 = st.columns([8,1])
    col1.title("👨‍🏫 Faculty Panel")

    if col2.button("Logout", key="faculty_logout"):
        st.session_state.login = False
        st.session_state.user = None
        st.rerun()

    menu = st.radio(
        "Menu",
        ["Students", "Attendance", "Engagement", "Dashboard"],
        horizontal=True,
        key="faculty_menu"
    )

    students = get_students()

    # ------------------ STUDENTS ------------------
    if menu == "Students":

        st.subheader("➕ Add Student")

        name = st.text_input("Student Name", key="student_name_input")
        grade = st.selectbox("Grade", [str(i) for i in range(5,13)], key="student_grade")

        stream = language = optional = None

        # Grade 5–10
        if grade in [str(i) for i in range(5,11)]:
            language = st.selectbox(
                "Language",
                ["Gujarati","French","Sanskrit"],
                key="student_language"
            )

        # Grade 11–12
        if grade in ["11","12"]:
            stream = st.selectbox(
                "Stream",
                ["Commerce","Science","Arts"],
                key="student_stream"
            )

            optional = st.selectbox(
                "Optional Subject",
                ["Computer Science","Psychology","Physical Education","Entrepreneurship"],
                key="student_optional"
            )

        st.info("Students can only be added via signup")

        st.divider()

        st.subheader("📋 All Students")
        st.dataframe(students[["name","grade","stream","language","optional_subject"]])

    # ------------------ ATTENDANCE ------------------
    elif menu == "Attendance":

        s = st.selectbox("Student", students["name"], key="attendance_student")
        sd = students[students["name"] == s].iloc[0]

        subjects = get_subjects(sd["grade"], sd["stream"], sd["language"], sd["optional_subject"])
        sub = st.selectbox("Subject", subjects, key="attendance_subject")

        date = st.date_input("Date", key="attendance_date")
        status = st.selectbox("Status", ["present","absent"], key="attendance_status")

        if st.button("Save Attendance", key="save_attendance_btn"):
            c.execute(
                "INSERT INTO attendance VALUES(NULL,?,?,?,?)",
                (sd["id"], sub, str(date), status)
            )
            conn.commit()
            st.success("✅ Attendance Saved")

    # ------------------ ENGAGEMENT ------------------
    elif menu == "Engagement":

        s = st.selectbox("Student", students["name"], key="engagement_student")
        sd = students[students["name"] == s].iloc[0]

        subjects = get_subjects(sd["grade"], sd["stream"], sd["language"], sd["optional_subject"])
        sub = st.selectbox("Subject", subjects, key="engagement_subject")

        date = st.date_input("Date", key="engagement_date")
        tag = st.selectbox(
            "Tag",
            ["Excellent","Active","Late","Needs Improvement"],
            key="engagement_tag"
        )

        if st.button("Save Engagement", key="save_engagement_btn"):
            c.execute(
                "INSERT INTO engagement VALUES(NULL,?,?,?,?)",
                (sd["id"], sub, str(date), tag)
            )
            conn.commit()
            st.success("✅ Engagement Saved")

    # ------------------ DASHBOARD ------------------
    elif menu == "Dashboard":

        att = pd.read_sql("SELECT student_id,status FROM attendance", conn)
        eng = pd.read_sql("SELECT student_id,tag FROM engagement", conn)

        if att.empty:
            st.info("No data")
            return

        att_sum = att.groupby("student_id")["status"].apply(
            lambda x:(x=="present").mean()*100
        )

        eng["score"] = eng["tag"].apply(tag_score)
        eng_sum = eng.groupby("student_id")["score"].mean()

        final = (att_sum*0.6) + (eng_sum*10*0.4)

        # 🏆 Leaderboard
        st.subheader("🏆 Leaderboard")
        leaderboard = final.sort_values(ascending=False)
        st.bar_chart(leaderboard)

        # ⚠️ Low Attendance
        st.subheader("⚠️ Students Below 75%")
        low = att_sum[att_sum < 75]

        if not low.empty:
            low_df = low.reset_index()
            low_df.columns = ["student_id","attendance"]
            low_df = low_df.merge(students, left_on="student_id", right_on="id")

            st.error(f"{len(low_df)} students below 75%")
            st.dataframe(low_df[["name","grade","attendance"]])

            pdf = generate_low_attendance_pdf(low_df)

            st.download_button(
                "📄 Download Report",
                pdf,
                "low_attendance.pdf",
                key="download_low_pdf"
            )

        else:
            st.success("All students safe 🎉")

        # 📊 Distribution
        st.subheader("📊 Attendance Distribution")
        fig = px.histogram(att_sum, nbins=10)
        st.plotly_chart(fig, use_container_width=True)

# ------------------ MAIN ------------------
if not st.session_state.login:
    auth()
else:
    if st.session_state.user[4]=="student":
        student_dashboard()
    else:
        faculty_dashboard()
