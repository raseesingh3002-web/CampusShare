import streamlit as st
import sqlite3
import hashlib
from datetime import datetime, date, timedelta

st.set_page_config(page_title="CampusShare", layout="wide")

DB = "campusshare.db"


# -------------------- DATABASE --------------------

def db():
    return sqlite3.connect(DB, check_same_thread=False)


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
        verifier_status TEXT DEFAULT 'No'
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
        image_name TEXT,
        status TEXT DEFAULT 'Available',
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
        photo_note TEXT,
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
        rated_user_id INTEGER,
        verifier_id INTEGER,
        score INTEGER,
        remarks TEXT,
        created_at TEXT
    )
    """)

    con.commit()
    con.close()


# -------------------- HELPERS --------------------

def classify_value(value):
    if value <= 1000:
        return "Low Value", 0
    elif value <= 5000:
        return "Medium Value", round(value * 0.30, 2)
    else:
        return "High Value", round(value * 0.50, 2)


# -------------------- AUTH --------------------

def signup():
    st.title("CampusShare Signup")

    name = st.text_input("Name")
    roll = st.text_input("Roll Number")
    email = st.text_input("Institute Email")
    password = st.text_input("Password", type="password")
    hostel = st.text_input("Hostel")
    verifier = st.checkbox("I want to volunteer as a Peer Verifier")

    if st.button("Create Account"):
        if not name or not roll or not email or not password:
            st.error("Please fill all required fields.")
            return

        role = "admin" if email == "admin@iiitm.ac.in" else "student"
        verifier_status = "Yes" if verifier else "No"

        try:
            con = db()
            cur = con.cursor()
            cur.execute("""
            INSERT INTO users (name, roll, email, password, hostel, role, verifier_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (name, roll, email, hash_pw(password), hostel, role, verifier_status))
            con.commit()
            con.close()
            st.success("Account created successfully. Please login.")
        except sqlite3.IntegrityError:
            st.error("Email or roll number already exists.")


def login():
    st.title("CampusShare Login")

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        con = db()
        cur = con.cursor()

        cur.execute("""
        SELECT id, name, role FROM users
        WHERE email=? AND password=?
        """, (email, hash_pw(password)))

        user = cur.fetchone()
        con.close()

        if user:
            st.session_state.user_id = user[0]
            st.session_state.name = user[1]
            st.session_state.role = user[2]
            st.success("Login successful.")
            st.rerun()
        else:
            st.error("Invalid email or password.")


# -------------------- DASHBOARD --------------------

def dashboard():
    st.title("CampusShare Dashboard")
    st.write(f"Welcome, **{st.session_state.name}**")

    con = db()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM items")
    total_items = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM items WHERE status='Available'")
    available_items = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM requests WHERE borrower_id=?", (st.session_state.user_id,))
    my_requests = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM disputes WHERE status='Open'")
    disputes_count = cur.fetchone()[0]

    con.close()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Items", total_items)
    c2.metric("Available Items", available_items)
    c3.metric("My Requests", my_requests)
    c4.metric("Open Disputes", disputes_count)


# -------------------- ADD ITEM --------------------

