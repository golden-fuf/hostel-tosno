import os
import re
import requests
from datetime import datetime
from typing import Optional
from functools import wraps
from pydantic import BaseModel, field_validator, ValidationError
from flask import Flask, request, jsonify, send_from_directory, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app, resources={r"/api/*": {"origins": os.getenv("CORS_ORIGINS", "*").split(",")}})

# ==================== ПОДКЛЮЧЕНИЕ К SUPABASE ====================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ==================== ЗАПРОСЫ К SUPABASE ====================
def supabase_request(method, endpoint, data=None, params=None):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    if method.upper() == "GET":
        response = requests.get(url, headers=headers, params=params)
    else:
        response = requests.request(method, url, headers=headers, json=data, params=params)
    
    return response

# ==================== АУТЕНТИФИКАЦИЯ ====================
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "hostel-secret-2026")
GUEST_TOKEN = os.getenv("GUEST_TOKEN", "guest-view-2026")

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-Auth-Token", "")
        if token not in (AUTH_TOKEN, GUEST_TOKEN):
            return jsonify({"error": "Unauthorized"}), 401
        
        # Если гость — разрешаем только GET и OPTIONS (экспорт тоже отдельно проверяется)
        if token == GUEST_TOKEN and request.method not in ["GET", "OPTIONS"]:
            return jsonify({"error": "Forbidden: read-only mode"}), 403
        return f(*args, **kwargs)
    return decorated

# ==================== PYDANTIC МОДЕЛИ ====================
PHONE_RE = re.compile(r'^\+?\d{10,15}$')

class ResidentUpdate(BaseModel):
    group_name: str = '-'
    full_name: str
    check_in: Optional[str] = None
    registration: Optional[str] = None
    phone: Optional[str] = '-'
    note: Optional[str] = '-'

    @field_validator('check_in', 'registration', mode='before')
    @classmethod
    def parse_date(cls, v):
        if v and v != '-':
            try:
                if '.' in v:
                    return datetime.strptime(v, '%d.%m.%Y').date().isoformat()
                return v
            except:
                raise ValueError('Неверный формат даты, ожидается дд.мм.гггг')
        return None

    @field_validator('phone', mode='before')
    @classmethod
    def validate_phone(cls, v):
        if v and v != '-':
            if not PHONE_RE.match(v):
                raise ValueError('Телефон должен начинаться с + и содержать 10-15 цифр')
        return v or '-'

class ResidentAdd(ResidentUpdate):
    room: str
    place: int

class ResidentMove(BaseModel):
    to_room: str
    to_place: int
    group_name: str = '-'
    full_name: str
    check_in: Optional[str] = None
    registration: Optional[str] = None
    phone: Optional[str] = '-'
    note: Optional[str] = '-'

    @field_validator('check_in', 'registration', mode='before')
    @classmethod
    def parse_date(cls, v):
        if v and v != '-':
            try:
                if '.' in v:
                    return datetime.strptime(v, '%d.%m.%Y').date().isoformat()
                return v
            except:
                raise ValueError('Неверный формат даты, ожидается дд.мм.гггг')
        return None

class SettingsUpdate(BaseModel):
    стирка: str
    госпошлина: str
    кпб_чистое: str
    кпб_грязное: str
    кпб_сдано: str
    кпб_принято: str

# ==================== СТАТИЧЕСКИЕ ФАЙЛЫ ====================
@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

@app.route('/static/css/style.css')
def serve_css():
    return send_from_directory('static/css', 'style.css')

@app.route('/static/js/app.js')
def serve_js():
    return send_from_directory('static/js', 'app.js')

@app.route('/manifest.json')
def manifest():
    return send_from_directory('.', 'manifest.json')

@app.route('/static/icons/<path:filename>')
def serve_icons(filename):
    return send_from_directory('static/icons', filename)

# ==================== API: ЖИЛЬЦЫ ====================
@app.route('/api/residents', methods=['GET'])
@require_auth
def get_residents():
    floor = request.args.get('floor', type=int)
    params = {"select": "*"}
    if floor is not None:
        params["floor"] = f"eq.{floor}"
    params["order"] = "room.asc,place.asc"
    
    response = supabase_request("GET", "residents", params=params)
    if response.status_code != 200:
        return jsonify({"error": "Ошибка загрузки"}), 500
    return jsonify(response.json())

@app.route('/api/residents/<int:resident_id>', methods=['GET'])
@require_auth
def get_resident(resident_id):
    params = {"select": "*", "id": f"eq.{resident_id}"}
    response = supabase_request("GET", "residents", params=params)
    if response.status_code != 200 or not response.json():
        return jsonify({"error": "Not found"}), 404
    return jsonify(response.json()[0])

