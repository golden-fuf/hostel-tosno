// ==================== СОСТОЯНИЕ ====================
let allResidents = [];
let filteredResidents = [];
let currentFilter = 'all';
let searchQuery = '';

// ==================== АВТОРИЗАЦИЯ ====================
const AUTH_HEADERS = {
    'X-API-Key': '1488'
};

// ==================== ИНИЦИАЛИЗАЦИЯ ====================
document.addEventListener('DOMContentLoaded', () => {
    loadData();
    updateStats();
    
    const searchInput = document.getElementById('searchInput');
    const clearBtn = document.querySelector('.btn-clear');
    
    searchInput.addEventListener('input', () => {
        clearBtn.classList.toggle('visible', searchInput.value.length > 0);
        filterResidents();
    });
});

// ==================== ЗАГРУЗКА ДАННЫХ ====================
async function loadData() {
    try {
        const response = await fetch('/api/residents', { headers: AUTH_HEADERS });
        if (!response.ok) throw new Error('Ошибка загрузки');
        allResidents = await response.json();
        filteredResidents = [...allResidents];
        renderRooms();
        updateStats();
    } catch (error) {
        console.error(error);
        showToast('❌ Ошибка загрузки данных');
    }
}

async function updateStats() {
    try {
        const response = await fetch('/api/report', { headers: AUTH_HEADERS });
        if (!response.ok) throw new Error('Ошибка статистики');
        const data = await response.json();
        
        document.getElementById('totalCount').textContent = data.total || 0;
        document.getElementById('occupiedCount').textContent = data.occupied || 0;
        document.getElementById('freeCount').textContent = data.free || 0;
        document.getElementById('loadPercent').textContent = (data.load_percent || 0) + '%';
    } catch (error) {
        console.error('Ошибка обновления статистики:', error);
    }
}

// ==================== ФОРМАТИРОВАНИЕ ДАТ ====================
function formatDate(isoDate) {
    if (!isoDate || isoDate === '-') return '-';
    try {
        const d = new Date(isoDate + 'T00:00:00');
        if (isNaN(d.getTime())) return isoDate;
        return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
    } catch {
        return isoDate;
    }
}

// ==================== ФИЛЬТРАЦИЯ ====================
function filterResidents() {
    searchQuery = document.getElementById('searchInput').value.toLowerCase().trim();
    applyFilters();
}

function filterByGroup(group) {
    currentFilter = group;
    document.querySelectorAll('.filter-tab').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.group === group);
    });
    applyFilters();
}

function clearSearch() {
    document.getElementById('searchInput').value = '';
    document.querySelector('.btn-clear').classList.remove('visible');
    filterResidents();
}

function applyFilters() {
    let filtered = [...allResidents];
    
    if (searchQuery) {
        filtered = filtered.filter(r => {
            const searchStr = `${r.full_name} ${r.room} ${r.group_name} ${r.phone} ${r.note}`.toLowerCase();
            return searchStr.includes(searchQuery);
        });
    }
    
    if (currentFilter === 'occupied') {
        filtered = filtered.filter(r => r.full_name !== '(свободно)');
    } else if (currentFilter === 'free') {
        filtered = filtered.filter(r => r.full_name === '(свободно)');
    }
    
    filteredResidents = filtered;
    renderRooms();
}