def add_item():
    st.title("Add Item")

    name = st.text_input("Item Name")
    category = st.selectbox("Category", ["Books", "Cycles", "Electronics", "Appliances", "Formals", "Other"])
    description = st.text_area("Description")
    condition = st.selectbox("Item Condition", ["New", "Good", "Usable"])
    value = st.number_input("Approximate Item Value ₹", min_value=0.0)

    value_level, deposit = classify_value(value)

    st.info(f"Value Level: {value_level}")
    st.info(f"Refundable Security Deposit: ₹{deposit}")

    image = st.file_uploader("Upload Item Image", type=["jpg", "jpeg", "png"])

    image_name = ""
    if image is not None:
        st.image(image, caption="Uploaded Item Image", use_container_width=True)
        image_name = image.name

    if st.button("Add Item"):
        if not name:
            st.error("Item name is required.")
            return

        con = db()
        cur = con.cursor()

        cur.execute("""
        INSERT INTO items
        (owner_id, name, category, description, item_value, value_level, deposit, condition, image_name, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            st.session_state.user_id,
            name,
            category,
            description,
            value,
            value_level,
            deposit,
            condition,
            image_name,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        con.commit()
        con.close()

        st.success("Item listed successfully.")


# -------------------- BROWSE ITEMS --------------------

def browse_items():
    st.title("Browse Items")

    search = st.text_input("Search Item")
    category_filter = st.selectbox(
        "Filter by Category",
        ["All", "Books", "Cycles", "Electronics", "Appliances", "Formals", "Other"]
    )

    con = db()
    cur = con.cursor()

    query = """
    SELECT items.id, items.name, items.category, items.description, items.item_value,
           items.value_level, items.deposit, items.condition, items.image_name,
           items.status, users.name, users.hostel, items.owner_id
    FROM items
    JOIN users ON items.owner_id = users.id
    WHERE items.owner_id != ?
    """

    params = [st.session_state.user_id]

    if search:
        query += " AND items.name LIKE ?"
        params.append(f"%{search}%")

    if category_filter != "All":
        query += " AND items.category=?"
        params.append(category_filter)

    cur.execute(query, params)
    items = cur.fetchall()

    if not items:
        st.info("No items found.")

    for item in items:
        with st.container(border=True):
            st.subheader(item[1])
            st.write(f"**Category:** {item[2]}")
            st.write(f"**Description:** {item[3]}")
            st.write(f"**Value:** ₹{item[4]}")
            st.write(f"**Value Level:** {item[5]}")
            st.write(f"**Deposit:** ₹{item[6]}")
            st.write(f"**Condition:** {item[7]}")
            st.image(f"**Image Uploaded:** {item[8] if item[8] else 'No image'}")
            st.write(f"**Status:** {item[9]}")
            st.write(f"**Owner:** {item[10]} | Hostel: {item[11]}")

            if item[9] == "Available":
                days = st.number_input(
                    "Borrow Duration Days",
                    min_value=1,
                    max_value=30,
                    key=f"days_{item[0]}"
                )

                message = st.text_area("Message to Owner", key=f"msg_{item[0]}")

                cur.execute("""
                SELECT id, name FROM users
                WHERE id != ? AND id != ?
                """, (st.session_state.user_id, item[12]))

                verifier_options = cur.fetchall()

                if verifier_options:
                    selected_verifier = st.selectbox(
                        "Select Verifier",
                        verifier_options,
                        format_func=lambda x: x[1],
                        key=f"verifier_{item[0]}"
                    )
                else:
                    selected_verifier = None
                    st.warning("No verifier available.")

                if st.button("Request Item", key=f"req_{item[0]}"):
                    if selected_verifier is None:
                        st.error("Please select a verifier.")
                    else:
                        return_date = date.today() + timedelta(days=int(days))

                        cur.execute("""
                        INSERT INTO requests
                        (item_id, borrower_id, owner_id, verifier_id, duration_days, return_date, message, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            item[0],
                            st.session_state.user_id,
                            item[12],
                            selected_verifier[0],
                            int(days),
                            return_date.isoformat(),
                            message,
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        ))

                        con.commit()
                        st.success("Request sent successfully.")

    con.close()


# -------------------- MY REQUESTS --------------------

def my_requests():
    st.title("My Requests")

    con = db()
    cur = con.cursor()

    st.subheader("Requests Sent By Me")

    cur.execute("""
    SELECT r.id, i.name, u.name, r.return_date, r.status, i.deposit
    FROM requests r
    JOIN items i ON r.item_id=i.id
    JOIN users u ON r.verifier_id=u.id
    WHERE r.borrower_id=?
    """, (st.session_state.user_id,))

    sent = cur.fetchall()

    for r in sent:
        with st.container(border=True):
            st.write(f"**Request ID:** {r[0]}")
            st.write(f"**Item:** {r[1]}")
            st.write(f"**Verifier:** {r[2]}")
            st.write(f"**Return Date:** {r[3]}")
            st.write(f"**Status:** {r[4]}")
            st.write(f"**Deposit:** ₹{r[5]}")

            if r[4] == "Accepted":
                extra_days = st.number_input("Request extra days", min_value=1, max_value=7, key=f"extra_{r[0]}")
                reason = st.text_area("Reason for extension", key=f"reason_{r[0]}")

                if st.button("Submit Special Request", key=f"ext_{r[0]}"):
                    cur.execute("SELECT extension_count FROM requests WHERE id=?", (r[0],))
                    count = cur.fetchone()[0]

                    if count >= 2:
                        st.error("Maximum extension requests reached.")
                    else:
                        cur.execute("""
                        INSERT INTO extension_requests (request_id, extra_days, reason, created_at)
                        VALUES (?, ?, ?, ?)
                        """, (
                            r[0],
                            extra_days,
                            reason,
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        ))
                        con.commit()
                        st.success("Special request submitted.")

    st.subheader("Requests Received")

    cur.execute("""
    SELECT r.id, i.name, b.name, v.name, r.return_date, r.status, r.item_id
    FROM requests r
    JOIN items i ON r.item_id=i.id
    JOIN users b ON r.borrower_id=b.id
    JOIN users v ON r.verifier_id=v.id
    WHERE r.owner_id=?
    """, (st.session_state.user_id,))

    received = cur.fetchall()

    for r in received:
        with st.container(border=True):
            st.write(f"**Request ID:** {r[0]}")
            st.write(f"**Item:** {r[1]}")
            st.write(f"**Borrower:** {r[2]}")
            st.write(f"**Selected Verifier:** {r[3]}")
            st.write(f"**Return Date:** {r[4]}")
            st.write(f"**Status:** {r[5]}")

            if r[5] == "Pending":
                c1, c2 = st.columns(2)

                if c1.button("Accept", key=f"accept_{r[0]}"):
                    cur.execute("UPDATE requests SET status='Accepted' WHERE id=?", (r[0],))
                    cur.execute("UPDATE items SET status='Unavailable' WHERE id=?", (r[6],))
                    con.commit()
                    st.rerun()

                if c2.button("Reject", key=f"reject_{r[0]}"):
                    cur.execute("UPDATE requests SET status='Rejected' WHERE id=?", (r[0],))
                    con.commit()
                    st.rerun()

            if r[5] == "Accepted":
                if st.button("Mark as Returned", key=f"return_{r[0]}"):
                    cur.execute("UPDATE requests SET status='Returned' WHERE id=?", (r[0],))
                    cur.execute("UPDATE items SET status='Available' WHERE id=?", (r[6],))
                    con.commit()
                    st.rerun()

    con.close()