@app.route('/api/residents/<int:resident_id>', methods=['PUT'])
@require_auth
def update_resident(resident_id):
    try:
        data = ResidentUpdate(**request.json)
    except ValidationError as e:
        return jsonify({'error': e.errors()}), 400

    if data.full_name != '(свободно)':
        params = {"select": "id", "full_name": f"eq.{data.full_name}", "id": f"neq.{resident_id}"}
        check = supabase_request("GET", "residents", params=params)
        if check.json():
            return jsonify({'error': 'Жилец с таким ФИО уже существует'}), 400

    update_data = {
        "group_name": data.group_name,
        "full_name": data.full_name,
        "check_in": data.check_in,
        "registration": data.registration,
        "phone": data.phone,
        "note": data.note,
        "updated_at": datetime.now().isoformat()
    }
    
    params = {"id": f"eq.{resident_id}"}
    response = supabase_request("PATCH", "residents", data=update_data, params=params)
    
    if response.status_code not in [200, 201, 204]:
        return jsonify({"error": f"Ошибка обновления: {response.status_code}"}), 500
    return jsonify({'status': 'success'})

@app.route('/api/residents', methods=['POST'])
@require_auth
def add_resident():
    try:
        data = ResidentAdd(**request.json)
    except ValidationError as e:
        return jsonify({'error': e.errors()}), 400

    params = {"select": "*", "room": f"eq.{data.room}", "place": f"eq.{data.place}"}
    existing = supabase_request("GET", "residents", params=params)
    if not existing.json():
        return jsonify({'error': 'Место не найдено'}), 404
    if existing.json()[0]['full_name'] != '(свободно)':
        return jsonify({'error': 'Место занято'}), 400

    if data.full_name != '(свободно)':
        params = {"select": "id", "full_name": f"eq.{data.full_name}"}
        check = supabase_request("GET", "residents", params=params)
        if check.json():
            return jsonify({'error': 'Жилец с таким ФИО уже заселён'}), 400

    update_data = {
        "group_name": data.group_name,
        "full_name": data.full_name,
        "check_in": data.check_in,
        "registration": data.registration,
        "phone": data.phone,
        "note": data.note,
        "updated_at": datetime.now().isoformat()
    }
    
    params = {"room": f"eq.{data.room}", "place": f"eq.{data.place}"}
    response = supabase_request("PATCH", "residents", data=update_data, params=params)
    if response.status_code not in [200, 201, 204]:
        return jsonify({"error": f"Ошибка заселения: {response.status_code}"}), 500
    return jsonify({'status': 'success'}), 201

@app.route('/api/residents/<int:resident_id>/move', methods=['POST'])
@require_auth
def move_resident(resident_id):
    try:
        data = ResidentMove(**request.json)
    except ValidationError as e:
        return jsonify({'error': e.errors()}), 400

    if data.full_name != '(свободно)':
        params = {"select": "id", "full_name": f"eq.{data.full_name}", "id": f"neq.{resident_id}"}
        check = supabase_request("GET", "residents", params=params)
        if check.json():
            return jsonify({'error': 'Жилец с таким ФИО уже существует'}), 400

    params = {"id": f"eq.{resident_id}"}
    supabase_request("PATCH", "residents", data={
        "group_name": "-",
        "full_name": "(свободно)",
        "check_in": None,
        "registration": None,
        "phone": "-",
        "note": "-"
    }, params=params)

    params = {"select": "*", "room": f"eq.{data.to_room}", "place": f"eq.{data.to_place}"}
    target = supabase_request("GET", "residents", params=params)
    if target.json() and target.json()[0]['full_name'] == '(свободно)':
        update_data = {
            "group_name": data.group_name,
            "full_name": data.full_name,
            "check_in": data.check_in,
            "registration": data.registration,
            "phone": data.phone,
            "note": data.note,
            "updated_at": datetime.now().isoformat()
        }
        params = {"room": f"eq.{data.to_room}", "place": f"eq.{data.to_place}"}
        supabase_request("PATCH", "residents", data=update_data, params=params)
        return jsonify({'status': 'success'})
    else:
        return jsonify({'error': 'Целевое место занято или не существует'}), 400

@app.route('/api/residents/<int:resident_id>', methods=['DELETE'])
@require_auth
def free_place(resident_id):
    params = {"id": f"eq.{resident_id}"}
    supabase_request("PATCH", "residents", data={
        "group_name": "-",
        "full_name": "(свободно)",
        "check_in": None,
        "registration": None,
        "phone": "-",
        "note": "-"
    }, params=params)
    return jsonify({'status': 'success'})