// ==================== ОТОБРАЖЕНИЕ КОМНАТ ====================
function renderRooms() {
    const container = document.getElementById('roomsContainer');
    
    if (!filteredResidents || filteredResidents.length === 0) {
        container.innerHTML = `
            <div style="text-align:center;padding:40px;color:#666;">
                <div style="font-size:48px;margin-bottom:16px;">🔍</div>
                <div>Ничего не найдено</div>
            </div>
        `;
        return;
    }
    
    const rooms = {};
    filteredResidents.forEach(r => {
        if (!rooms[r.room]) rooms[r.room] = [];
        rooms[r.room].push(r);
    });
    
    const roomCapacities = {};
    allResidents.forEach(r => {
        if (!roomCapacities[r.room]) roomCapacities[r.room] = [];
        if (!roomCapacities[r.room].includes(r.place)) {
            roomCapacities[r.room].push(r.place);
        }
    });
    
    const sortedRooms = Object.keys(rooms).sort((a, b) => parseInt(a) - parseInt(b));
    let html = '';
    
    sortedRooms.forEach(room => {
        const residents = rooms[room];
        const totalPlaces = roomCapacities[room]?.length || residents.length;
        const occupied = residents.filter(r => r.full_name !== '(свободно)').length;
        const free = totalPlaces - occupied;
        const isFree = occupied === 0;
        
        html += `
            <div class="room-card ${isFree ? 'free-room' : ''}">
                <div class="room-header">
                    <span class="room-name">🏠 Комната ${room}</span>
                    <span class="room-stats">
                        👥 ${occupied} / ${totalPlaces} · 
                        <span class="occupied-badge">🟢 ${occupied}</span> · 
                        <span class="free-badge">🔴 ${free}</span>
                    </span>
                </div>
                <div class="residents-list">
        `;
        
        residents.sort((a, b) => a.place - b.place);
        
        residents.forEach(r => {
            const isFreePlace = r.full_name === '(свободно)';
            html += `
                <div class="resident-item" onclick="${isFreePlace ? `showAddFormToRoom('${r.room}', ${r.place})` : `editResident(${r.id})`}">
                    <span class="resident-place">${r.place}</span>
                    <div class="resident-info">
                        <div class="resident-name ${isFreePlace ? 'free' : ''}">
                            ${isFreePlace ? '🟢 свободно' : r.full_name}
                        </div>
                        ${!isFreePlace ? `
                            <div class="resident-details">
                                <span class="resident-group">${r.group_name}</span>
                                <span>📅 ${formatDate(r.check_in)}</span>
                                ${r.phone && r.phone !== '-' ? `<span class="resident-phone">📞 ${r.phone}</span>` : ''}
                            </div>
                        ` : ''}
                    </div>
                    ${!isFreePlace ? `
                        <div class="resident-actions">
                            <button class="btn-action" onclick="event.stopPropagation(); editResident(${r.id})" title="Редактировать">✏️</button>
                            <button class="btn-action" onclick="event.stopPropagation(); freePlace(${r.id}, '${r.full_name}')" title="Освободить">🗑️</button>
                        </div>
                    ` : ''}
                </div>
            `;
        });
        
        html += `
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

// ==================== РЕДАКТИРОВАНИЕ ====================
async function editResident(id) {
    try {
        const response = await fetch(`/api/resident/${id}`, { headers: AUTH_HEADERS });
        if (!response.ok) throw new Error('Ошибка загрузки жильца');
        const r = await response.json();
        
        const modal = document.getElementById('modalContent');
        modal.innerHTML = `
            <div class="modal-header">
                <span class="modal-title">✏️ Редактирование</span>
                <button class="modal-close" onclick="closeModal()">✕</button>
            </div>
            <form onsubmit="saveEdit(event, ${id})">
                <div class="form-group">
                    <label class="form-label">Группа</label>
                    <input class="form-control" id="editGroup" value="${r.group_name}" list="groupList">
                    <datalist id="groupList"></datalist>
                </div>
                <div class="form-group">
                    <label class="form-label">ФИО</label>
                    <input class="form-control" id="editName" value="${r.full_name}" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Дата заезда</label>
                    <input class="form-control" id="editCheckIn" value="${formatDate(r.check_in)}" placeholder="дд.мм.гггг">
                </div>
                <div class="form-group">
                    <label class="form-label">Регистрация до</label>
                    <input class="form-control" id="editRegistration" value="${formatDate(r.registration)}" placeholder="дд.мм.гггг">
                </div>
                <div class="form-group">
                    <label class="form-label">Телефон</label>
                    <input class="form-control" id="editPhone" value="${r.phone}" placeholder="+7...">
                </div>
                <div class="form-group">
                    <label class="form-label">Примечание</label>
                    <input class="form-control" id="editNote" value="${r.note}" placeholder="Примечание">
                </div>
                <div class="btn-row">
                    <button type="submit" class="btn-primary">✅ Сохранить</button>
                    <button type="button" class="btn-primary btn-secondary" onclick="showMoveForm(${id})">🚚 Переселить</button>
                </div>
            </form>
        `;
        loadGroups('groupList');
        openModal();
    } catch (error) {
        showToast('❌ Ошибка загрузки данных');
        console.error(error);
    }
}

async function saveEdit(event, id) {
    event.preventDefault();
    
    const data = {
        group_name: document.getElementById('editGroup').value || '-',
        full_name: document.getElementById('editName').value,
        check_in: document.getElementById('editCheckIn').value || '-',
        registration: document.getElementById('editRegistration').value || '-',
        phone: document.getElementById('editPhone').value || '-',
        note: document.getElementById('editNote').value || '-'
    };
    
    try {
        const response = await fetch(`/api/resident/${id}`, {
            method: 'PUT',
            headers: { ...AUTH_HEADERS, 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            closeModal();
            showToast('✅ Данные сохранены');
            loadData();
        } else {
            const err = await response.json();
            showToast('❌ ' + (err.error || 'Ошибка сохранения'));
        }
    } catch (error) {
        showToast('❌ Ошибка сети');
        console.error(error);
    }
}

// ==================== ПЕРЕСЕЛЕНИЕ ====================
async function showMoveForm(id) {
    const resp = await fetch(`/api/resident/${id}`, { headers: AUTH_HEADERS });
    const resident = await resp.json();
    
    const freePlacesResp = await fetch('/api/free_places', { headers: AUTH_HEADERS });
    const freePlaces = await freePlacesResp.json();

    const modal = document.getElementById('modalContent');
    modal.innerHTML = `
        <div class="modal-header">
            <span class="modal-title">🚚 Переселение</span>
            <button class="modal-close" onclick="closeModal()">✕</button>
        </div>
        <form onsubmit="saveMove(event, ${id})">
            <div class="form-group">
                <label class="form-label">ФИО</label>
                <input class="form-control" value="${resident.full_name}" disabled>
                <input type="hidden" id="moveName" value="${resident.full_name}">
            </div>
            <div class="form-group">
                <label class="form-label">Новая комната и место</label>
                <select class="form-control" id="movePlace" required>
                    ${freePlaces.map(p => 
                        `<option value="${p.room}|${p.place}">Комната ${p.room}, место ${p.place}</option>`
                    ).join('')}
                </select>
            </div>
            <div class="form-group">
                <label class="form-label">Группа</label>
                <input class="form-control" id="moveGroup" value="${resident.group_name}" list="groupListMove">
                <datalist id="groupListMove"></datalist>
            </div>
            <div class="form-group">
                <label class="form-label">Дата заезда</label>
                <input class="form-control" id="moveCheckIn" value="${formatDate(resident.check_in)}" placeholder="дд.мм.гггг">
            </div>
            <div class="form-group">
                <label class="form-label">Регистрация до</label>
                <input class="form-control" id="moveRegistration" value="${formatDate(resident.registration)}" placeholder="дд.мм.гггг">
            </div>
            <div class="form-group">
                <label class="form-label">Телефон</label>
                <input class="form-control" id="movePhone" value="${resident.phone}" placeholder="+7...">
            </div>
            <div class="form-group">
                <label class="form-label">Примечание</label>
                <input class="form-control" id="moveNote" value="${resident.note}" placeholder="Примечание">
            </div>
            <button type="submit" class="btn-primary">✅ Переселить</button>
        </form>
    `;
    loadGroups('groupListMove');
    openModal();
}

async function saveMove(event, fromId) {
    event.preventDefault();
    const placeValue = document.getElementById('movePlace').value;
    const [room, place] = placeValue.split('|');

    const data = {
        from_id: fromId,
        to_room: room,
        to_place: parseInt(place),
        group_name: document.getElementById('moveGroup').value || '-',
        full_name: document.getElementById('moveName').value,
        check_in: document.getElementById('moveCheckIn').value || '-',
        registration: document.getElementById('moveRegistration').value || '-',
        phone: document.getElementById('movePhone').value || '-',
        note: document.getElementById('moveNote').value || '-'
    };

    try {
        const response = await fetch('/api/move', {
            method: 'POST',
            headers: { ...AUTH_HEADERS, 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            closeModal();
            showToast('✅ Жилец переселён');
            loadData();
        } else {
            const err = await response.json();
            showToast('❌ ' + (err.error || 'Ошибка переселения'));
        }
    } catch (error) {
        showToast('❌ Ошибка сети');
        console.error(error);
    }
}

// ==================== ЗАСЕЛЕНИЕ ====================
function showAddForm() {
    showAddFormToRoom(null, null);
}

async function showAddFormToRoom(room, place) {
    try {
        const freePlacesResponse = await fetch('/api/free_places', { headers: AUTH_HEADERS });
        if (!freePlacesResponse.ok) throw new Error('Ошибка загрузки мест');
        const freePlaces = await freePlacesResponse.json();
        
        const modal = document.getElementById('modalContent');
        modal.innerHTML = `
            <div class="modal-header">
                <span class="modal-title">➕ Заселение</span>
                <button class="modal-close" onclick="closeModal()">✕</button>
            </div>
            <form onsubmit="saveAdd(event)">
                <div class="form-group">
                    <label class="form-label">Место</label>
                    <select class="form-control" id="addPlace" required>
                        ${freePlaces.map(p => 
                            `<option value="${p.room}|${p.place}">Комната ${p.room}, место ${p.place}</option>`
                        ).join('')}
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Группа</label>
                    <input class="form-control" id="addGroup" list="groupListAdd" placeholder="Выберите или введите новую">
                    <datalist id="groupListAdd"></datalist>
                </div>
                <div class="form-group">
                    <label class="form-label">ФИО</label>
                    <input class="form-control" id="addName" required placeholder="Введите ФИО">
                </div>
                <div class="form-group">
                    <label class="form-label">Дата заезда</label>
                    <input class="form-control" id="addCheckIn" value="${getToday()}" placeholder="дд.мм.гггг">
                </div>
                <div class="form-group">
                    <label class="form-label">Регистрация до</label>
                    <input class="form-control" id="addRegistration" placeholder="дд.мм.гггг">
                </div>
                <div class="form-group">
                    <label class="form-label">Телефон</label>
                    <input class="form-control" id="addPhone" placeholder="+7...">
                </div>
                <div class="form-group">
                    <label class="form-label">Примечание</label>
                    <input class="form-control" id="addNote" placeholder="Примечание">
                </div>
                <button type="submit" class="btn-primary">✅ Заселить</button>
            </form>
        `;
        
        if (room && place) {
            const select = document.getElementById('addPlace');
            const options = select.options;
            for (let i = 0; i < options.length; i++) {
                const [r, p] = options[i].value.split('|');
                if (r === String(room) && parseInt(p) === place) {
                    select.selectedIndex = i;
                    break;
                }
            }
        }
        
        loadGroups('groupListAdd');
        openModal();
    } catch (error) {
        showToast('❌ Ошибка загрузки свободных мест');
        console.error(error);
    }
}

async function saveAdd(event) {
    event.preventDefault();
    
    const placeValue = document.getElementById('addPlace').value;
    const [room, place] = placeValue.split('|');
    
    const data = {
        room: room,
        place: parseInt(place),
        group_name: document.getElementById('addGroup').value || '-',
        full_name: document.getElementById('addName').value,
        check_in: document.getElementById('addCheckIn').value || '-',
        registration: document.getElementById('addRegistration').value || '-',
        phone: document.getElementById('addPhone').value || '-',
        note: document.getElementById('addNote').value || '-'
    };
    
    try {
        const response = await fetch('/api/add', {
            method: 'POST',
            headers: { ...AUTH_HEADERS, 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            closeModal();
            showToast('✅ Жилец заселён');
            loadData();
        } else {
            const error = await response.json();
            showToast('❌ ' + (error.error || 'Ошибка заселения'));
        }
    } catch (error) {
        showToast('❌ Ошибка сети');
        console.error(error);
    }
}

// ==================== ОСВОБОЖДЕНИЕ ====================
async function freePlace(id, name) {
    if (!confirm(`Освободить место "${name}"?`)) return;
    
    try {
        const response = await fetch('/api/free', {
            method: 'POST',
            headers: { ...AUTH_HEADERS, 'Content-Type': 'application/json' },
            body: JSON.stringify({ id })
        });
        
        if (response.ok) {
            showToast('✅ Место освобождено');
            loadData();
        } else {
            showToast('❌ Ошибка');
        }
    } catch (error) {
        showToast('❌ Ошибка сети');
        console.error(error);
    }
}

// ==================== ОТЧЁТ ====================
async function showReport() {
    try {
        const response = await fetch('/api/report', { headers: AUTH_HEADERS });
        if (!response.ok) throw new Error('Ошибка отчёта');
        const data = await response.json();
        
        const modal = document.getElementById('modalContent');
        let groupsHtml = '';
        (data.groups || []).forEach(g => {
            groupsHtml += `
                <div class="report-item">
                    <div class="report-item-label">${g.group_name}</div>
                    <div class="report-item-value">${g.count}</div>
                </div>
            `;
        });
        
        modal.innerHTML = `
            <div class="modal-header">
                <span class="modal-title">📊 Отчёт</span>
                <button class="modal-close" onclick="closeModal()">✕</button>
            </div>
            <div class="report-container">
                <div class="report-section">
                    <div class="report-section-title">📈 Общие показатели</div>
                    <div class="report-grid">
                        <div class="report-item">
                            <div class="report-item-label">Всего мест</div>
                            <div class="report-item-value">${data.total}</div>
                        </div>
                        <div class="report-item">
                            <div class="report-item-label">👥 Заселено</div>
                            <div class="report-item-value" style="color:#88dd88">${data.occupied}</div>
                        </div>
                        <div class="report-item">
                            <div class="report-item-label">🟢 Свободно</div>
                            <div class="report-item-value" style="color:#ff8888">${data.free}</div>
                        </div>
                        <div class="report-item">
                            <div class="report-item-label">Загрузка</div>
                            <div class="report-item-value">${data.load_percent}%</div>
                        </div>
                    </div>
                </div>
                
                <div class="report-section">
                    <div class="report-section-title">👥 Группы</div>
                    <div class="report-grid">
                        ${groupsHtml || '<div style="grid-column:1/-1;text-align:center;color:#666;">Нет данных</div>'}
                    </div>
                </div>
                
                <div class="report-section">
                    <div class="report-section-title">💰 Финансы</div>
                    <div class="report-grid">
                        <div class="report-item">
                            <div class="report-item-label">Стирка</div>
                            <div class="report-item-value">${data.settings?.стирка || '400'} ₽</div>
                        </div>
                        <div class="report-item">
                            <div class="report-item-label">Госпошлина</div>
                            <div class="report-item-value">${data.settings?.госпошлина || '2000'} ₽</div>
                        </div>
                    </div>
                </div>
                
                <div class="report-section">
                    <div class="report-section-title">🧺 Постельное бельё</div>
                    <div class="report-grid">
                        <div class="report-item">
                            <div class="report-item-label">Чистое</div>
                            <div class="report-item-value">${data.settings?.кпб_чистое || '10'}</div>
                        </div>
                        <div class="report-item">
                            <div class="report-item-label">Грязное</div>
                            <div class="report-item-value">${data.settings?.кпб_грязное || '4'}</div>
                        </div>
                        <div class="report-item">
                            <div class="report-item-label">Сдано</div>
                            <div class="report-item-value">${data.settings?.кпб_сдано || '0'}</div>
                        </div>
                        <div class="report-item">
                            <div class="report-item-label">Принято</div>
                            <div class="report-item-value">${data.settings?.кпб_принято || '0'}</div>
                        </div>
                    </div>
                </div>
                
                <div style="text-align:center;margin-top:16px;color:#666;font-size:12px;">
                    Отчёт: ${data.date}
                </div>
            </div>
        `;
        
        openModal();
    } catch (error) {
        showToast('❌ Ошибка загрузки отчёта');
        console.error(error);
    }
}

// ==================== НАСТРОЙКИ ====================
async function showSettings() {
    try {
        const response = await fetch('/api/settings', { headers: AUTH_HEADERS });
        if (!response.ok) throw new Error('Ошибка настроек');
        const settings = await response.json();
        
        const modal = document.getElementById('modalContent');
        modal.innerHTML = `
            <div class="modal-header">
                <span class="modal-title">⚙️ Настройки</span>
                <button class="modal-close" onclick="closeModal()">✕</button>
            </div>
            <form onsubmit="saveSettings(event)">
                <div class="form-group">
                    <label class="form-label">💰 Стирка (₽)</label>
                    <input class="form-control" id="settingWash" value="${settings.стирка || '400'}">
                </div>
                <div class="form-group">
                    <label class="form-label">💰 Госпошлина (₽)</label>
                    <input class="form-control" id="settingStateFee" value="${settings.госпошлина || '2000'}">
                </div>
                <div class="form-group">
                    <label class="form-label">🧺 Чистое КПБ</label>
                    <input class="form-control" id="settingKpbClean" value="${settings.кпб_чистое || '10'}">
                </div>
                <div class="form-group">
                    <label class="form-label">🧺 Грязное КПБ</label>
                    <input class="form-control" id="settingKpbDirty" value="${settings.кпб_грязное || '4'}">
                </div>
                <div class="form-group">
                    <label class="form-label">🧺 Сдано КПБ</label>
                    <input class="form-control" id="settingKpbGiven" value="${settings.кпб_сдано || '0'}">
                </div>
                <div class="form-group">
                    <label class="form-label">🧺 Принято КПБ</label>
                    <input class="form-control" id="settingKpbReceived" value="${settings.кпб_принято || '0'}">
                </div>
                <button type="submit" class="btn-primary">✅ Сохранить</button>
            </form>
        `;
        
        openModal();
    } catch (error) {
        showToast('❌ Ошибка загрузки настроек');
        console.error(error);
    }
}

async function saveSettings(event) {
    event.preventDefault();
    
    const data = {
        стирка: document.getElementById('settingWash').value || '0',
        госпошлина: document.getElementById('settingStateFee').value || '0',
        кпб_чистое: document.getElementById('settingKpbClean').value || '0',
        кпб_грязное: document.getElementById('settingKpbDirty').value || '0',
        кпб_сдано: document.getElementById('settingKpbGiven').value || '0',
        кпб_принято: document.getElementById('settingKpbReceived').value || '0'
    };
    
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: { ...AUTH_HEADERS, 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            closeModal();
            showToast('✅ Настройки сохранены');
            updateStats();
        } else {
            const err = await response.json();
            showToast('❌ ' + (err.error || 'Ошибка сохранения'));
        }
    } catch (error) {
        showToast('❌ Ошибка сети');
        console.error(error);
    }
}

// ==================== ГРУППЫ ====================
async function loadGroups(datalistId) {
    try {
        const response = await fetch('/api/groups', { headers: AUTH_HEADERS });
        if (!response.ok) throw new Error('Ошибка групп');
        const groups = await response.json();
        const datalist = document.getElementById(datalistId);
        if (datalist) {
            datalist.innerHTML = groups.map(g => `<option value="${g}">`).join('');
        }
    } catch (error) {
        console.error('Ошибка загрузки групп:', error);
    }
}

// ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
function getToday() {
    const now = new Date();
    const day = String(now.getDate()).padStart(2, '0');
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const year = now.getFullYear();
    return `${day}.${month}.${year}`;
}

function openModal() {
    document.getElementById('modalOverlay').classList.add('open');
    document.body.style.overflow = 'hidden';
}

function closeModal(event) {
    if (event && event.target !== event.currentTarget) return;
    document.getElementById('modalOverlay').classList.remove('open');
    document.body.style.overflow = '';
}

function showToast(message) {
    const toast = document.createElement('div');
    toast.className = 'toast show';
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function showMain() {
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    document.querySelector('.nav-item:first-child').classList.add('active');
    window.scrollTo({ top: 0, behavior: 'smooth' });
}