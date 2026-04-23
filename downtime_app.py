import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
import hashlib

# ============================================================================
# DATABASE SETUP
# ============================================================================

DB_PATH = "downtime_tracker.db"

def init_database():
    """Initialize SQLite database with tables"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT DEFAULT 'maintenance'
        )
    ''')
    
    # Downtime records table
    c.execute('''
        CREATE TABLE IF NOT EXISTS downtime_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipment TEXT NOT NULL,
            main_category TEXT NOT NULL,
            sub_category TEXT,
            description TEXT,
            reported_by TEXT NOT NULL,
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP,
            status TEXT DEFAULT 'ongoing',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    
    # Add default users if they don't exist
    try:
        c.execute("INSERT INTO users (username, password, name, role) VALUES (?, ?, ?, ?)",
                  ('marvin', hashlib.sha256('marvin123'.encode()).hexdigest(), 'Marvin Rosario', 'manager'))
        c.execute("INSERT INTO users (username, password, name, role) VALUES (?, ?, ?, ?)",
                  ('jerone', hashlib.sha256('jerone123'.encode()).hexdigest(), 'Jerone Silvestre', 'maintenance'))
        conn.commit()
    except:
        pass  # Users already exist
    
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_user(username, password):
    """Check if user credentials are valid"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ? AND password = ?",
              (username, hash_password(password)))
    user = c.fetchone()
    conn.close()
    return user

def get_user_name(username):
    """Get user's full name"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else username

# ============================================================================
# DOWNTIME OPERATIONS
# ============================================================================

EQUIPMENT_LIST = [
    "Screw conveyor", "Bucket elevator", "Batch weigher", "Hammermill",
    "Mixer", "Conditioner", "Pelletmill", "Cooler", "Crumbler", "Sifter",
    "Bagging", "Boiler", "Compressor", "Transformer", "Liquid system"
]

CATEGORY_MAPPING = {
    "Equipment Downtime": ["Electrical", "Mechanical", "PLC"],
    "Power Failure": [],
    "Process": [],
    "Warehouse": [],
    "Raw Materials": [],
    "Change Over Downtime": ["Change Over", "Change Die", "Change Screen"]
}

def start_downtime(equipment, main_category, sub_category, description, reported_by):
    """Record a new downtime event"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    start_time = datetime.now()
    
    c.execute('''
        INSERT INTO downtime_records 
        (equipment, main_category, sub_category, description, reported_by, start_time, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (equipment, main_category, sub_category or "", description, reported_by, start_time, 'ongoing'))
    
    conn.commit()
    record_id = c.lastrowid
    conn.close()
    return record_id

def resolve_downtime(record_id):
    """Mark downtime as resolved"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    end_time = datetime.now()
    
    c.execute('''
        UPDATE downtime_records 
        SET status = 'resolved', end_time = ?, updated_at = ?
        WHERE id = ?
    ''', (end_time, datetime.now(), record_id))
    
    conn.commit()
    conn.close()

def get_active_downtimes():
    """Get all ongoing downtimes"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT id, equipment, main_category, sub_category, description, reported_by, start_time, status
        FROM downtime_records
        WHERE status = 'ongoing'
        ORDER BY start_time DESC
    ''')
    results = c.fetchall()
    conn.close()
    
    downtimes = []
    for row in results:
        duration = (datetime.now() - datetime.fromisoformat(row[6])).total_seconds() / 60
        downtimes.append({
            'id': row[0],
            'equipment': row[1],
            'main_category': row[2],
            'sub_category': row[3],
            'description': row[4],
            'reported_by': row[5],
            'start_time': row[6],
            'duration_minutes': round(duration, 1),
            'status': row[7]
        })
    return downtimes

