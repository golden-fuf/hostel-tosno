import os
import re
import sqlite3
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

# ==================== БАЗА ДАННЫХ ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data', 'hostel.db')
TXT_FILE_MAIN = os.path.join(BASE_DIR, 'новый 1.txt')

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS residents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            floor INTEGER NOT NULL,
            room TEXT NOT NULL,
            group_name TEXT DEFAULT '-',
            place INTEGER NOT NULL,
            full_name TEXT DEFAULT '(свободно)',
            check_in TEXT DEFAULT NULL,
            registration TEXT DEFAULT NULL,
            phone TEXT DEFAULT '-',
            note TEXT DEFAULT '-',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(room, place)
        );
        CREATE INDEX IF NOT EXISTS idx_residents_room ON residents(room);
        CREATE INDEX IF NOT EXISTS idx_residents_name ON residents(full_name);
        CREATE INDEX IF NOT EXISTS idx_residents_group ON residents(group_name);

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER,
            action TEXT,
            old_data TEXT,
            new_data TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    default_settings = {
        'стирка': '400', 'госпошлина': '2000',
        'кпб_чистое': '10', 'кпб_грязное': '4',
        'кпб_сдано': '0', 'кпб_принято': '0'
    }
    for k, v in default_settings.items():
        conn.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (k, v))

    if conn.execute('SELECT COUNT(*) as cnt FROM residents').fetchone()['cnt'] == 0:
        imported = import_data(conn)
        if not imported:
            print("Файлы не найдены или пусты, создаю тестовые данные...")
            create_test_data(conn)

    conn.commit()
    conn.close()

def import_data(conn):
    if not os.path.exists(TXT_FILE_MAIN):
        print(f"❌ Файл не найден: {TXT_FILE_MAIN}")
        return False

    print(f"✅ Найден файл: {TXT_FILE_MAIN}, начинаю импорт...")
    try:
        with open(TXT_FILE_MAIN, 'r', encoding='utf-8') as f:
            lines = f.read().strip().split('\n')
            for line in lines[1:]:
                parts = line.split('\t')
                if len(parts) >= 5:
                    check_in = parts[5] if len(parts) > 5 and parts[5] != '-' else None
                    registration = parts[6] if len(parts) > 6 and parts[6] != '-' else None

                    if check_in:
                        try:
                            check_in = datetime.strptime(check_in, '%d.%m.%Y').date().isoformat()
                        except:
                            check_in = None
                    if registration:
                        try:
                            registration = datetime.strptime(registration, '%d.%m.%Y').date().isoformat()
                        except:
                            registration = None

                    conn.execute('''
                        INSERT OR REPLACE INTO residents 
                        (floor, room, group_name, place, full_name, check_in, registration, phone, note)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (int(parts[0]), parts[1], parts[2], int(parts[3]), parts[4],
                          check_in, registration, parts[7] if len(parts) > 7 else '-',
                          parts[8] if len(parts) > 8 else '-'))
        print("✅ Импорт завершён.")
        return True
    except Exception as e:
        print(f"❌ ОШИБКА импорта: {e}")
        return False

def create_test_data(conn):
    test_data = [
        (1, '1', 'Индусы', 1, 'Мохд Джамин', None, None, '-', '-'),
        (1, '1', 'Индусы', 2, 'Шаурма Каран', None, None, '-', '-'),
    ]
    for data in test_data:
        conn.execute('''
            INSERT OR REPLACE INTO residents 
            (floor, room, group_name, place, full_name, check_in, registration, phone, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', data)
    conn.commit()

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

@app.route('/manifest.json')
def manifest():
    return send_from_directory('.', 'manifest.json')

@app.route('/static/css/style.css')
def serve_css():
    return send_from_directory('static/css', 'style.css')

@app.route('/static/js/app.js')
def serve_js():
    return send_from_directory('static/js', 'app.js')

@app.route('/static/icons/<path:filename>')
def serve_icons(filename):
    return send_from_directory('static/icons', filename)

# ----- Жильцы -----
@app.route('/api/residents', methods=['GET'])
@require_auth
def get_residents():
    floor = request.args.get('floor', type=int)
    conn = get_db()
    query = 'SELECT * FROM residents WHERE 1=1'
    params = []
    if floor is not None:
        query += ' AND floor = ?'
        params.append(floor)
    query += ' ORDER BY CAST(room AS INTEGER), place'
    residents = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in residents])

