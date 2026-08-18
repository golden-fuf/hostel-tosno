import os
import requests
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ==================== АУТЕНТИФИКАЦИЯ ====================
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "hostel-secret-2026")

# ==================== ПРОСТЫЕ ЭНДПОИНТЫ ДЛЯ ТЕСТА ====================

@app.route('/api/test')
def test():
    """Простой тестовый эндпоинт"""
    return jsonify({
        "status": "ok",
        "message": "Сервер работает!",
        "supabase_url": SUPABASE_URL
    })

@app.route('/api/test-db')
def test_db():
    """Проверка подключения к Supabase"""
    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
        url = f"{SUPABASE_URL}/rest/v1/residents?select=count"
        response = requests.get(url, headers=headers)
        return jsonify({
            "status": "db_connected",
            "status_code": response.status_code,
            "response": response.text[:200] if response.text else "empty"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==================== ОСНОВНЫЕ API ====================

@app.route('/api/residents')
def get_residents():
    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
        url = f"{SUPABASE_URL}/rest/v1/residents?select=*&order=room.asc,place.asc"
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return jsonify({"error": f"Supabase error: {response.status_code}"}), 500
        return jsonify(response.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/report')
def get_report():
    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
        url = f"{SUPABASE_URL}/rest/v1/residents?select=*"
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return jsonify({"error": f"Supabase error: {response.status_code}"}), 500
        
        residents = response.json()
        total = len(residents)
        occupied = len([r for r in residents if r.get('full_name') != '(свободно)'])
        free = total - occupied
        
        return jsonify({
            "total": total,
            "occupied": occupied,
            "free": free,
            "load_percent": round((occupied / total) * 100, 1) if total > 0 else 0,
            "groups": [],
            "settings": {}
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/floors')
def get_floors():
    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
        url = f"{SUPABASE_URL}/rest/v1/residents?select=floor"
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return jsonify({"error": f"Supabase error: {response.status_code}"}), 500
        
        floors = list(set(r.get('floor') for r in response.json()))
        floors.sort()
        return jsonify(floors)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/groups')
def get_groups():
    return jsonify([])

@app.route('/api/free_places')
def get_free_places():
    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        }
        url = f"{SUPABASE_URL}/rest/v1/residents?select=room,place,floor&full_name=eq.(свободно)&order=room.asc,place.asc"
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return jsonify({"error": f"Supabase error: {response.status_code}"}), 500
        return jsonify(response.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