def get_downtime_history(days=1):
    """Get downtime records for the last N days"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    from_date = datetime.now() - timedelta(days=days)
    
    c.execute('''
        SELECT id, equipment, main_category, sub_category, description, reported_by, start_time, end_time, status
        FROM downtime_records
        WHERE start_time >= ? OR (status = 'resolved' AND end_time >= ?)
        ORDER BY start_time DESC
    ''', (from_date, from_date))
    
    results = c.fetchall()
    conn.close()
    
    records = []
    for row in results:
        if row[7]:  # end_time exists
            duration = (datetime.fromisoformat(row[7]) - datetime.fromisoformat(row[6])).total_seconds() / 60
        else:
            duration = (datetime.now() - datetime.fromisoformat(row[6])).total_seconds() / 60
        
        records.append({
            'id': row[0],
            'equipment': row[1],
            'main_category': row[2],
            'sub_category': row[3],
            'description': row[4],
            'reported_by': row[5],
            'start_time': row[6],
            'end_time': row[7] or '-',
            'duration_minutes': round(duration, 1),
            'status': row[8]
        })
    return records

# ============================================================================
# PAGE SETUP
# ============================================================================

st.set_page_config(page_title="AC Plant Downtime Tracker", layout="wide", initial_sidebar_state="expanded")

# Custom CSS
st.markdown("""
    <style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
    .ongoing-alert {
        background-color: #fff3cd;
        padding: 15px;
        border-radius: 5px;
        border-left: 4px solid #ff6b6b;
    }
    .resolved-success {
        background-color: #d4edda;
        padding: 15px;
        border-radius: 5px;
    }
    </style>