@app.route('/api/residents/<int:resident_id>', methods=['GET'])
@require_auth
def get_resident(resident_id):
    conn = get_db()
    resident = conn.execute('SELECT * FROM residents WHERE id = ?', (resident_id,)).fetchone()
    conn.close()
    if resident:
        return jsonify(dict(resident))
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/residents/<int:resident_id>', methods=['PUT'])
@require_auth
def update_resident(resident_id):
    try:
        data = ResidentUpdate(**request.json)
    except ValidationError as e:
        return jsonify({'error': e.errors()}), 400

    conn = get_db()
    if data.full_name != '(свободно)':
        existing = conn.execute('SELECT id FROM residents WHERE full_name = ? AND id != ?', 
                               (data.full_name, resident_id)).fetchone()
        if existing:
            conn.close()
            return jsonify({'error': 'Жилец с таким ФИО уже существует'}), 400

    conn.execute('''
        UPDATE residents 
        SET group_name=?, full_name=?, check_in=?, registration=?, phone=?, note=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    ''', (data.group_name, data.full_name, data.check_in, data.registration, data.phone, data.note, resident_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/api/residents', methods=['POST'])
@require_auth
def add_resident():
    try:
        data = ResidentAdd(**request.json)
    except ValidationError as e:
        return jsonify({'error': e.errors()}), 400

    conn = get_db()
    existing = conn.execute('SELECT * FROM residents WHERE room=? AND place=?', (data.room, data.place)).fetchone()
    if not existing:
        conn.close()
        return jsonify({'error': 'Место не найдено'}), 404
    if existing['full_name'] != '(свободно)':
        conn.close()
        return jsonify({'error': 'Место занято'}), 400

    if data.full_name != '(свободно)':
        dup = conn.execute('SELECT id FROM residents WHERE full_name = ?', (data.full_name,)).fetchone()
        if dup:
            conn.close()
            return jsonify({'error': 'Жилец с таким ФИО уже заселён'}), 400

    conn.execute('''
        UPDATE residents 
        SET group_name=?, full_name=?, check_in=?, registration=?, phone=?, note=?, updated_at=CURRENT_TIMESTAMP
        WHERE room=? AND place=?
    ''', (data.group_name, data.full_name, data.check_in, data.registration, data.phone, data.note,
          data.room, data.place))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'}), 201

@app.route('/api/residents/<int:resident_id>/move', methods=['POST'])
@require_auth
def move_resident(resident_id):
    try:
        data = ResidentMove(**request.json)
    except ValidationError as e:
        return jsonify({'error': e.errors()}), 400

    conn = get_db()
    if data.full_name != '(свободно)':
        dup = conn.execute('SELECT id FROM residents WHERE full_name = ? AND id != ?', 
                          (data.full_name, resident_id)).fetchone()
        if dup:
            conn.close()
            return jsonify({'error': 'Жилец с таким ФИО уже существует'}), 400

    conn.execute('''
        UPDATE residents 
        SET group_name='-', full_name='(свободно)', check_in=NULL, registration=NULL, phone='-', note='-', updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    ''', (resident_id,))

    target = conn.execute('SELECT * FROM residents WHERE room=? AND place=?', (data.to_room, data.to_place)).fetchone()
    if target and target['full_name'] == '(свободно)':
        conn.execute('''
            UPDATE residents 
            SET group_name=?, full_name=?, check_in=?, registration=?, phone=?, note=?, updated_at=CURRENT_TIMESTAMP
            WHERE room=? AND place=?
        ''', (data.group_name, data.full_name, data.check_in, data.registration, data.phone, data.note,
              data.to_room, data.to_place))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})
    else:
        conn.close()
        return jsonify({'error': 'Целевое место занято или не существует'}), 400