# -------------------- CONDITION CHECK --------------------

def condition_check():
    st.title("Condition Verification")

    con = db()
    cur = con.cursor()

    cur.execute("""
    SELECT r.id, i.name, r.status
    FROM requests r
    JOIN items i ON r.item_id=i.id
    WHERE r.verifier_id=? OR r.borrower_id=? OR r.owner_id=?
    """, (st.session_state.user_id, st.session_state.user_id, st.session_state.user_id))

    rows = cur.fetchall()

    for r in rows:
        with st.container(border=True):
            st.write(f"**Request ID:** {r[0]}")
            st.write(f"**Item:** {r[1]}")
            st.write(f"**Status:** {r[2]}")

            stage = st.selectbox("Stage", ["Before Handover", "After Return"], key=f"stage_{r[0]}")

            working = st.checkbox("Item working properly", key=f"working_{r[0]}")
            no_damage = st.checkbox("No visible damage", key=f"damage_{r[0]}")
            accessories = st.checkbox("Accessories included", key=f"accessories_{r[0]}")
            clean = st.checkbox("Clean condition", key=f"clean_{r[0]}")
            photo_note = st.text_area("Photo proof note", key=f"photo_{r[0]}")

            if st.button("Submit Condition Check", key=f"check_{r[0]}"):
                cur.execute("""
                INSERT INTO condition_checks
                (request_id, stage, working, no_damage, accessories, clean, photo_note, checked_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    r[0],
                    stage,
                    str(working),
                    str(no_damage),
                    str(accessories),
                    str(clean),
                    photo_note,
                    st.session_state.user_id,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))

                con.commit()
                st.success("Condition check submitted.")

    con.close()


# -------------------- SPECIAL REQUESTS --------------------

def special_requests():
    st.title("Special Requests")

    con = db()
    cur = con.cursor()

    cur.execute("""
    SELECT e.id, e.request_id, i.name, b.name, e.extra_days, e.reason, e.status
    FROM extension_requests e
    JOIN requests r ON e.request_id=r.id
    JOIN items i ON r.item_id=i.id
    JOIN users b ON r.borrower_id=b.id
    WHERE r.owner_id=?
    """, (st.session_state.user_id,))

    rows = cur.fetchall()

    for r in rows:
        with st.container(border=True):
            st.write(f"**Item:** {r[2]}")
            st.write(f"**Borrower:** {r[3]}")
            st.write(f"**Extra Days:** {r[4]}")
            st.write(f"**Reason:** {r[5]}")
            st.write(f"**Status:** {r[6]}")

            if r[6] == "Pending":
                c1, c2 = st.columns(2)

                if c1.button("Approve", key=f"approve_{r[0]}"):
                    cur.execute("UPDATE extension_requests SET status='Approved' WHERE id=?", (r[0],))
                    cur.execute("SELECT return_date, extension_count FROM requests WHERE id=?", (r[1],))
                    old_date, count = cur.fetchone()
                    new_date = date.fromisoformat(old_date) + timedelta(days=r[4])

                    cur.execute("""
                    UPDATE requests SET return_date=?, extension_count=? WHERE id=?
                    """, (new_date.isoformat(), count + 1, r[1]))

                    con.commit()
                    st.rerun()

                if c2.button("Reject", key=f"reject_ext_{r[0]}"):
                    cur.execute("UPDATE extension_requests SET status='Rejected' WHERE id=?", (r[0],))
                    con.commit()
                    st.rerun()

    con.close()


# -------------------- DISPUTES --------------------

def disputes():
    st.title("Dispute Center")

    con = db()
    cur = con.cursor()

    request_id = st.number_input("Request ID", min_value=1)
    reason = st.text_area("Dispute Reason")

    if st.button("Raise Dispute"):
        cur.execute("""
        INSERT INTO disputes (request_id, raised_by, reason, created_at)
        VALUES (?, ?, ?, ?)
        """, (
            request_id,
            st.session_state.user_id,
            reason,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        con.commit()
        st.success("Dispute raised.")

    st.subheader("Related Disputes")

    cur.execute("""
    SELECT d.id, d.request_id, d.reason, d.status, d.admin_decision
    FROM disputes d
    JOIN requests r ON d.request_id=r.id
    WHERE r.owner_id=? OR r.borrower_id=? OR r.verifier_id=?
    """, (st.session_state.user_id, st.session_state.user_id, st.session_state.user_id))

    for d in cur.fetchall():
        with st.container(border=True):
            st.write(f"**Dispute ID:** {d[0]}")
            st.write(f"**Request ID:** {d[1]}")
            st.write(f"**Reason:** {d[2]}")
            st.write(f"**Status:** {d[3]}")
            st.write(f"**Admin Decision:** {d[4]}")

    con.close()


# -------------------- VERIFIER RATING --------------------

def verifier_rating():
    st.title("Verifier Rating")

    con = db()
    cur = con.cursor()

    cur.execute("""
    SELECT r.id, i.name, b.id, b.name, o.id, o.name
    FROM requests r
    JOIN items i ON r.item_id=i.id
    JOIN users b ON r.borrower_id=b.id
    JOIN users o ON r.owner_id=o.id
    WHERE r.verifier_id=? AND r.status='Returned'
    """, (st.session_state.user_id,))

    rows = cur.fetchall()

    for r in rows:
        with st.container(border=True):
            st.write(f"**Request ID:** {r[0]}")
            st.write(f"**Item:** {r[1]}")

            selected_user = st.selectbox(
                "Rate User",
                [(r[2], f"Borrower: {r[3]}"), (r[4], f"Lender: {r[5]}")],
                format_func=lambda x: x[1],
                key=f"rate_user_{r[0]}"
            )

            score = st.slider("Checklist Score", 1, 5, 5, key=f"score_{r[0]}")
            remarks = st.text_area("Remarks", key=f"remarks_{r[0]}")

            if st.button("Submit Rating", key=f"submit_rating_{r[0]}"):
                cur.execute("""
                INSERT INTO ratings
                (request_id, rated_user_id, verifier_id, score, remarks, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    r[0],
                    selected_user[0],
                    st.session_state.user_id,
                    score,
                    remarks,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))

                con.commit()
                st.success("Verifier rating submitted.")

    con.close()


