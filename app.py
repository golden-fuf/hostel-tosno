import os
import re
from datetime import datetime
from typing import Optional
from functools import wraps
from pydantic import BaseModel, field_validator, ValidationError
from flask import Flask, request, jsonify, send_from_directory, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app, resources={r"/api/*": {"origins": os.getenv("CORS_ORIGINS", "*").split(",")}})

# ==================== ПОДКЛЮЧЕНИЕ К SUPABASE ====================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
from supabase import create_client, Client(SUPABASE_URL, SUPABASE_KEY)

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

# ==================== API ЭНДПОИНТЫ ====================
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

# ----- Жильцы -----
@app.route('/api/residents', methods=['GET'])
@require_auth
def get_residents():
    floor = request.args.get('floor', type=int)
    query = supabase.table('residents').select('*')
    if floor is not None:
        query = query.eq('floor', floor)
    query = query.order('room', desc=False).order('place', desc=False)
    response = query.execute()
    return jsonify(response.data)

@app.route('/api/residents/<int:resident_id>', methods=['GET'])
@require_auth
def get_resident(resident_id):
    response = supabase.table('residents').select('*').eq('id', resident_id).execute()
    if response.data:
        return jsonify(response.data[0])
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/residents/<int:resident_id>', methods=['PUT'])
@require_auth
def update_resident(resident_id):
    try:
        data = ResidentUpdate(**request.json)
    except ValidationError as e:
        return jsonify({'error': e.errors()}), 400

    if data.full_name != '(свободно)':
        check = supabase.table('residents').select('id').eq('full_name', data.full_name).neq('id', resident_id).execute()
        if check.data:
            return jsonify({'error': 'Жилец с таким ФИО уже существует'}), 400

    response = supabase.table('residents').update({
        'group_name': data.group_name,
        'full_name': data.full_name,
        'check_in': data.check_in,
        'registration': data.registration,
        'phone': data.phone,
        'note': data.note,
        'updated_at': datetime.now().isoformat()
    }).eq('id', resident_id).execute()
    
    return jsonify({'status': 'success'})

@app.route('/api/residents', methods=['POST'])
@require_auth
def add_resident():
    try:
        data = ResidentAdd(**request.json)
    except ValidationError as e:
        return jsonify({'error': e.errors()}), 400

    # Проверка существования места
    existing = supabase.table('residents').select('*').eq('room', data.room).eq('place', data.place).execute()
    if not existing.data:
        return jsonify({'error': 'Место не найдено'}), 404
    if existing.data[0]['full_name'] != '(свободно)':
        return jsonify({'error': 'Место занято'}), 400

    if data.full_name != '(свободно)':
        check = supabase.table('residents').select('id').eq('full_name', data.full_name).execute()
        if check.data:
            return jsonify({'error': 'Жилец с таким ФИО уже заселён'}), 400

    response = supabase.table('residents').update({
        'group_name': data.group_name,
        'full_name': data.full_name,
        'check_in': data.check_in,
        'registration': data.registration,
        'phone': data.phone,
        'note': data.note,
        'updated_at': datetime.now().isoformat()
    }).eq('room', data.room).eq('place', data.place).execute()
    
    return jsonify({'status': 'success'}), 201

@app.route('/api/residents/<int:resident_id>/move', methods=['POST'])
@require_auth
def move_resident(resident_id):
    try:
        data = ResidentMove(**request.json)
    except ValidationError as e:
        return jsonify({'error': e.errors()}), 400

    if data.full_name != '(свободно)':
        check = supabase.table('residents').select('id').eq('full_name', data.full_name).neq('id', resident_id).execute()
        if check.data:
            return jsonify({'error': 'Жилец с таким ФИО уже существует'}), 400

    # Освобождаем старое место
    supabase.table('residents').update({
        'group_name': '-',
        'full_name': '(свободно)',
        'check_in': None,
        'registration': None,
        'phone': '-',
        'note': '-'
    }).eq('id', resident_id).execute()

    # Проверяем новое место
    target = supabase.table('residents').select('*').eq('room', data.to_room).eq('place', data.to_place).execute()
    if target.data and target.data[0]['full_name'] == '(свободно)':
        supabase.table('residents').update({
            'group_name': data.group_name,
            'full_name': data.full_name,
            'check_in': data.check_in,
            'registration': data.registration,
            'phone': data.phone,
            'note': data.note,
            'updated_at': datetime.now().isoformat()
        }).eq('room', data.to_room).eq('place', data.to_place).execute()
        return jsonify({'status': 'success'})
    else:
        return jsonify({'error': 'Целевое место занято или не существует'}), 400

@app.route('/api/residents/<int:resident_id>', methods=['DELETE'])
@require_auth
def free_place(resident_id):
    supabase.table('residents').update({
        'group_name': '-',
        'full_name': '(свободно)',
        'check_in': None,
        'registration': None,
        'phone': '-',
        'note': '-'
    }).eq('id', resident_id).execute()
    return jsonify({'status': 'success'})

# ----- Настройки -----
@app.route('/api/settings', methods=['POST'])
@require_auth
def update_settings():
    try:
        data = SettingsUpdate(**request.json)
    except ValidationError as e:
        return jsonify({'error': e.errors()}), 400

    for k, v in data.model_dump().items():
        supabase.table('settings').upsert({'key': k, 'value': v}).execute()
    return jsonify({'status': 'success'})

@app.route('/api/settings', methods=['GET'])
@require_auth
def get_settings():
    response = supabase.table('settings').select('key, value').execute()
    settings = {item['key']: item['value'] for item in response.data}
    return jsonify(settings)

# ----- Отчёты -----
@app.route('/api/report', methods=['GET'])
@require_auth
def get_report():
    residents = supabase.table('residents').select('*').execute().data
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

    settings_resp = supabase.table('settings').select('key, value').execute()
    settings = {item['key']: item['value'] for item in settings_resp.data}

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
    residents = supabase.table('residents').select('group_name').neq('group_name', '-').execute().data
    groups = list(set(r['group_name'] for r in residents))
    groups.sort()
    return jsonify(groups)

@app.route('/api/free_places', methods=['GET'])
@require_auth
def get_free_places():
    floor = request.args.get('floor', type=int)
    query = supabase.table('residents').select('room, place, floor').eq('full_name', '(свободно)')
    if floor is not None:
        query = query.eq('floor', floor)
    query = query.order('room', desc=False).order('place', desc=False)
    response = query.execute()
    return jsonify(response.data)

@app.route('/api/rooms', methods=['GET'])
@require_auth
def get_rooms():
    response = supabase.table('residents').select('room').execute()
    rooms = list(set(r['room'] for r in response.data))
    rooms.sort(key=lambda x: int(x) if x.isdigit() else 0)
    return jsonify(rooms)

@app.route('/api/floors', methods=['GET'])
@require_auth
def get_floors():
    response = supabase.table('residents').select('floor').execute()
    floors = list(set(r['floor'] for r in response.data))
    floors.sort()
    return jsonify(floors)

# ==================== ЭКСПОРТ ====================
@app.route('/api/export/html', methods=['GET'])
def export_html():
    token = request.args.get('token')
    if token != AUTH_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401
    
    residents = supabase.table('residents').select('*').order('floor', desc=False).order('room', desc=False).execute().data
    total = len(residents)
    occupied = len([r for r in residents if r['full_name'] != '(свободно)'])
    
    settings_resp = supabase.table('settings').select('key, value').execute()
    settings = {item['key']: item['value'] for item in settings_resp.data}

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
    
    residents = supabase.table('residents').select('*').order('floor', desc=False).order('room', desc=False).execute().data

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
