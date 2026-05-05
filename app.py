import streamlit as st
import sqlite3
import hashlib
from datetime import datetime, date, timedelta
import os
import base64

st.set_page_config(page_title="CampusShare", layout="wide")

DB = "campusshare.db"
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────

def db():
    con = sqlite3.connect(DB, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def hash_pw(password):
    return hashlib.sha256(password.encode()).hexdigest()


def init_db():
    con = db()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        roll TEXT UNIQUE,
        email TEXT UNIQUE,
        password TEXT,
        hostel TEXT,
        role TEXT DEFAULT 'student',
        karma INTEGER DEFAULT 0,
        avg_rating REAL DEFAULT 0.0,
        rating_count INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER,
        name TEXT,
        category TEXT,
        description TEXT,
        item_value REAL,
        value_level TEXT,
        deposit REAL,
        condition TEXT,
        image_path TEXT,
        status TEXT DEFAULT 'Available',
        hostel TEXT,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER,
        borrower_id INTEGER,
        owner_id INTEGER,
        verifier_id INTEGER,
        duration_days INTEGER,
        return_date TEXT,
        message TEXT,
        status TEXT DEFAULT 'Pending',
        extension_count INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS condition_checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER,
        stage TEXT,
        working TEXT,
        no_damage TEXT,
        accessories TEXT,
        clean TEXT,
        photo_path TEXT,
        notes TEXT,
        checked_by INTEGER,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS extension_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER,
        extra_days INTEGER,
        reason TEXT,
        status TEXT DEFAULT 'Pending',
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS disputes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER,
        raised_by INTEGER,
        reason TEXT,
        status TEXT DEFAULT 'Open',
        admin_decision TEXT,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS ratings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER,
        rater_id INTEGER,
        rated_user_id INTEGER,
        score INTEGER,
        remarks TEXT,
        role TEXT,
        created_at TEXT
    )
    """)

    con.commit()
    con.close()


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def classify_value(value):
    if value <= 1000:
        return "Low Value", 0
    elif value <= 5000:
        return "Medium Value", round(value * 0.30, 2)
    else:
        return "High Value", round(value * 0.50, 2)


def save_image(uploaded_file, prefix="img"):
    """Save uploaded image to disk and return the path."""
    if uploaded_file is None:
        return None
    ext = uploaded_file.name.split(".")[-1]
    filename = f"{prefix}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}.{ext}"
    path = os.path.join(UPLOAD_DIR, filename)
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return path


def show_image(path, caption="", width=300):
    """Display a saved image."""
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            data = f.read()
        b64 = base64.b64encode(data).decode()
        ext = path.split(".")[-1].lower()
        mime = "image/jpeg" if ext in ["jpg","jpeg"] else "image/png"
        st.markdown(
            f'<img src="data:{mime};base64,{b64}" width="{width}" style="border-radius:8px;margin:6px 0"/>',
            unsafe_allow_html=True
        )
        if caption:
            st.caption(caption)


def update_user_rating(user_id):
    """Recalculate and update a user's average rating."""
    con = db()
    cur = con.cursor()
    cur.execute(
        "SELECT AVG(score), COUNT(*) FROM ratings WHERE rated_user_id=?",
        (user_id,)
    )
    row = cur.fetchone()
    avg = round(row[0] or 0.0, 2)
    count = row[1] or 0
    cur.execute(
        "UPDATE users SET avg_rating=?, rating_count=? WHERE id=?",
        (avg, count, user_id)
    )
    con.commit()
    con.close()


def add_karma(user_id, points, con_ext=None):
    """Add or deduct karma from a user."""
    close_after = False
    if con_ext is None:
        con_ext = db()
        close_after = True
    con_ext.execute(
        "UPDATE users SET karma = karma + ? WHERE id=?",
        (points, user_id)
    )
    if close_after:
        con_ext.commit()
        con_ext.close()


def assign_verifier(item_id, borrower_id, owner_id):
    """
    FIX 1 — System-assigned verifier.
    Picks a student who is NOT the borrower or owner,
    preferring users with verifier_status='Yes' if that column exists,
    otherwise any eligible student. Falls back to any student.
    """
    con = db()
    cur = con.cursor()

    # Check if verifier_status column exists (backward compat)
    cur.execute("PRAGMA table_info(users)")
    cols = [row[1] for row in cur.fetchall()]

    if "verifier_status" in cols:
        cur.execute("""
            SELECT id FROM users
            WHERE id != ? AND id != ?
            AND role = 'student'
            AND verifier_status = 'Yes'
            ORDER BY karma DESC
            LIMIT 1
        """, (borrower_id, owner_id))
        row = cur.fetchone()
        if row:
            con.close()
            return row[0]

    # Fallback — highest karma student who isn't borrower or owner
    cur.execute("""
        SELECT id FROM users
        WHERE id != ? AND id != ?
        AND role = 'student'
        ORDER BY karma DESC
        LIMIT 1
    """, (borrower_id, owner_id))
    row = cur.fetchone()
    con.close()
    return row[0] if row else None


# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────

def signup():
    st.title("🔗 CampusShare — Create Account")

    col1, col2 = st.columns(2)
    with col1:
        name     = st.text_input("Full Name")
        roll     = st.text_input("Roll Number")
        email    = st.text_input("Institute Email")
    with col2:
        password = st.text_input("Password", type="password")
        hostel   = st.selectbox("Hostel", ["Hostel A","Hostel B","Hostel C","Hostel D","Other"])
        volunteer = st.checkbox("Volunteer as Peer Verifier")

    if st.button("Create Account", type="primary"):
        if not name or not roll or not email or not password:
            st.error("Please fill all required fields.")
            return
        role = "admin" if email == "admin@iiitm.ac.in" else "student"
        try:
            con = db()
            cur = con.cursor()
            # Add verifier_status column if not present
            try:
                cur.execute("ALTER TABLE users ADD COLUMN verifier_status TEXT DEFAULT 'No'")
                con.commit()
            except Exception:
                pass
            cur.execute("""
                INSERT INTO users (name, roll, email, password, hostel, role, verifier_status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (name, roll, email, hash_pw(password), hostel, role, "Yes" if volunteer else "No"))
            con.commit()
            con.close()
            st.success("Account created! Please login.")
        except sqlite3.IntegrityError:
            st.error("Email or roll number already exists.")


def login():
    st.title("🔗 CampusShare — Login")

    email    = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login", type="primary"):
        con = db()
        cur = con.cursor()
        cur.execute("""
            SELECT id, name, role, hostel, karma, avg_rating
            FROM users WHERE email=? AND password=?
        """, (email, hash_pw(password)))
        user = cur.fetchone()
        con.close()

        if user:
            st.session_state.user_id   = user[0]
            st.session_state.name      = user[1]
            st.session_state.role      = user[2]
            st.session_state.hostel    = user[3]
            st.session_state.karma     = user[4]
            st.session_state.rating    = user[5]
            st.rerun()
        else:
            st.error("Invalid email or password.")


# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────

def dashboard():
    st.title("📊 Dashboard")
    st.write(f"Welcome back, **{st.session_state.name}** 👋")

    con = db()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM items WHERE status='Available'")
    available = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM items WHERE owner_id=?", (st.session_state.user_id,))
    my_items = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM requests WHERE borrower_id=? AND status='Accepted'",
                (st.session_state.user_id,))
    active_borrows = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM requests WHERE owner_id=? AND status='Pending'",
                (st.session_state.user_id,))
    pending_recv = cur.fetchone()[0]

    cur.execute("SELECT karma, avg_rating, rating_count FROM users WHERE id=?",
                (st.session_state.user_id,))
    urow = cur.fetchone()
    karma = urow[0]; avg_r = urow[1]; r_count = urow[2]

    con.close()

    # ── Stats row 1
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Available Items", available)
    c2.metric("My Listings",     my_items)
    c3.metric("Active Borrows",  active_borrows)
    c4.metric("Pending Requests", pending_recv,
              delta="needs action" if pending_recv else None,
              delta_color="inverse")
    c5.metric("My Karma ★",      karma)

    st.divider()

    # ── My profile summary
    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("My Profile")
        st.write(f"**Name:** {st.session_state.name}")
        st.write(f"**Hostel:** {st.session_state.hostel}")
        st.write(f"**Karma:** ★ {karma}")
        stars = "⭐" * round(avg_r) if avg_r else "—"
        st.write(f"**Rating:** {stars} ({avg_r:.1f} from {r_count} ratings)")

    with col2:
        st.subheader("Karma Guide")
        karma_table = {
            "List an item": "+2",
            "Item returned on time": "+5",
            "Give item away free": "+8",
            "Receive 5★ rating": "+3",
            "Late return (>24h)": "−5",
            "Damage reported": "−10",
            "No-show for pickup": "−3",
        }
        for k, v in karma_table.items():
            color = "green" if v.startswith("+") else "red"
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;padding:4px 0;'
                f'border-bottom:1px solid #eee"><span>{k}</span>'
                f'<span style="color:{color};font-weight:600">{v}</span></div>',
                unsafe_allow_html=True
            )


# ─────────────────────────────────────────────
# ADD ITEM
# ─────────────────────────────────────────────

def add_item():
    st.title("➕ Add Item")

    col1, col2 = st.columns(2)
    with col1:
        name      = st.text_input("Item Name")
        category  = st.selectbox("Category",
            ["Books","Cycles","Electronics","Appliances","Formals","Sports","Tools","Other"])
        condition = st.selectbox("Condition", ["New","Good","Usable"])
        hostel    = st.selectbox("Pickup Hostel",
            ["Hostel A","Hostel B","Hostel C","Hostel D","Other"],
            index=["Hostel A","Hostel B","Hostel C","Hostel D","Other"].index(
                st.session_state.get("hostel","Hostel A")) if st.session_state.get("hostel") else 0)

    with col2:
        value = st.number_input("Approximate Value ₹", min_value=0.0)
        value_level, deposit = classify_value(value)
        st.info(f"**Value Level:** {value_level}")
        st.info(f"**Security Deposit Required:** ₹{deposit}")
        description = st.text_area("Description", height=100)

    # FIX 2 — Real image upload
    st.subheader("📸 Item Photo")
    image = st.file_uploader("Upload item photo", type=["jpg","jpeg","png"])
    if image:
        st.image(image, caption="Preview", width=300)

    if st.button("List Item", type="primary"):
        if not name:
            st.error("Item name is required.")
            return

        image_path = save_image(image, prefix="item") if image else None

        con = db()
        cur = con.cursor()
        cur.execute("""
            INSERT INTO items
            (owner_id, name, category, description, item_value, value_level,
             deposit, condition, image_path, hostel, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            st.session_state.user_id, name, category, description,
            value, value_level, deposit, condition, image_path,
            hostel, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        # Karma +2 for listing
        add_karma(st.session_state.user_id, 2, con)
        con.commit()
        con.close()
        st.success("✅ Item listed! +2 karma earned.")


# ─────────────────────────────────────────────
# BROWSE ITEMS  — FIX 6: hostel filter
# ─────────────────────────────────────────────

def browse_items():
    st.title("🔍 Browse Items")

    col1, col2, col3 = st.columns(3)
    with col1:
        search = st.text_input("Search", placeholder="Item name...")
    with col2:
        category_filter = st.selectbox("Category",
            ["All","Books","Cycles","Electronics","Appliances","Formals","Sports","Tools","Other"])
    with col3:
        # FIX 6 — hostel filter
        hostel_filter = st.selectbox("Hostel",
            ["All","Hostel A","Hostel B","Hostel C","Hostel D","Other"])

    con = db()
    cur = con.cursor()

    query = """
        SELECT i.id, i.name, i.category, i.description, i.item_value,
               i.value_level, i.deposit, i.condition, i.image_path,
               i.status, u.name, u.hostel, i.owner_id, i.hostel as item_hostel,
               u.karma, u.avg_rating
        FROM items i
        JOIN users u ON i.owner_id = u.id
        WHERE i.owner_id != ? AND i.status = 'Available'
    """
    params = [st.session_state.user_id]

    if search:
        query += " AND i.name LIKE ?"
        params.append(f"%{search}%")
    if category_filter != "All":
        query += " AND i.category = ?"
        params.append(category_filter)
    if hostel_filter != "All":
        query += " AND i.hostel = ?"
        params.append(hostel_filter)

    query += " ORDER BY i.created_at DESC"
    cur.execute(query, params)
    items = cur.fetchall()

    if not items:
        st.info("No items found matching your filters.")
        con.close()
        return

    st.write(f"**{len(items)} item(s) found**")

    for item in items:
        with st.container(border=True):
            c1, c2 = st.columns([1, 2])

            with c1:
                # FIX 2 — show actual item photo
                if item[8] and os.path.exists(item[8]):
                    show_image(item[8], width=220)
                else:
                    st.markdown(
                        '<div style="width:220px;height:150px;background:#f0f0f0;'
                        'border-radius:8px;display:flex;align-items:center;'
                        'justify-content:center;color:#999">No photo</div>',
                        unsafe_allow_html=True
                    )

            with c2:
                st.subheader(item[1])
                col_a, col_b, col_c = st.columns(3)
                col_a.write(f"**Category:** {item[2]}")
                col_b.write(f"**Condition:** {item[7]}")
                col_c.write(f"**Hostel:** {item[13]}")

                col_d, col_e, col_f = st.columns(3)
                col_d.write(f"**Value:** ₹{item[4]}")
                col_e.write(f"**Level:** {item[5]}")
                col_f.write(f"**Deposit:** ₹{item[6]}")

                owner_stars = "⭐" * round(item[15]) if item[15] else "—"
                st.write(f"**Owner:** {item[10]} · {item[11]} · Karma ★{item[14]} · {owner_stars}")
                st.write(f"**Description:** {item[3]}")

                with st.expander("📨 Send Borrow Request"):
                    days    = st.number_input("Duration (days)", min_value=1, max_value=30,
                                               key=f"days_{item[0]}")
                    message = st.text_area("Message to owner", key=f"msg_{item[0]}")

                    if st.button("Send Request", key=f"req_{item[0]}", type="primary"):
                        # FIX 1 — system assigns verifier, no manual selection
                        verifier_id = assign_verifier(item[0], st.session_state.user_id, item[12])

                        if verifier_id is None:
                            st.error("No eligible verifier found. Please contact admin.")
                        else:
                            return_date = date.today() + timedelta(days=int(days))
                            cur.execute("""
                                INSERT INTO requests
                                (item_id, borrower_id, owner_id, verifier_id,
                                 duration_days, return_date, message, created_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                item[0], st.session_state.user_id, item[12],
                                verifier_id, int(days),
                                return_date.isoformat(), message,
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            ))
                            con.commit()
                            cur2 = con.cursor()
                            cur2.execute("SELECT name FROM users WHERE id=?", (verifier_id,))
                            vrow = cur2.fetchone()
                            st.success(
                                f"✅ Request sent! System assigned **{vrow[0]}** as your verifier."
                            )
    con.close()


# ─────────────────────────────────────────────
# MY REQUESTS
# ─────────────────────────────────────────────

def my_requests():
    st.title("📋 My Requests")

    con = db()
    cur = con.cursor()

    # ── Sent by me
    st.subheader("Requests I Sent")
    cur.execute("""
        SELECT r.id, i.name, u_v.name, u_o.name, r.return_date,
               r.status, i.deposit, r.extension_count
        FROM requests r
        JOIN items i ON r.item_id = i.id
        JOIN users u_v ON r.verifier_id = u_v.id
        JOIN users u_o ON r.owner_id = u_o.id
        WHERE r.borrower_id = ?
        ORDER BY r.created_at DESC
    """, (st.session_state.user_id,))
    sent = cur.fetchall()

    if not sent:
        st.info("You haven't sent any requests yet.")
    for r in sent:
        status_color = {"Pending":"🟡","Accepted":"🟢","Rejected":"🔴","Returned":"🔵"}.get(r[4],"⚪")
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns(4)
            c1.write(f"**Item:** {r[1]}")
            c2.write(f"**Owner:** {r[3]}")
            c3.write(f"**Verifier:** {r[2]}")
            c4.write(f"**Return:** {r[4]}")
            st.write(f"**Status:** {status_color} {r[4]}  |  **Deposit:** ₹{r[6]}")

            if r[4] == "Accepted" and r[7] < 2:
                with st.expander("⏰ Request Extension"):
                    extra = st.number_input("Extra days", 1, 7, key=f"extra_{r[0]}")
                    reason = st.text_area("Reason", key=f"reason_{r[0]}")
                    if st.button("Submit Extension Request", key=f"ext_{r[0]}"):
                        cur.execute("""
                            INSERT INTO extension_requests
                            (request_id, extra_days, reason, created_at)
                            VALUES (?, ?, ?, ?)
                        """, (r[0], extra, reason, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                        con.commit()
                        st.success("Extension request submitted.")

    st.divider()

    # ── Received by me (as owner)
    st.subheader("Requests Received")
    cur.execute("""
        SELECT r.id, i.name, u_b.name, u_v.name, r.return_date,
               r.status, r.item_id, r.borrower_id, r.message
        FROM requests r
        JOIN items i ON r.item_id = i.id
        JOIN users u_b ON r.borrower_id = u_b.id
        JOIN users u_v ON r.verifier_id = u_v.id
        WHERE r.owner_id = ?
        ORDER BY r.created_at DESC
    """, (st.session_state.user_id,))
    received = cur.fetchall()

    if not received:
        st.info("No requests received yet.")
    for r in received:
        status_color = {"Pending":"🟡","Accepted":"🟢","Rejected":"🔴","Returned":"🔵"}.get(r[4],"⚪")
        with st.container(border=True):
            c1, c2, c3 = st.columns(3)
            c1.write(f"**Item:** {r[1]}")
            c2.write(f"**Borrower:** {r[2]}")
            c3.write(f"**Verifier (auto-assigned):** {r[3]}")
            st.write(f"**Return Date:** {r[4]}  |  **Status:** {status_color} {r[4]}")
            if r[8]:
                st.write(f"**Message:** {r[8]}")

            if r[4] == "Pending":
                col_a, col_b = st.columns(2)
                if col_a.button("✅ Accept", key=f"accept_{r[0]}"):
                    cur.execute("UPDATE requests SET status='Accepted' WHERE id=?", (r[0],))
                    cur.execute("UPDATE items SET status='Unavailable' WHERE id=?", (r[6],))
                    con.commit()
                    st.rerun()
                if col_b.button("❌ Reject", key=f"reject_{r[0]}"):
                    cur.execute("UPDATE requests SET status='Rejected' WHERE id=?", (r[0],))
                    con.commit()
                    st.rerun()

            if r[4] == "Accepted":
                if st.button("📦 Mark as Returned", key=f"return_{r[0]}"):
                    cur.execute("UPDATE requests SET status='Returned' WHERE id=?", (r[0],))
                    cur.execute("UPDATE items SET status='Available' WHERE id=?", (r[6],))
                    # Karma +5 for on-time return
                    add_karma(r[7], 5, con)
                    con.commit()
                    st.rerun()

    con.close()


# ─────────────────────────────────────────────
# CONDITION CHECK  — FIX 2: real photo upload
# ─────────────────────────────────────────────

def condition_check():
    st.title("📷 Condition Verification")
    st.write("Upload photos at pickup and return to create an evidence trail.")

    con = db()
    cur = con.cursor()

    cur.execute("""
        SELECT r.id, i.name, r.status, u_b.name, u_o.name
        FROM requests r
        JOIN items i ON r.item_id = i.id
        JOIN users u_b ON r.borrower_id = u_b.id
        JOIN users u_o ON r.owner_id = u_o.id
        WHERE (r.verifier_id = ? OR r.borrower_id = ? OR r.owner_id = ?)
        AND r.status IN ('Accepted','Returned')
    """, (st.session_state.user_id,) * 3)
    rows = cur.fetchall()

    if not rows:
        st.info("No active requests requiring condition verification.")
        con.close()
        return

    for r in rows:
        with st.container(border=True):
            st.subheader(f"Request #{r[0]} — {r[1]}")
            st.write(f"**Borrower:** {r[3]}  |  **Owner:** {r[4]}  |  **Status:** {r[2]}")

            # Show existing checks for this request
            cur.execute("""
                SELECT stage, working, no_damage, accessories, clean, photo_path, notes,
                       checked_by, created_at
                FROM condition_checks WHERE request_id = ?
                ORDER BY created_at ASC
            """, (r[0],))
            existing = cur.fetchall()

            if existing:
                st.write("**Previous checks:**")
                for ex in existing:
                    with st.expander(f"Check — {ex[0]} ({ex[8][:10]})"):
                        col1, col2 = st.columns([1, 2])
                        with col1:
                            if ex[5] and os.path.exists(ex[5]):
                                show_image(ex[5], caption=ex[0], width=200)
                            else:
                                st.write("No photo uploaded")
                        with col2:
                            st.write(f"✅ Working: {ex[0]}")
                            st.write(f"✅ No Damage: {ex[1]}")
                            st.write(f"✅ Accessories: {ex[2]}")
                            st.write(f"✅ Clean: {ex[3]}")
                            st.write(f"📝 Notes: {ex[6] or '—'}")

            st.divider()
            st.write("**Submit New Check:**")

            stage    = st.selectbox("Stage", ["Before Handover","After Return"],
                                     key=f"stage_{r[0]}")
            working  = st.checkbox("Item working properly",  key=f"w_{r[0]}")
            no_dmg   = st.checkbox("No visible damage",      key=f"d_{r[0]}")
            acc      = st.checkbox("All accessories present",key=f"a_{r[0]}")
            clean    = st.checkbox("Item is clean",          key=f"c_{r[0]}")
            notes    = st.text_area("Additional notes",      key=f"n_{r[0]}")

            # FIX 2 — actual photo upload
            photo = st.file_uploader(
                "📸 Upload condition photo (required)",
                type=["jpg","jpeg","png"],
                key=f"photo_{r[0]}"
            )
            if photo:
                st.image(photo, caption="Photo preview", width=250)

            if st.button("Submit Condition Check", key=f"submit_check_{r[0]}", type="primary"):
                if photo is None:
                    st.error("Please upload a condition photo before submitting.")
                else:
                    photo_path = save_image(photo, prefix=f"cond_{r[0]}_{stage.replace(' ','_')}")
                    cur.execute("""
                        INSERT INTO condition_checks
                        (request_id, stage, working, no_damage, accessories, clean,
                         photo_path, notes, checked_by, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        r[0], stage, str(working), str(no_dmg), str(acc), str(clean),
                        photo_path, notes, st.session_state.user_id,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ))
                    con.commit()
                    st.success("✅ Condition check submitted with photo.")
                    st.rerun()

    con.close()


# ─────────────────────────────────────────────
# SPECIAL REQUESTS
# ─────────────────────────────────────────────

def special_requests():
    st.title("⏰ Extension Requests")

    con = db()
    cur = con.cursor()

    cur.execute("""
        SELECT e.id, e.request_id, i.name, u_b.name,
               e.extra_days, e.reason, e.status
        FROM extension_requests e
        JOIN requests r ON e.request_id = r.id
        JOIN items i ON r.item_id = i.id
        JOIN users u_b ON r.borrower_id = u_b.id
        WHERE r.owner_id = ?
        ORDER BY e.created_at DESC
    """, (st.session_state.user_id,))
    rows = cur.fetchall()

    if not rows:
        st.info("No extension requests received.")
        con.close()
        return

    for r in rows:
        status_color = {"Pending":"🟡","Approved":"🟢","Rejected":"🔴"}.get(r[6],"⚪")
        with st.container(border=True):
            c1, c2, c3 = st.columns(3)
            c1.write(f"**Item:** {r[2]}")
            c2.write(f"**Borrower:** {r[3]}")
            c3.write(f"**Status:** {status_color} {r[6]}")
            st.write(f"**Extra Days:** {r[4]}  |  **Reason:** {r[5]}")

            if r[6] == "Pending":
                col_a, col_b = st.columns(2)
                if col_a.button("✅ Approve", key=f"app_{r[0]}"):
                    cur.execute(
                        "UPDATE extension_requests SET status='Approved' WHERE id=?", (r[0],))
                    cur.execute(
                        "SELECT return_date, extension_count FROM requests WHERE id=?", (r[1],))
                    old = cur.fetchone()
                    new_date = date.fromisoformat(old[0]) + timedelta(days=r[4])
                    cur.execute(
                        "UPDATE requests SET return_date=?, extension_count=? WHERE id=?",
                        (new_date.isoformat(), old[1] + 1, r[1]))
                    con.commit()
                    st.rerun()
                if col_b.button("❌ Reject", key=f"rej_ext_{r[0]}"):
                    cur.execute(
                        "UPDATE extension_requests SET status='Rejected' WHERE id=?", (r[0],))
                    con.commit()
                    st.rerun()

    con.close()


# ─────────────────────────────────────────────
# DISPUTES
# ─────────────────────────────────────────────

def disputes():
    st.title("⚖️ Dispute Center")

    con = db()
    cur = con.cursor()

    with st.expander("➕ Raise a New Dispute"):
        request_id = st.number_input("Request ID", min_value=1)
        reason     = st.text_area("Describe the issue")
        if st.button("Raise Dispute", type="primary"):
            cur.execute("""
                INSERT INTO disputes (request_id, raised_by, reason, created_at)
                VALUES (?, ?, ?, ?)
            """, (request_id, st.session_state.user_id, reason,
                  datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            con.commit()
            st.success("Dispute raised. Admin will review it.")

    st.subheader("My Disputes")
    cur.execute("""
        SELECT d.id, d.request_id, i.name, d.reason, d.status, d.admin_decision
        FROM disputes d
        JOIN requests r ON d.request_id = r.id
        JOIN items i ON r.item_id = i.id
        WHERE r.owner_id=? OR r.borrower_id=? OR r.verifier_id=?
        ORDER BY d.created_at DESC
    """, (st.session_state.user_id,) * 3)

    for d in cur.fetchall():
        status_color = {"Open":"🟡","Resolved":"🟢"}.get(d[4],"⚪")
        with st.container(border=True):
            c1, c2, c3 = st.columns(3)
            c1.write(f"**Dispute #{d[0]}**")
            c2.write(f"**Item:** {d[2]}")
            c3.write(f"**Status:** {status_color} {d[4]}")
            st.write(f"**Reason:** {d[3]}")
            if d[5]:
                st.success(f"**Admin Decision:** {d[5]}")

    con.close()


# ─────────────────────────────────────────────
# RATINGS  — FIX 3: mutual ratings (both parties)
# ─────────────────────────────────────────────

def ratings_page():
    st.title("⭐ Ratings")

    con = db()
    cur = con.cursor()

    # Find all completed transactions where I was involved
    cur.execute("""
        SELECT r.id, i.name, u_b.id, u_b.name, u_o.id, u_o.name, r.status
        FROM requests r
        JOIN items i ON r.item_id = i.id
        JOIN users u_b ON r.borrower_id = u_b.id
        JOIN users u_o ON r.owner_id = u_o.id
        WHERE (r.borrower_id = ? OR r.owner_id = ?)
        AND r.status = 'Returned'
    """, (st.session_state.user_id, st.session_state.user_id))
    rows = cur.fetchall()

    pending = []
    for r in rows:
        # Check if I already rated in this transaction
        cur.execute("""
            SELECT id FROM ratings
            WHERE request_id = ? AND rater_id = ?
        """, (r[0], st.session_state.user_id))
        already_rated = cur.fetchone()
        if not already_rated:
            pending.append(r)

    if not pending:
        st.info("No pending ratings. All transactions rated!")
    else:
        st.write(f"**{len(pending)} transaction(s) pending your rating:**")

    for r in pending:
        # Determine who I'm rating
        if st.session_state.user_id == r[2]:  # I am the borrower → rate the owner
            rate_id   = r[4]
            rate_name = r[5]
            my_role   = "borrower"
        else:  # I am the owner → rate the borrower
            rate_id   = r[2]
            rate_name = r[3]
            my_role   = "owner"

        with st.container(border=True):
            st.write(f"**Request #{r[0]}** — {r[1]}")
            st.write(f"Rate: **{rate_name}**")

            score   = st.slider("Score (1–5 ⭐)", 1, 5, 5, key=f"score_{r[0]}")
            remarks = st.text_area("Remarks", key=f"rem_{r[0]}")

            if st.button(f"Submit Rating for {rate_name}", key=f"rate_{r[0]}", type="primary"):
                cur.execute("""
                    INSERT INTO ratings
                    (request_id, rater_id, rated_user_id, score, remarks, role, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    r[0], st.session_state.user_id, rate_id,
                    score, remarks, my_role,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
                # Karma bonus for 5-star rating
                if score == 5:
                    add_karma(rate_id, 3, con)
                con.commit()
                update_user_rating(rate_id)
                st.success(f"✅ Rating submitted! {'+3 karma to them for a 5★!' if score == 5 else ''}")
                st.rerun()

    st.divider()
    st.subheader("Ratings I've Received")
    cur.execute("""
        SELECT r.score, r.remarks, r.role, u.name, r.created_at
        FROM ratings r
        JOIN users u ON r.rater_id = u.id
        WHERE r.rated_user_id = ?
        ORDER BY r.created_at DESC
    """, (st.session_state.user_id,))
    received = cur.fetchall()

    if not received:
        st.info("No ratings received yet.")
    for rt in received:
        stars = "⭐" * rt[0]
        with st.container(border=True):
            st.write(f"{stars} from **{rt[3]}** ({rt[2]}) on {rt[4][:10]}")
            if rt[1]:
                st.write(f"_{rt[1]}_")

    con.close()


# ─────────────────────────────────────────────
# ADMIN PANEL  — FIX 5: names instead of IDs
# ─────────────────────────────────────────────

def admin_panel():
    st.title("🛡️ Admin Panel")

    if st.session_state.role != "admin":
        st.error("Access denied.")
        return

    con = db()
    cur = con.cursor()

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["👥 Users", "📦 Items", "📋 Requests", "⚖️ Disputes", "📊 Stats"])

    with tab1:
        st.subheader("All Users")
        # FIX 5 — readable columns, no raw IDs in display
        cur.execute("""
            SELECT name, roll, email, hostel, role, karma,
                   ROUND(avg_rating,2), rating_count
            FROM users ORDER BY karma DESC
        """)
        rows = cur.fetchall()
        st.dataframe(
            rows,
            column_config={
                0: st.column_config.TextColumn("Name"),
                1: st.column_config.TextColumn("Roll"),
                2: st.column_config.TextColumn("Email"),
                3: st.column_config.TextColumn("Hostel"),
                4: st.column_config.TextColumn("Role"),
                5: st.column_config.NumberColumn("Karma ★"),
                6: st.column_config.NumberColumn("Avg Rating"),
                7: st.column_config.NumberColumn("# Ratings"),
            },
            use_container_width=True
        )

    with tab2:
        st.subheader("All Items")
        cur.execute("""
            SELECT i.name, u.name, i.category, i.condition,
                   i.item_value, i.value_level, i.deposit, i.status, i.hostel
            FROM items i JOIN users u ON i.owner_id = u.id
            ORDER BY i.created_at DESC
        """)
        rows = cur.fetchall()
        st.dataframe(
            rows,
            column_config={
                0: st.column_config.TextColumn("Item"),
                1: st.column_config.TextColumn("Owner"),
                2: st.column_config.TextColumn("Category"),
                3: st.column_config.TextColumn("Condition"),
                4: st.column_config.NumberColumn("Value ₹"),
                5: st.column_config.TextColumn("Level"),
                6: st.column_config.NumberColumn("Deposit ₹"),
                7: st.column_config.TextColumn("Status"),
                8: st.column_config.TextColumn("Hostel"),
            },
            use_container_width=True
        )

    with tab3:
        st.subheader("All Requests")
        # FIX 5 — join names instead of showing IDs
        cur.execute("""
            SELECT r.id, i.name, u_b.name, u_o.name, u_v.name,
                   r.return_date, r.status, r.extension_count
            FROM requests r
            JOIN items i ON r.item_id = i.id
            JOIN users u_b ON r.borrower_id = u_b.id
            JOIN users u_o ON r.owner_id = u_o.id
            JOIN users u_v ON r.verifier_id = u_v.id
            ORDER BY r.created_at DESC
        """)
        rows = cur.fetchall()
        st.dataframe(
            rows,
            column_config={
                0: st.column_config.NumberColumn("Req #"),
                1: st.column_config.TextColumn("Item"),
                2: st.column_config.TextColumn("Borrower"),
                3: st.column_config.TextColumn("Owner"),
                4: st.column_config.TextColumn("Verifier"),
                5: st.column_config.TextColumn("Return Date"),
                6: st.column_config.TextColumn("Status"),
                7: st.column_config.NumberColumn("Extensions"),
            },
            use_container_width=True
        )

    with tab4:
        st.subheader("Open Disputes")
        cur.execute("""
            SELECT d.id, i.name, u_b.name, u_o.name,
                   d.reason, d.status, d.admin_decision
            FROM disputes d
            JOIN requests r ON d.request_id = r.id
            JOIN items i ON r.item_id = i.id
            JOIN users u_b ON r.borrower_id = u_b.id
            JOIN users u_o ON r.owner_id = u_o.id
            ORDER BY d.created_at DESC
        """)
        for d in cur.fetchall():
            status_color = {"Open":"🟡","Resolved":"🟢"}.get(d[5],"⚪")
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns(4)
                c1.write(f"**Dispute #{d[0]}**")
                c2.write(f"**Item:** {d[1]}")
                c3.write(f"**Borrower:** {d[2]}")
                c4.write(f"**Owner:** {d[3]}")
                st.write(f"**Reason:** {d[4]}")
                st.write(f"**Status:** {status_color} {d[5]}")
                if d[6]:
                    st.success(f"Decision: {d[6]}")
                if d[5] == "Open":
                    decision = st.text_area("Admin Decision", key=f"dec_{d[0]}")
                    if st.button("Resolve", key=f"res_{d[0]}", type="primary"):
                        cur.execute("""
                            UPDATE disputes SET status='Resolved', admin_decision=?
                            WHERE id=?
                        """, (decision, d[0]))
                        con.commit()
                        st.rerun()

    with tab5:
        st.subheader("Platform Stats")
        cur.execute("SELECT COUNT(*) FROM users")
        st.metric("Total Users", cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM items")
        st.metric("Total Items Listed", cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM requests")
        st.metric("Total Requests", cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM requests WHERE status='Returned'")
        st.metric("Completed Transactions", cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM disputes WHERE status='Open'")
        st.metric("Open Disputes", cur.fetchone()[0])
        cur.execute("SELECT AVG(score) FROM ratings")
        avg = cur.fetchone()[0]
        st.metric("Platform Avg Rating", f"{avg:.2f} ⭐" if avg else "—")

    con.close()


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

init_db()

if "user_id" not in st.session_state:
    st.session_state.user_id = None

if st.session_state.user_id is None:
    page = st.sidebar.radio("", ["Login", "Signup"])
    if page == "Login":
        login()
    else:
        signup()
else:
    st.sidebar.title("🔗 CampusShare")
    st.sidebar.write(f"👤 **{st.session_state.name}**")
    st.sidebar.write(f"⭐ Karma: **{st.session_state.get('karma', 0)}**")
    st.sidebar.divider()

    pages = [
        "Dashboard",
        "Add Item",
        "Browse Items",
        "My Requests",
        "Condition Verification",
        "Special Requests",
        "Disputes",
        "Ratings",
    ]
    if st.session_state.role == "admin":
        pages.append("Admin Panel")
    pages.append("Logout")

    choice = st.sidebar.radio("Navigate", pages)

    if choice == "Dashboard":
        dashboard()
    elif choice == "Add Item":
        add_item()
    elif choice == "Browse Items":
        browse_items()
    elif choice == "My Requests":
        my_requests()
    elif choice == "Condition Verification":
        condition_check()
    elif choice == "Special Requests":
        special_requests()
    elif choice == "Disputes":
        disputes()
    elif choice == "Ratings":
        ratings_page()
    elif choice == "Admin Panel":
        admin_panel()
    elif choice == "Logout":
        st.session_state.clear()
        st.rerun()