# -------------------- ADMIN --------------------

def admin_panel():
    st.title("Admin Panel")

    if st.session_state.role != "admin":
        st.error("Access denied.")
        return

    con = db()
    cur = con.cursor()

    st.subheader("Users")
    cur.execute("SELECT id, name, roll, email, hostel, role, verifier_status FROM users")
    st.dataframe(cur.fetchall())

    st.subheader("Items")
    cur.execute("SELECT id, name, value_level, deposit, status FROM items")
    st.dataframe(cur.fetchall())

    st.subheader("Requests")
    cur.execute("SELECT id, item_id, borrower_id, owner_id, verifier_id, status, return_date FROM requests")
    st.dataframe(cur.fetchall())

    st.subheader("Disputes")
    cur.execute("SELECT id, request_id, reason, status, admin_decision FROM disputes")
    st.dataframe(cur.fetchall())

    dispute_id = st.number_input("Dispute ID to Resolve", min_value=1)
    decision = st.text_area("Admin Decision")

    if st.button("Resolve Dispute"):
        cur.execute("""
        UPDATE disputes SET status='Resolved', admin_decision=? WHERE id=?
        """, (decision, dispute_id))
        con.commit()
        st.success("Dispute resolved.")

    con.close()


# -------------------- MAIN --------------------

init_db()

if "user_id" not in st.session_state:
    st.session_state.user_id = None

if st.session_state.user_id is None:
    page = st.sidebar.radio("Menu", ["Login", "Signup"])

    if page == "Login":
        login()
    else:
        signup()

else:
    st.sidebar.title("CampusShare")
    st.sidebar.write(f"Logged in as: {st.session_state.name}")

    pages = [
        "Dashboard",
        "Add Item",
        "Browse Items",
        "My Requests",
        "Condition Verification",
        "Special Requests",
        "Disputes",
        "Verifier Rating"
    ]

    if st.session_state.role == "admin":
        pages.append("Admin Panel")

    pages.append("Logout")

    choice = st.sidebar.radio("Menu", pages)

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
    elif choice == "Verifier Rating":
        verifier_rating()
    elif choice == "Admin Panel":
        admin_panel()
    elif choice == "Logout":
        st.session_state.clear()
        st.rerun()
