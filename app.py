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

# ==================== ЛОГИРОВАНИЕ ====================
def log(msg):
    """Простое логирование в stdout (видно в логах Vercel)"""
    print(f"[LOG] {msg}")

def log_error(msg):
    """Логирование ошибок"""
    print(f"[ERROR] {msg}")

# ==================== ЗАПРОСЫ К SUPABASE ====================
def supabase_request(method, endpoint, data=None, params=None):
    """Универсальная функция для запросов к Supabase"""
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    log(f"🔹 {method} {endpoint}")
    if data:
        log(f"   Data: {data}")
    if params:
        log(f"   Params: {params}")
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, params=params)
        else:
            response = requests.request(method, url, headers=headers, json=data, params=params)
        
        log(f"   Status: {response.status_code}")
        if response.status_code >= 400:
            log_error(f"   Error: {response.text[:500]}")
        
        return response
    except Exception as e:
        log_error(f"   Exception: {str(e)}")
        raise

# ==================== АУТЕНТИФИКАЦИЯ ====================
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "hostel-secret-2026")

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-Auth-Token", "")
        if token != AUTH_TOKEN:
            return jsonify({"error": "Unauthorized"}), 401
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

# ==================== API: НАСТРОЙКИ (С ПОДРОБНЫМ ЛОГИРОВАНИЕМ) ====================
@app.route('/api/settings', methods=['POST'])
@require_auth
def update_settings():
    """Сохранение настроек с полным логированием"""
    try:
        data = SettingsUpdate(**request.json)
        log(f"✅ Получены настройки: {data.model_dump()}")
    except ValidationError as e:
        log_error(f"❌ Ошибка валидации: {e.errors()}")
        return jsonify({'error': e.errors()}), 400

    # Сохраняем каждую настройку по отдельности
    results = {}
    for k, v in data.model_dump().items():
        log(f"💾 Сохраняем {k} = {v}")
        
        try:
            # Используем POST с on_conflict для upsert
            params = {"on_conflict": "key"}
            response = supabase_request("POST", "settings", data={"key": k, "value": v}, params=params)
            
            # ПРИНУДИТЕЛЬНО ЛОГИРУЕМ ОТВЕТ
            log(f"📡 Ответ от Supabase: статус {response.status_code}")
            log(f"📄 Тело ответа: {response.text[:300]}")
            
            results[k] = response.status_code
            
            if response.status_code not in [200, 201, 204]:
                log_error(f"❌ Ошибка сохранения {k}: статус {response.status_code}")
                log_error(f"   Ответ: {response.text[:500]}")
                return jsonify({
                    "error": f"Ошибка сохранения {k}", 
                    "status": response.status_code,
                    "detail": response.text[:200]
                }), 500
            else:
                log(f"✅ {k} сохранено успешно")
                
        except Exception as e:
            log_error(f"❌ Исключение при сохранении {k}: {str(e)}")
            return jsonify({"error": f"Исключение при сохранении {k}", "detail": str(e)}), 500
    
    log(f"✅ Все настройки сохранены: {results}")
    return jsonify({'status': 'success', 'results': results})

@app.route('/api/settings', methods=['GET'])
@require_auth
def get_settings():
    """Загрузка настроек"""
    log("🔹 GET settings")
    params = {"select": "key,value"}
    response = supabase_request("GET", "settings", params=params)
    
    if response.status_code != 200:
        log_error(f"❌ Ошибка загрузки настроек: {response.status_code}")
        return jsonify({"error": "Ошибка загрузки настроек"}), 500
    
    settings = {item['key']: item['value'] for item in response.json()}
    log(f"✅ Загружены настройки: {settings}")
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

