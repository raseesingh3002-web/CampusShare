import streamlit as st
import sqlite3
import hashlib
from datetime import datetime

st.set_page_config(page_title="CampusShare", layout="wide")

DB = "campusshare.db"


# -------------------- DB --------------------
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
        email TEXT UNIQUE,
        password TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER,
        name TEXT,
        category TEXT,
        description TEXT,
        image_name TEXT,
        status TEXT DEFAULT 'Available'
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER,
        borrower_id INTEGER,
        owner_id INTEGER,
        verifier_id INTEGER,
        status TEXT DEFAULT 'Pending'
    )
    """)

    con.commit()
    con.close()


# -------------------- AUTH --------------------
def signup():
    st.title("Signup")

    name = st.text_input("Name")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Create Account"):
        con = db()
        cur = con.cursor()
        try:
            cur.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                        (name, email, hash_pw(password)))
            con.commit()
            st.success("Account created. Login now.")
        except:
            st.error("User already exists.")
        con.close()


def login():
    st.title("Login")

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        con = db()
        cur = con.cursor()

        cur.execute("SELECT id, name FROM users WHERE email=? AND password=?",
                    (email, hash_pw(password)))
        user = cur.fetchone()

        if user:
            st.session_state.user_id = user[0]
            st.session_state.name = user[1]
            st.success("Login successful")
            st.rerun()
        else:
            st.error("Invalid login")

        con.close()


# -------------------- ADD ITEM --------------------
def add_item():
    st.title("Add Item")

    name = st.text_input("Item Name")
    category = st.selectbox("Category", ["Books", "Electronics", "Cycle", "Other"])
    description = st.text_area("Description")

    image = st.file_uploader("Upload Image", type=["jpg", "png", "jpeg"])

    if image:
        st.image(image, width=200)

    if st.button("Add Item"):
        con = db()
        cur = con.cursor()

        image_name = image.name if image else ""

        cur.execute("""
        INSERT INTO items (owner_id, name, category, description, image_name)
        VALUES (?, ?, ?, ?, ?)
        """, (st.session_state.user_id, name, category, description, image_name))

        con.commit()
        con.close()

        st.success("Item added")


# -------------------- BROWSE --------------------
def browse():
    st.title("Browse Items")

    con = db()
    cur = con.cursor()

    cur.execute("""
    SELECT items.id, items.name, items.category, items.description,
           items.status, users.name, items.owner_id
    FROM items
    JOIN users ON items.owner_id = users.id
    WHERE items.owner_id != ?
    """, (st.session_state.user_id,))

    items = cur.fetchall()

    for item in items:
        with st.container(border=True):
            st.subheader(item[1])
            st.write(f"Category: {item[2]}")
            st.write(f"Description: {item[3]}")
            st.write(f"Owner: {item[5]}")
            st.write(f"Status: {item[4]}")

            if item[4] == "Available":

                # Fetch users for verifier selection
                cur.execute("""
                SELECT id, name FROM users
                WHERE id != ? AND id != ?
                """, (st.session_state.user_id, item[6]))

                users = cur.fetchall()

                verifier = st.selectbox(
                    "Select Verifier",
                    users,
                    format_func=lambda x: x[1],
                    key=f"ver{item[0]}"
                )

                if st.button("Request", key=f"req{item[0]}"):
                    cur.execute("""
                    INSERT INTO requests (item_id, borrower_id, owner_id, verifier_id)
                    VALUES (?, ?, ?, ?)
                    """, (item[0], st.session_state.user_id, item[6], verifier[0]))

                    con.commit()
                    st.success("Request sent")

    con.close()


# -------------------- REQUESTS --------------------
def requests_page():
    st.title("My Requests")

    con = db()
    cur = con.cursor()

    # Requests received
    st.subheader("Requests Received")

    cur.execute("""
    SELECT r.id, i.name, u.name, r.status
    FROM requests r
    JOIN items i ON r.item_id = i.id
    JOIN users u ON r.borrower_id = u.id
    WHERE r.owner_id = ?
    """, (st.session_state.user_id,))

    data = cur.fetchall()

    for r in data:
        with st.container(border=True):
            st.write(f"Item: {r[1]}")
            st.write(f"Borrower: {r[2]}")
            st.write(f"Status: {r[3]}")

            if r[3] == "Pending":
                c1, c2 = st.columns(2)

                if c1.button("Accept", key=f"a{r[0]}"):
                    cur.execute("UPDATE requests SET status='Accepted' WHERE id=?", (r[0],))
                    con.commit()
                    st.rerun()

                if c2.button("Reject", key=f"x{r[0]}"):
                    cur.execute("UPDATE requests SET status='Rejected' WHERE id=?", (r[0],))
                    con.commit()
                    st.rerun()

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
    st.sidebar.title(f"Welcome {st.session_state.name}")

    menu = ["Add Item", "Browse", "My Requests", "Logout"]
    choice = st.sidebar.radio("Menu", menu)

    if choice == "Add Item":
        add_item()
    elif choice == "Browse":
        browse()
    elif choice == "My Requests":
        requests_page()
    elif choice == "Logout":
        st.session_state.clear()
        st.rerun()