# ==================== API: НАСТРОЙКИ (ПРОСТОЙ СПОСОБ) ====================
@app.route('/api/settings', methods=['POST'])
@require_auth
def update_settings():
    try:
        data = SettingsUpdate(**request.json)
        print(f"Получены настройки: {data.model_dump()}")
    except ValidationError as e:
        return jsonify({'error': e.errors()}), 400

    # Сохраняем каждую настройку методом "удалить + вставить"
    for k, v in data.model_dump().items():
        print(f"Сохраняем {k} = {v}")
        
        # 1. Удаляем существующую запись
        delete_params = {"key": f"eq.{k}"}
        supabase_request("DELETE", "settings", params=delete_params)
        
        # 2. Вставляем новую
        supabase_request("POST", "settings", data={"key": k, "value": v})
    
    return jsonify({'status': 'success'})

@app.route('/api/settings', methods=['GET'])
@require_auth
def get_settings():
    params = {"select": "key,value"}
    response = supabase_request("GET", "settings", params=params)
    settings = {item['key']: item['value'] for item in response.json()}
    return jsonify(settings)

# ==================== API: ОТЧЁТЫ ====================
@app.route('/api/report', methods=['GET'])
@require_auth
def get_report():
    params = {"select": "*"}
    response = supabase_request("GET", "residents", params=params)
    residents = response.json()
    
    total = len(residents)
    occupied = len([r for r in residents if r['full_name'] != '(свободно)'])
    free = total - occupied
    load_percent = round((occupied / total) * 100, 1) if total > 0 else 0

    groups_data = {}
    for r in residents:
        if r['full_name'] != '(свободно)':
            groups_data[r['group_name']] = groups_data.get(r['group_name'], 0) + 1
    groups = [{'group_name': k, 'count': v} for k, v in groups_data.items()]
    groups.sort(key=lambda x: x['count'], reverse=True)

    params = {"select": "key,value"}
    settings_resp = supabase_request("GET", "settings", params=params)
    settings = {item['key']: item['value'] for item in settings_resp.json()}

    return jsonify({
        'total': total,
        'occupied': occupied,
        'free': free,
        'load_percent': load_percent,
        'groups': groups,
        'settings': settings,
        'date': datetime.now().strftime('%Y-%m-%d')
    })

@app.route('/api/groups', methods=['GET'])
@require_auth
def get_groups():
    params = {"select": "group_name", "group_name": "neq.-"}
    response = supabase_request("GET", "residents", params=params)
    groups = list(set(r['group_name'] for r in response.json()))
    groups.sort()
    return jsonify(groups)

@app.route('/api/free_places', methods=['GET'])
@require_auth
def get_free_places():
    floor = request.args.get('floor', type=int)
    params = {"select": "room,place,floor", "full_name": "eq.(свободно)"}
    if floor is not None:
        params["floor"] = f"eq.{floor}"
    params["order"] = "room.asc,place.asc"
    response = supabase_request("GET", "residents", params=params)
    return jsonify(response.json())

@app.route('/api/rooms', methods=['GET'])
@require_auth
def get_rooms():
    params = {"select": "room"}
    response = supabase_request("GET", "residents", params=params)
    rooms = list(set(r['room'] for r in response.json()))
    rooms.sort(key=lambda x: int(x) if x.isdigit() else 0)
    return jsonify(rooms)

@app.route('/api/floors', methods=['GET'])
@require_auth
def get_floors():
    params = {"select": "floor"}
    response = supabase_request("GET", "residents", params=params)
    floors = list(set(r['floor'] for r in response.json()))
    floors.sort()
    return jsonify(floors)

# ==================== ЭКСПОРТ ====================
# TXT-экспорт оставлен, HTML-экспорт удалён по запросу

@app.route('/api/export/txt', methods=['GET'])
def export_txt():
    token = request.args.get('token')
    if token not in (AUTH_TOKEN, GUEST_TOKEN):
        return jsonify({"error": "Unauthorized"}), 401
    
    params = {"select": "*", "order": "floor.asc,room.asc,place.asc"}
    residents = supabase_request("GET", "residents", params=params).json()

    lines = ["Этаж\tКомната\tГруппа\t№\tФИО\tДата заезда\tРегистрация\tТелефон\tПримечание"]
    for r in residents:
        lines.append(f"{r['floor']}\t{r['room']}\t{r['group_name']}\t{r['place']}\t{r['full_name']}\t{r['check_in'] or '-'}\t{r['registration'] or '-'}\t{r['phone']}\t{r['note']}")

    response = app.response_class(
        "\n".join(lines),
        mimetype='text/plain; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=export_hostel_data.txt'}
    )
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