# ==================== API: ВСПОМОГАТЕЛЬНЫЕ ====================
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
@app.route('/api/export/html', methods=['GET'])
def export_html():
    token = request.args.get('token')
    if token != AUTH_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401
    
    params = {"select": "*", "order": "floor.asc,room.asc,place.asc"}
    residents = supabase_request("GET", "residents", params=params).json()
    total = len(residents)
    occupied = len([r for r in residents if r['full_name'] != '(свободно)'])
    
    params = {"select": "key,value"}
    settings_resp = supabase_request("GET", "settings", params=params)
    settings = {item['key']: item['value'] for item in settings_resp.json()}

    html_template = '''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Отчёт по хостелу</title>
        <script>window.onload = function() { window.print(); };</script>
        <style>
            body { font-family: -apple-system, sans-serif; margin: 20px; background: #f5f5f5; color: #333; }
            .header { background: #2d7d46; color: white; padding: 15px 20px; border-radius: 8px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
            .header h2 { margin: 0; font-size: 22px; }
            .header .date { font-size: 14px; opacity: 0.9; }
            .stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 20px; }
            .stat-box { background: white; padding: 12px 16px; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); text-align: center; }
            .stat-box .num { font-size: 24px; font-weight: 700; color: #2d7d46; }
            .stat-box .label { font-size: 13px; color: #666; margin-top: 4px; }
            .section-title { font-size: 18px; font-weight: 600; color: #2d7d46; margin: 20px 0 10px 0; border-bottom: 2px solid #2d7d46; padding-bottom: 4px; }
            .settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 15px; }
            .setting-item { background: white; padding: 10px 14px; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); display: flex; justify-content: space-between; }
            .setting-item .label { color: #666; font-size: 14px; }
            .setting-item .value { font-weight: 600; font-size: 14px; }
            .table-wrapper { overflow-x: auto; background: white; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
            table { width: 100%; border-collapse: collapse; font-size: 14px; }
            th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid #eee; white-space: nowrap; }
            th { background: #2d7d46; color: white; font-weight: 600; }
            .free { color: #999; font-style: italic; }
            .free td { background: #fafafa; }
            @media print { 
                body { background: white; margin: 0; padding: 10px; } 
                th { background: #2d7d46 !important; color: white !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
                .header { background: #2d7d46 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
                .stat-box, .setting-item { box-shadow: none; border: 1px solid #ddd; }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h2>🏠 Отчёт по хостелу "Тосно"</h2>
            <span class="date">{{ date }}</span>
        </div>
        <div class="stats-grid">
            <div class="stat-box"><div class="num">{{ total }}</div><div class="label">Всего мест</div></div>
            <div class="stat-box"><div class="num" style="color:#2d7d46;">{{ occupied }}</div><div class="label">Заселено</div></div>
            <div class="stat-box"><div class="num" style="color:#d9534f;">{{ total - occupied }}</div><div class="label">Свободно</div></div>
            <div class="stat-box"><div class="num">{{ (occupied / total * 100) | round(1) }}%</div><div class="label">Загрузка</div></div>
        </div>
        <div class="section-title">💰 Финансы и склад</div>
        <div class="settings-grid">
            <div class="setting-item"><span class="label">Стирка</span><span class="value">{{ settings.стирка }} ₽</span></div>
            <div class="setting-item"><span class="label">Госпошлина</span><span class="value">{{ settings.госпошлина }} ₽</span></div>
            <div class="setting-item"><span class="label">Чистое КПБ</span><span class="value">{{ settings.кпб_чистое }}</span></div>
            <div class="setting-item"><span class="label">Грязное КПБ</span><span class="value">{{ settings.кпб_грязное }}</span></div>
            <div class="setting-item"><span class="label">Сдано КПБ</span><span class="value">{{ settings.кпб_сдано }}</span></div>
            <div class="setting-item"><span class="label">Принято КПБ</span><span class="value">{{ settings.кпб_принято }}</span></div>
        </div>
        <div class="section-title">👥 Список жильцов</div>
        <div class="table-wrapper">
            <table>
                <thead><tr><th>Этаж</th><th>Комната</th><th>Место</th><th>Группа</th><th>ФИО</th><th>Заезд</th><th>Регистрация</th><th>Телефон</th><th>Примечание</th></tr></thead>
                <tbody>
                    {% for r in residents %}
                    <tr class="{% if r.full_name == '(свободно)' %}free{% endif %}">
                        <td>{{ r.floor }}</td><td>{{ r.room }}</td><td>{{ r.place }}</td>
                        <td>{{ r.group_name }}</td><td>{{ r.full_name }}</td>
                        <td>{{ r.check_in or '-' }}</td><td>{{ r.registration or '-' }}</td>
                        <td>{{ r.phone }}</td><td>{{ r.note }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    '''
    return render_template_string(html_template, 
                                  residents=residents, 
                                  total=total, 
                                  occupied=occupied, 
                                  settings=settings,
                                  date=datetime.now().strftime('%d.%m.%Y %H:%M'))

@app.route('/api/export/txt', methods=['GET'])
def export_txt():
    token = request.args.get('token')
    if token != AUTH_TOKEN:
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

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