@app.route('/api/residents/<int:resident_id>', methods=['DELETE'])
@require_auth
def free_place(resident_id):
    conn = get_db()
    conn.execute('''
        UPDATE residents 
        SET group_name='-', full_name='(свободно)', check_in=NULL, registration=NULL, phone='-', note='-', updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    ''', (resident_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

# ----- Настройки -----
@app.route('/api/settings', methods=['POST'])
@require_auth
def update_settings():
    try:
        data = SettingsUpdate(**request.json)
    except ValidationError as e:
        return jsonify({'error': e.errors()}), 400

    conn = get_db()
    for k, v in data.model_dump().items():
        conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (k, v))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/api/settings', methods=['GET'])
@require_auth
def get_settings():
    conn = get_db()
    settings = conn.execute('SELECT key, value FROM settings').fetchall()
    conn.close()
    return jsonify({s['key']: s['value'] for s in settings})

# ----- Отчёты -----
@app.route('/api/report', methods=['GET'])
@require_auth
def get_report():
    conn = get_db()
    total = conn.execute('SELECT COUNT(*) as count FROM residents').fetchone()['count']
    occupied = conn.execute('SELECT COUNT(*) as count FROM residents WHERE full_name != "(свободно)"').fetchone()['count']
    free = total - occupied
    load_percent = round((occupied / total) * 100, 1) if total > 0 else 0

    groups = conn.execute('''
        SELECT group_name, COUNT(*) as count 
        FROM residents WHERE full_name != "(свободно)" GROUP BY group_name ORDER BY count DESC
    ''').fetchall()

    settings = conn.execute('SELECT key, value FROM settings').fetchall()
    settings_dict = {s['key']: s['value'] for s in settings}

    conn.close()
    return jsonify({
        'total': total, 'occupied': occupied, 'free': free, 'load_percent': load_percent,
        'groups': [dict(g) for g in groups],
        'settings': settings_dict,
        'date': datetime.now().strftime('%Y-%m-%d')
    })

@app.route('/api/groups', methods=['GET'])
@require_auth
def get_groups():
    conn = get_db()
    groups = conn.execute('SELECT DISTINCT group_name FROM residents WHERE group_name != "-" ORDER BY group_name').fetchall()
    conn.close()
    return jsonify([g['group_name'] for g in groups])

@app.route('/api/free_places', methods=['GET'])
@require_auth
def get_free_places():
    floor = request.args.get('floor', type=int)
    conn = get_db()
    query = 'SELECT room, place, floor FROM residents WHERE full_name = "(свободно)"'
    params = []
    if floor is not None:
        query += ' AND floor = ?'
        params.append(floor)
    query += ' ORDER BY CAST(room AS INTEGER), place'
    places = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(p) for p in places])

@app.route('/api/rooms', methods=['GET'])
@require_auth
def get_rooms():
    conn = get_db()
    rooms = conn.execute('SELECT DISTINCT room FROM residents ORDER BY CAST(room AS INTEGER)').fetchall()
    conn.close()
    return jsonify([r['room'] for r in rooms])

@app.route('/api/floors', methods=['GET'])
@require_auth
def get_floors():
    conn = get_db()
    floors = conn.execute('SELECT DISTINCT floor FROM residents ORDER BY floor').fetchall()
    conn.close()
    return jsonify([f['floor'] for f in floors])

# ==================== ЭКСПОРТ ====================
@app.route('/api/export/html', methods=['GET'])
def export_html():
    token = request.args.get('token')
    if token != AUTH_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401
    
    conn = get_db()
    residents = conn.execute('''
        SELECT floor, room, group_name, place, full_name, 
               IFNULL(check_in, '-') as check_in, 
               IFNULL(registration, '-') as registration, 
               phone, note
        FROM residents 
        ORDER BY floor, CAST(room AS INTEGER), place
    ''').fetchall()
    
    total = conn.execute('SELECT COUNT(*) as count FROM residents').fetchone()['count']
    occupied = conn.execute('SELECT COUNT(*) as count FROM residents WHERE full_name != "(свободно)"').fetchone()['count']
    
    settings_rows = conn.execute('SELECT key, value FROM settings').fetchall()
    settings = {row['key']: row['value'] for row in settings_rows}
    conn.close()

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
                        <td>{{ r.check_in }}</td><td>{{ r.registration }}</td>
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
    
    conn = get_db()
    residents = conn.execute('''
        SELECT floor, room, group_name, place, full_name, 
               IFNULL(check_in, '-') as check_in, 
               IFNULL(registration, '-') as registration, 
               phone, note
        FROM residents 
        ORDER BY floor, CAST(room AS INTEGER), place
    ''').fetchall()
    conn.close()

    lines = ["Этаж\tКомната\tГруппа\t№\tФИО\tДата заезда\tРегистрация\tТелефон\tПримечание"]
    for r in residents:
        lines.append(f"{r['floor']}\t{r['room']}\t{r['group_name']}\t{r['place']}\t{r['full_name']}\t{r['check_in']}\t{r['registration']}\t{r['phone']}\t{r['note']}")

    response = app.response_class(
        "\n".join(lines),
        mimetype='text/plain; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=export_hostel_data.txt'}
    )
    return response

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
