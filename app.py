import streamlit as st
import sqlite3
import hashlib
from datetime import datetime, date, timedelta

st.set_page_config(page_title="CampusShare", layout="wide")

DB = "campusshare.db"


def db():
    return sqlite3.connect(DB, check_same_thread=False)


def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


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
        verifier_status TEXT DEFAULT 'No',
        rating REAL DEFAULT 5
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER,
        name TEXT,
        category TEXT,
        description TEXT,
        item_condition TEXT,
        item_value REAL,
        value_level TEXT,
        deposit REAL,
        image_note TEXT,
        status TEXT DEFAULT 'Available',
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
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
        transaction_id INTEGER,
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
        transaction_id INTEGER,
        extra_days INTEGER,
        reason TEXT,
        status TEXT DEFAULT 'Pending',
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS disputes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id INTEGER,
        raised_by INTEGER,
        reason TEXT,
        status TEXT DEFAULT 'Open',
        admin_decision TEXT,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS verifier_ratings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id INTEGER,
        rated_user_id INTEGER,
        verifier_id INTEGER,
        score INTEGER,
        remarks TEXT,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id INTEGER,
        action TEXT,
        created_at TEXT
    )
    """)

    con.commit()
    con.close()


def log_action(tid, action):
    con = db()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO logs (transaction_id, action, created_at) VALUES (?, ?, ?)",
        (tid, action, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    con.commit()
    con.close()


def classify_value(value):
    if value <= 1000:
        return "Low Value", 0
    elif value <= 5000:
        return "Medium Value", round(value * 0.30, 2)
    return "High Value", round(value * 0.50, 2)


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
            st.success("Account created. Please login.")
        except sqlite3.IntegrityError:
            st.error("Email or roll number already exists.")


def login():
    st.title("CampusShare Login")

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        con = db()
        cur = con.cursor()
        cur.execute(
            "SELECT id, name, role FROM users WHERE email=? AND password=?",
            (email, hash_pw(password))
        )
        user = cur.fetchone()
        con.close()

        if user:
            st.session_state.user_id = user[0]
            st.session_state.name = user[1]
            st.session_state.role = user[2]
            st.rerun()
        else:
            st.error("Invalid login details.")


def dashboard():
    st.title("CampusShare Dashboard")
    st.write(f"Welcome, **{st.session_state.name}**")

    con = db()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM items")
    total_items = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM items WHERE status='Available'")
    available_items = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM transactions WHERE borrower_id=?", (st.session_state.user_id,))
    my_transactions = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM disputes WHERE status='Open'")
    open_disputes = cur.fetchone()[0]

    con.close()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Items", total_items)
    c2.metric("Available Items", available_items)
    c3.metric("My Transactions", my_transactions)
    c4.metric("Open Disputes", open_disputes)


def add_item():
    st.title("Add Item")

    name = st.text_input("Item Name")
    category = st.selectbox("Category", ["Books", "Cycles", "Electronics", "Appliances", "Formals", "Other"])
    description = st.text_area("Description")
    condition = st.selectbox("Current Condition", ["New", "Good", "Usable"])
    value = st.number_input("Approximate Item Value ₹", min_value=0.0)
    image_note = st.text_area("Photo Proof Note / Image Description")

    value_level, deposit = classify_value(value)

    st.info(f"Value Level: {value_level}")
    st.info(f"Refundable Deposit Required: ₹{deposit}")

    if st.button("Add Item"):
        if not name:
            st.error("Item name is required.")
            return

        con = db()
        cur = con.cursor()
        cur.execute("""
        INSERT INTO items 
        (owner_id, name, category, description, item_condition, item_value, value_level, deposit, image_note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            st.session_state.user_id,
            name,
            category,
            description,
            condition,
            value,
            value_level,
            deposit,
            image_note,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        con.commit()
        con.close()
        st.success("Item listed successfully.")


def choose_verifier(owner_id, borrower_id):
    con = db()
    cur = con.cursor()
    cur.execute("""
    SELECT id FROM users
    WHERE verifier_status='Yes'
    AND id != ?
    AND id != ?
    ORDER BY RANDOM()
    LIMIT 1
    """, (owner_id, borrower_id))
    row = cur.fetchone()
    con.close()
    return row[0] if row else None


def browse_items():
    st.title("Browse Items")

    search = st.text_input("Search")
    category = st.selectbox("Category", ["All", "Books", "Cycles", "Electronics", "Appliances", "Formals", "Other"])

    con = db()
    cur = con.cursor()

    query = """
    SELECT items.id, items.name, items.category, items.description, items.item_condition,
           items.item_value, items.value_level, items.deposit, items.status,
           users.name, users.hostel, items.owner_id
    FROM items
    JOIN users ON items.owner_id = users.id
    WHERE items.owner_id != ?
    """
    params = [st.session_state.user_id]

    if search:
        query += " AND items.name LIKE ?"
        params.append(f"%{search}%")

    if category != "All":
        query += " AND items.category=?"
        params.append(category)

    cur.execute(query, params)
    items = cur.fetchall()
    con.close()

    for item in items:
        with st.container(border=True):
            st.subheader(item[1])
            st.write(f"**Category:** {item[2]}")
            st.write(f"**Description:** {item[3]}")
            st.write(f"**Condition:** {item[4]}")
            st.write(f"**Value:** ₹{item[5]} | {item[6]}")
            st.write(f"**Deposit:** ₹{item[7]}")
            st.write(f"**Status:** {item[8]}")
            st.write(f"**Owner:** {item[9]} | Hostel: {item[10]}")

            if item[8] == "Available":
                days = st.number_input("Borrow Duration Days", min_value=1, max_value=30, key=f"days{item[0]}")
                msg = st.text_area("Message to Owner", key=f"msg{item[0]}")

                if st.button("Request Item", key=f"req{item[0]}"):
                    verifier_id = choose_verifier(item[11], st.session_state.user_id)
                    return_date = date.today() + timedelta(days=int(days))

                    con = db()
                    cur = con.cursor()
                    cur.execute("""
                    INSERT INTO transactions 
                    (item_id, borrower_id, owner_id, verifier_id, duration_days, return_date, message, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        item[0], st.session_state.user_id, item[11], verifier_id,
                        int(days), return_date.isoformat(), msg,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ))
                    tid = cur.lastrowid
                    con.commit()
                    con.close()

                    log_action(tid, "Borrow request created")
                    st.success("Request sent successfully.")


def my_transactions():
    st.title("My Transactions")

    con = db()
    cur = con.cursor()

    st.subheader("Requests Sent By Me")
    cur.execute("""
    SELECT t.id, i.name, t.return_date, t.status, i.deposit
    FROM transactions t
    JOIN items i ON t.item_id=i.id
    WHERE t.borrower_id=?
    """, (st.session_state.user_id,))
    sent = cur.fetchall()

    for r in sent:
        with st.container(border=True):
            st.write(f"**Transaction ID:** {r[0]}")
            st.write(f"**Item:** {r[1]}")
            st.write(f"**Return Date:** {r[2]}")
            st.write(f"**Status:** {r[3]}")
            st.write(f"**Deposit:** ₹{r[4]}")

            if r[3] == "Accepted":
                extra = st.number_input("Extra days", min_value=1, max_value=7, key=f"ext{r[0]}")
                reason = st.text_area("Reason for extension", key=f"reason{r[0]}")
                if st.button("Request Extension", key=f"exbtn{r[0]}"):
                    cur.execute("SELECT extension_count FROM transactions WHERE id=?", (r[0],))
                    count = cur.fetchone()[0]

                    if count >= 2:
                        st.error("Maximum extension requests reached.")
                    else:
                        cur.execute("""
                        INSERT INTO extension_requests (transaction_id, extra_days, reason, created_at)
                        VALUES (?, ?, ?, ?)
                        """, (r[0], extra, reason, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                        con.commit()
                        log_action(r[0], "Extension request raised")
                        st.success("Extension request submitted.")

    st.subheader("Requests Received By Me")
    cur.execute("""
    SELECT t.id, i.name, u.name, t.return_date, t.status, t.item_id
    FROM transactions t
    JOIN items i ON t.item_id=i.id
    JOIN users u ON t.borrower_id=u.id
    WHERE t.owner_id=?
    """, (st.session_state.user_id,))
    received = cur.fetchall()

    for r in received:
        with st.container(border=True):
            st.write(f"**Transaction ID:** {r[0]}")
            st.write(f"**Item:** {r[1]}")
            st.write(f"**Borrower:** {r[2]}")
            st.write(f"**Return Date:** {r[3]}")
            st.write(f"**Status:** {r[4]}")

            if r[4] == "Pending":
                c1, c2 = st.columns(2)
                if c1.button("Accept", key=f"acc{r[0]}"):
                    cur.execute("UPDATE transactions SET status='Accepted' WHERE id=?", (r[0],))
                    cur.execute("UPDATE items SET status='Unavailable' WHERE id=?", (r[5],))
                    con.commit()
                    log_action(r[0], "Request accepted by lender")
                    st.rerun()

                if c2.button("Reject", key=f"rej{r[0]}"):
                    cur.execute("UPDATE transactions SET status='Rejected' WHERE id=?", (r[0],))
                    con.commit()
                    log_action(r[0], "Request rejected by lender")
                    st.rerun()

            if r[4] == "Accepted":
                if st.button("Mark Returned", key=f"ret{r[0]}"):
                    cur.execute("UPDATE transactions SET status='Returned' WHERE id=?", (r[0],))
                    cur.execute("UPDATE items SET status='Available' WHERE id=?", (r[5],))
                    con.commit()
                    log_action(r[0], "Item marked returned")
                    st.rerun()

    con.close()


def condition_verification():
    st.title("Condition Verification")

    con = db()
    cur = con.cursor()

    cur.execute("""
    SELECT t.id, i.name, t.status
    FROM transactions t
    JOIN items i ON t.item_id=i.id
    WHERE t.verifier_id=? OR t.owner_id=? OR t.borrower_id=?
    """, (st.session_state.user_id, st.session_state.user_id, st.session_state.user_id))
    rows = cur.fetchall()

    for r in rows:
        with st.container(border=True):
            st.write(f"**Transaction:** {r[0]} | **Item:** {r[1]} | **Status:** {r[2]}")
            stage = st.selectbox("Stage", ["Before Handover", "After Return"], key=f"stage{r[0]}")
            working = st.checkbox("Item working properly", key=f"work{r[0]}")
            no_damage = st.checkbox("No visible damage", key=f"damage{r[0]}")
            accessories = st.checkbox("Accessories included", key=f"accs{r[0]}")
            clean = st.checkbox("Clean condition", key=f"clean{r[0]}")
            photo_note = st.text_area("Photo proof note", key=f"photo{r[0]}")

            if st.button("Submit Condition Check", key=f"check{r[0]}"):
                cur.execute("""
                INSERT INTO condition_checks
                (transaction_id, stage, working, no_damage, accessories, clean, photo_note, checked_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    r[0], stage, str(working), str(no_damage), str(accessories),
                    str(clean), photo_note, st.session_state.user_id,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
                con.commit()
                log_action(r[0], f"Condition check submitted: {stage}")
                st.success("Condition check submitted.")

    con.close()


def special_requests():
    st.title("Special / Extension Requests")

    con = db()
    cur = con.cursor()

    cur.execute("""
    SELECT e.id, e.transaction_id, i.name, u.name, e.extra_days, e.reason, e.status
    FROM extension_requests e
    JOIN transactions t ON e.transaction_id=t.id
    JOIN items i ON t.item_id=i.id
    JOIN users u ON t.borrower_id=u.id
    WHERE t.owner_id=?
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

                if c1.button("Approve", key=f"appr{r[0]}"):
                    cur.execute("UPDATE extension_requests SET status='Approved' WHERE id=?", (r[0],))
                    cur.execute("SELECT return_date, extension_count FROM transactions WHERE id=?", (r[1],))
                    old_date, count = cur.fetchone()
                    new_date = date.fromisoformat(old_date) + timedelta(days=r[4])
                    cur.execute("""
                    UPDATE transactions SET return_date=?, extension_count=? WHERE id=?
                    """, (new_date.isoformat(), count + 1, r[1]))
                    con.commit()
                    log_action(r[1], "Extension approved")
                    st.rerun()

                if c2.button("Reject", key=f"rext{r[0]}"):
                    cur.execute("UPDATE extension_requests SET status='Rejected' WHERE id=?", (r[0],))
                    con.commit()
                    log_action(r[1], "Extension rejected")
                    st.rerun()

    con.close()


def disputes():
    st.title("Dispute Center")

    con = db()
    cur = con.cursor()

    tid = st.number_input("Transaction ID", min_value=1)
    reason = st.text_area("Dispute Reason")

    if st.button("Raise Dispute"):
        cur.execute("""
        INSERT INTO disputes (transaction_id, raised_by, reason, created_at)
        VALUES (?, ?, ?, ?)
        """, (tid, st.session_state.user_id, reason, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        con.commit()
        log_action(tid, "Dispute raised")
        st.success("Dispute raised.")

    st.subheader("My Related Disputes")
    cur.execute("""
    SELECT d.id, d.transaction_id, d.reason, d.status, d.admin_decision
    FROM disputes d
    JOIN transactions t ON d.transaction_id=t.id
    WHERE t.owner_id=? OR t.borrower_id=? OR t.verifier_id=?
    """, (st.session_state.user_id, st.session_state.user_id, st.session_state.user_id))

    for d in cur.fetchall():
        with st.container(border=True):
            st.write(f"**Dispute ID:** {d[0]}")
            st.write(f"**Transaction:** {d[1]}")
            st.write(f"**Reason:** {d[2]}")
            st.write(f"**Status:** {d[3]}")
            st.write(f"**Admin Decision:** {d[4]}")

    con.close()


def verifier_rating():
    st.title("Verifier Rating")

    con = db()
    cur = con.cursor()

    cur.execute("""
    SELECT t.id, i.name, b.id, b.name, o.id, o.name
    FROM transactions t
    JOIN items i ON t.item_id=i.id
    JOIN users b ON t.borrower_id=b.id
    JOIN users o ON t.owner_id=o.id
    WHERE t.verifier_id=? AND t.status IN ('Returned', 'Completed')
    """, (st.session_state.user_id,))
    rows = cur.fetchall()

    for r in rows:
        with st.container(border=True):
            st.write(f"**Transaction:** {r[0]} | **Item:** {r[1]}")

            rated = st.selectbox(
                "Rate User",
                [(r[2], f"Borrower: {r[3]}"), (r[4], f"Lender: {r[5]}")],
                format_func=lambda x: x[1],
                key=f"rated{r[0]}"
            )

            score = st.slider("Checklist Score", 1, 5, 5, key=f"score{r[0]}")
            remarks = st.text_area("Remarks", key=f"remarks{r[0]}")

            if st.button("Submit Rating", key=f"vr{r[0]}"):
                cur.execute("""
                INSERT INTO verifier_ratings
                (transaction_id, rated_user_id, verifier_id, score, remarks, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    r[0], rated[0], st.session_state.user_id, score, remarks,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))

                cur.execute("""
                SELECT AVG(score) FROM verifier_ratings WHERE rated_user_id=?
                """, (rated[0],))
                avg = cur.fetchone()[0]

                cur.execute("UPDATE users SET rating=? WHERE id=?", (avg, rated[0]))

                con.commit()
                log_action(r[0], "Verifier rating submitted")
                st.success("Rating submitted.")

    con.close()


def admin_panel():
    st.title("Admin Panel")

    if st.session_state.role != "admin":
        st.error("Only admin can access this page.")
        return

    con = db()
    cur = con.cursor()

    st.subheader("Users")
    cur.execute("SELECT id, name, roll, email, hostel, verifier_status, rating FROM users")
    st.dataframe(cur.fetchall())

    st.subheader("Items")
    cur.execute("SELECT id, name, value_level, deposit, status FROM items")
    st.dataframe(cur.fetchall())

    st.subheader("Transactions")
    cur.execute("SELECT id, item_id, borrower_id, owner_id, verifier_id, status, return_date FROM transactions")
    st.dataframe(cur.fetchall())

    st.subheader("Open Disputes")
    cur.execute("SELECT id, transaction_id, reason, status, admin_decision FROM disputes")
    disputes_data = cur.fetchall()
    st.dataframe(disputes_data)

    dispute_id = st.number_input("Dispute ID to Resolve", min_value=1)
    decision = st.text_area("Admin Decision")

    if st.button("Resolve Dispute"):
        cur.execute("""
        UPDATE disputes SET status='Resolved', admin_decision=? WHERE id=?
        """, (decision, dispute_id))
        con.commit()
        st.success("Dispute resolved.")

    st.subheader("Audit Logs")
    cur.execute("SELECT transaction_id, action, created_at FROM logs ORDER BY id DESC")
    st.dataframe(cur.fetchall())

    con.close()


def logout():
    st.session_state.clear()
    st.rerun()


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
        "My Transactions",
        "Condition Verification",
        "Special Requests",
        "Disputes",
        "Verifier Rating"
    ]

    if st.session_state.role == "admin":
        pages.append("Admin Panel")

    pages.append("Logout")

    page = st.sidebar.radio("Menu", pages)

    if page == "Dashboard":
        dashboard()
    elif page == "Add Item":
        add_item()
    elif page == "Browse Items":
        browse_items()
    elif page == "My Transactions":
        my_transactions()
    elif page == "Condition Verification":
        condition_verification()
    elif page == "Special Requests":
        special_requests()
    elif page == "Disputes":
        disputes()
    elif page == "Verifier Rating":
        verifier_rating()
    elif page == "Admin Panel":
        admin_panel()
    elif page == "Logout":
        logout()