import os
import sqlite3
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# ==================== БАЗА ДАННЫХ ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data', 'hostel.db')
TXT_FILE_MAIN = os.path.join(BASE_DIR, 'новый 1.txt')
TXT_FILE_REPORT = os.path.join(BASE_DIR, 'новый 2.txt')

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
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
            UNIQUE(room, place)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
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
        print("⚠️ Файл новый 1.txt не найден. Пропускаю импорт.")
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
class ResidentUpdate(BaseModel):
    group_name: str
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
                return None
        return None

class ResidentAdd(ResidentUpdate):
    room: str
    place: int

class ResidentMove(BaseModel):
    from_id: int
    to_room: str
    to_place: int
    group_name: str
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
                return None
        return None

class SettingsUpdate(BaseModel):
    стирка: str
    госпошлина: str
    кпб_чистое: str
    кпб_грязное: str
    кпб_сдано: str
    кпб_принято: str

# ==================== API ЭНДПОИНТЫ (БЕЗ ПАРОЛЯ) ====================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/residents')
def get_residents():
    conn = get_db()
    residents = conn.execute('SELECT * FROM residents ORDER BY CAST(room AS INTEGER), place').fetchall()
    conn.close()
    return jsonify([dict(r) for r in residents])

@app.route('/api/resident/<int:resident_id>')
def get_resident(resident_id):
    conn = get_db()
    resident = conn.execute('SELECT * FROM residents WHERE id = ?', (resident_id,)).fetchone()
    conn.close()
    if resident:
        return jsonify(dict(resident))
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/resident/<int:resident_id>', methods=['PUT'])
def update_resident(resident_id):
    try:
        data = ResidentUpdate(**request.json)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

    conn = get_db()
    conn.execute('''
        UPDATE residents 
        SET group_name=?, full_name=?, check_in=?, registration=?, phone=?, note=?
        WHERE id=?
    ''', (data.group_name, data.full_name, data.check_in, data.registration, data.phone, data.note, resident_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/api/add', methods=['POST'])
def add_resident():
    try:
        data = ResidentAdd(**request.json)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

    conn = get_db()
    existing = conn.execute('SELECT * FROM residents WHERE room=? AND place=?', (data.room, data.place)).fetchone()
    if not existing:
        conn.close()
        return jsonify({'error': 'Место не найдено'}), 404
    if existing['full_name'] != '(свободно)':
        conn.close()
        return jsonify({'error': 'Место занято'}), 400

    conn.execute('''
        UPDATE residents 
        SET group_name=?, full_name=?, check_in=?, registration=?, phone=?, note=?
        WHERE room=? AND place=?
    ''', (data.group_name, data.full_name, data.check_in, data.registration, data.phone, data.note,
          data.room, data.place))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/api/move', methods=['POST'])
def move_resident():
    try:
        data = ResidentMove(**request.json)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

    conn = get_db()
    conn.execute('''
        UPDATE residents 
        SET group_name='-', full_name='(свободно)', check_in=NULL, registration=NULL, phone='-', note='-'
        WHERE id=?
    ''', (data.from_id,))

    target = conn.execute('SELECT * FROM residents WHERE room=? AND place=?', (data.to_room, data.to_place)).fetchone()
    if target and target['full_name'] == '(свободно)':
        conn.execute('''
            UPDATE residents 
            SET group_name=?, full_name=?, check_in=?, registration=?, phone=?, note=?
            WHERE room=? AND place=?
        ''', (data.group_name, data.full_name, data.check_in, data.registration, data.phone, data.note,
              data.to_room, data.to_place))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})
    else:
        conn.close()
        return jsonify({'error': 'Целевое место занято или не существует'}), 400

@app.route('/api/free', methods=['POST'])
def free_place():
    data = request.json
    conn = get_db()
    conn.execute('''
        UPDATE residents 
        SET group_name='-', full_name='(свободно)', check_in=NULL, registration=NULL, phone='-', note='-'
        WHERE id=?
    ''', (data['id'],))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/api/settings', methods=['POST'])
def update_settings():
    try:
        data = SettingsUpdate(**request.json)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

    conn = get_db()
    for k, v in data.model_dump().items():
        conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (k, v))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/api/settings')
def get_settings():
    conn = get_db()
    settings = conn.execute('SELECT key, value FROM settings').fetchall()
    conn.close()
    return jsonify({s['key']: s['value'] for s in settings})

@app.route('/api/report')
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

@app.route('/api/groups')
def get_groups():
    conn = get_db()
    groups = conn.execute('SELECT DISTINCT group_name FROM residents WHERE group_name != "-" ORDER BY group_name').fetchall()
    conn.close()
    return jsonify([g['group_name'] for g in groups])

@app.route('/api/free_places')
def get_free_places():
    conn = get_db()
    places = conn.execute('''
        SELECT room, place, floor FROM residents WHERE full_name = "(свободно)" ORDER BY CAST(room AS INTEGER), place
    ''').fetchall()
    conn.close()
    return jsonify([dict(p) for p in places])

@app.route('/api/rooms')
def get_rooms():
    conn = get_db()
    rooms = conn.execute('SELECT DISTINCT room FROM residents ORDER BY CAST(room AS INTEGER)').fetchall()
    conn.close()
    return jsonify([r['room'] for r in rooms])

# ==================== PWA ====================
@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json')

@app.route('/sw.js')
def service_worker():
    return send_from_directory('static/js', 'sw.js', mimetype='application/javascript')

@app.route('/static/<path:path>')
def static_files(path):
    return send_from_directory('static', path)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)