""", unsafe_allow_html=True)

# Initialize database
init_database()

# ============================================================================
# AUTHENTICATION
# ============================================================================

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.user_name = None

if not st.session_state.logged_in:
    st.title("🔐 AC Plant Downtime Tracker")
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.subheader("Login")
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")
        
        if st.button("Login", key="login_btn", use_container_width=True):
            user = verify_user(username, password)
            if user:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.user_name = get_user_name(username)
                st.success("✅ Login successful!")
                st.rerun()
            else:
                st.error("❌ Invalid credentials")
        
        st.markdown("---")
        st.info("**Demo Credentials:**\n- Username: `marvin` | Password: `marvin123`\n- Username: `jerone` | Password: `jerone123`")

else:
    # ============================================================================
    # MAIN APP
    # ============================================================================
    
    # Sidebar
    with st.sidebar:
        st.title(f"👤 {st.session_state.user_name}")
        st.markdown("---")
        page = st.radio("Navigation", ["📊 Dashboard", "📝 Log Downtime", "📋 History", "🔄 Active"], label_visibility="collapsed")
        st.markdown("---")
        if st.button("Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.username = None
            st.session_state.user_name = None
            st.rerun()
    
    # ============================================================================
    # PAGE: LOG DOWNTIME
    # ============================================================================
    
    if page == "📝 Log Downtime":
        st.title("📝 Log New Downtime")
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        
        with col1:
            equipment = st.selectbox("Equipment", EQUIPMENT_LIST)
            main_category = st.selectbox("Downtime Category", list(CATEGORY_MAPPING.keys()))
        
        with col2:
            if CATEGORY_MAPPING[main_category]:
                sub_category = st.selectbox("Sub-Category", CATEGORY_MAPPING[main_category])
            else:
                sub_category = None
                st.info("No sub-categories for this type")
        
        description = st.text_area("Description / Notes (optional)", placeholder="e.g., Bearing failure on main shaft", height=80)
        
        st.markdown("---")
        st.info(f"**Reported By:** {st.session_state.user_name}")
        
        if st.button("🚨 START DOWNTIME", use_container_width=True, type="primary"):
            record_id = start_downtime(equipment, main_category, sub_category, description, st.session_state.user_name)
            st.success(f"✅ Downtime logged! (ID: {record_id})")
            st.balloons()
    
    # ============================================================================
    # PAGE: ACTIVE DOWNTIMES
    # ============================================================================
    
    elif page == "🔄 Active":
        st.title("🔄 Active Downtimes")
        st.markdown("---")
        
        active = get_active_downtimes()
        
        if active:
            st.warning(f"⚠️ **{len(active)} ongoing downtime(s)**", icon="⚠️")
            
            for dt in active:
                with st.container(border=True):
                    col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
                    
                    with col1:
                        st.subheading(f"🏭 {dt['equipment']}")
                        st.caption(f"Category: {dt['main_category']}")
                        if dt['sub_category']:
                            st.caption(f"Sub: {dt['sub_category']}")
                    
                    with col2:
                        st.metric("Duration", f"{dt['duration_minutes']} min")
                        st.caption(f"Started: {datetime.fromisoformat(dt['start_time']).strftime('%H:%M:%S')}")
                        st.caption(f"By: {dt['reported_by']}")
                    
                    with col3:
                        if dt['description']:
                            st.caption(f"📝 {dt['description'][:50]}...")
                    
                    with col4:
                        if st.button("✅ Resolve", key=f"resolve_{dt['id']}", use_container_width=True):
                            resolve_downtime(dt['id'])
                            st.success("Downtime resolved!")
                            st.rerun()
        else:
            st.success("✅ No active downtimes! Great job!")
    
    # ============================================================================
    # PAGE: DASHBOARD
    # ============================================================================
    
    elif page == "📊 Dashboard":
        st.title("📊 Downtime Dashboard")
        st.markdown("---")
        
        # Time period selector
        col1, col2, col3 = st.columns(3)
        with col1:
            period = st.radio("Time Period", ["Today (24h)", "This Week (7d)", "This Month (30d)"], label_visibility="collapsed")
        
        days_map = {"Today (24h)": 1, "This Week (7d)": 7, "This Month (30d)": 30}
        days = days_map[period]
        
        # Fetch data
        history = get_downtime_history(days)
        active = get_active_downtimes()
        
        if not history and not active:
            st.info("No downtime data for this period")
        else:
            # KPIs
            st.subheader("Key Metrics")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Events", len(history) + len(active))
            
            with col2:
                st.metric("Active Now", len(active))
            
            with col3:
                if history:
                    total_minutes = sum([h['duration_minutes'] for h in history if h['status'] == 'resolved'])
                    st.metric("Total Downtime", f"{round(total_minutes/60, 1)}h")
                else:
                    st.metric("Total Downtime", "0h")
            
            with col4:
                resolved_count = len([h for h in history if h['status'] == 'resolved'])
                st.metric("Resolved", resolved_count)
            
            st.markdown("---")
            
            # Charts
            if history:
                df = pd.DataFrame(history)
                df['start_time'] = pd.to_datetime(df['start_time'])
                
                # Chart 1: Downtime by Category
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("Downtime by Category (%)")
                    category_counts = df['main_category'].value_counts()
                    if not category_counts.empty:
                        fig = px.pie(values=category_counts.values, names=category_counts.index, 
                                    color_discrete_sequence=px.colors.qualitative.Set3)
                        st.plotly_chart(fig, use_container_width=True)
                
                # Chart 2: Downtime by Equipment
                with col2:
                    st.subheader("Downtime by Equipment (Count)")
                    equip_counts = df['equipment'].value_counts().head(10)
                    if not equip_counts.empty:
                        fig = px.bar(x=equip_counts.values, y=equip_counts.index, orientation='h',
                                    labels={'x': 'Count', 'y': 'Equipment'})
                        st.plotly_chart(fig, use_container_width=True)
                
                st.markdown("---")
                
                # Category breakdown
                st.subheader("Breakdown by Category")
                for category in df['main_category'].unique():
                    cat_data = df[df['main_category'] == category]
                    count = len(cat_data)
                    resolved = len(cat_data[cat_data['status'] == 'resolved'])
                    percentage = (count / len(df)) * 100 if len(df) > 0 else 0
                    st.write(f"**{category}**: {count} events ({percentage:.1f}%) | Resolved: {resolved}")
            else:
                st.info("No historical data available")
    
    # ============================================================================
    # PAGE: HISTORY
    # ============================================================================
    
    elif page == "📋 History":
        st.title("📋 Downtime History")
        st.markdown("---")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            period = st.radio("Period", ["Last 24h", "Last 7 days", "Last 30 days"], label_visibility="collapsed")
        
        days_map = {"Last 24h": 1, "Last 7 days": 7, "Last 30 days": 30}
        days = days_map[period]
        
        history = get_downtime_history(days)
        
        if history:
            df = pd.DataFrame(history)
            
            # Export to Excel
            col2.write("")
            col2.write("")
            if col2.button("📥 Export to Excel", use_container_width=True):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, sheet_name='Downtime Records', index=False)
                output.seek(0)
                st.download_button(
                    label="Download Excel",
                    data=output,
                    file_name=f"AC_Downtime_Report_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No records found for this period")

