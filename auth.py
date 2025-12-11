import json
import os
from flask import session, redirect, url_for, Blueprint, request, render_template
from flask_bcrypt import Bcrypt

# Bcrypt will be initialized by the Flask app
bcrypt = Bcrypt()

USERS_FILE = "users.json"
if os.environ.get("WEBSITE_INSTANCE_ID"):  # Running on Azure
    USERS_FILE = "/home/site/data/users.json"


def load_users():
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w") as f:
            json.dump({}, f)
    with open(USERS_FILE, "r") as f:
        return json.load(f)


def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=4)


def add_user(username, password, role="customer_admin"):
    """
    Add a new user with a specified role
    role can be: 'admin' or 'customer_admin'
    """
    users = load_users()
    if username in users:
        return False  # User already exists
    hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")
    users[username] = {
        "password": hashed_password,
        "role": role
    }
    save_users(users)
    return True


def check_password(username, password):
    """
    Check password and return (success, role) tuple
    Handles both old format (string) and new format (dict with password and role)
    """
    users = load_users()
    if username not in users:
        return False, None
    
    user_data = users[username]
    
    # Handle old format (backward compatibility)
    if isinstance(user_data, str):
        # Old format: just the hashed password string
        if bcrypt.check_password_hash(user_data, password):
            # Assume old users are admins, but migrate to new format
            users[username] = {"password": user_data, "role": "admin"}
            save_users(users)
            return True, "admin"
        return False, None
    
    # New format: dict with password and role
    if bcrypt.check_password_hash(user_data["password"], password):
        return True, user_data.get("role", "customer_admin")
    return False, None


def get_user_role(username):
    """Get the role of a user"""
    users = load_users()
    if username not in users:
        return None
    
    user_data = users[username]
    if isinstance(user_data, str):
        return "admin"  # Default for old format
    return user_data.get("role", "customer_admin")


def init_auth(app):
    bcrypt.init_app(app)
