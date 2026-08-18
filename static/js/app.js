// ==================== СОСТОЯНИЕ ====================
let allResidents = [];
let filteredResidents = [];
let currentFilter = 'all';
let currentFloor = 'all';
let searchQuery = '';
let authToken = localStorage.getItem('hostel_auth_token') || '';
let isGuest = false;
let hasUnsavedChanges = false;

// ==================== XSS ЗАЩИТА ====================
function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

// ==================== АУТЕНТИФИКАЦИЯ ====================
function checkAuth() {
    if (!authToken) {
        document.getElementById('authOverlay').style.display = 'flex';
        document.getElementById('app').style.display = 'none';
        return;
    }

    // Определяем, гость ли это (по токену)
    isGuest = authToken.startsWith('guest') || authToken === 'guest-view-2026';

    document.getElementById('authOverlay').style.display = 'none';
    document.getElementById('app').style.display = 'block';

    // Показываем гостевую метку
    const guestBadge = document.getElementById('guestBadge');
    if (isGuest) {
        if (!guestBadge) {
            const badge = document.createElement('div');
            badge.id = 'guestBadge';
            badge.style.cssText = `
                background: #ffaa00; color: #121212; 
                padding: 4px 12px; border-radius: 20px;
                font-size: 12px; font-weight: 600;
                margin-left: 10px; display: inline-block;
            `;
            badge.textContent = '👀 Гостевой (только просмотр)';
            document.querySelector('.app-title').appendChild(badge);
        }
    } else {
        if (guestBadge) guestBadge.remove();
    }

    // Скрыть/показать кнопки редактирования
    toggleEditButtons();

    loadData();
    loadFloors();
    updateStats();
}

function doAuth() {
    const token = document.getElementById('authToken').value.trim();
    if (!token) {
        document.getElementById('authError').textContent = 'Введите токен';
        return;
    }
    authToken = token;
    localStorage.setItem('hostel_auth_token', token);
    checkAuth();
}

function logout() {
    authToken = '';
    localStorage.removeItem('hostel_auth_token');
    checkAuth();
}

function toggleEditButtons() {
    // Скрываем кнопки редактирования в шапке (кроме кнопки выхода — у неё нет класса btn-edit-allowed)
    document.querySelectorAll('.btn-edit-allowed').forEach(el => {
        el.style.display = isGuest ? 'none' : 'flex';
    });
}

// ==================== API ХЕЛПЕР ====================
async function apiFetch(url, options = {}) {
    options.headers = options.headers || {};
    options.headers['X-Auth-Token'] = authToken;
    if (!options.headers['Content-Type'] && (!options.body || typeof options.body === 'string')) {
        options.headers['Content-Type'] = 'application/json';
    }
    const resp = await fetch(url, options);
    if (resp.status === 401) {
        logout();
        throw new Error('Unauthorized');
    }
    if (resp.status === 403) {
        showToast('error', 'Гостевой режим: действие запрещено');
        throw new Error('Forbidden');
    }
    return resp;
}

// ==================== DEBOUNCE ====================
function debounce(fn, ms) {
    let timer;
    return function(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), ms);
    };
}

// ==================== ИНИЦИАЛИЗАЦИЯ ====================
document.addEventListener('DOMContentLoaded', () => {
    checkAuth();
    const searchInput = document.getElementById('searchInput');
    const clearBtn = document.querySelector('.btn-clear');
    searchInput.addEventListener('input', debounce(() => {
        clearBtn.classList.toggle('visible', searchInput.value.length > 0);
        applyFilters();
    }, 300));
});

// ==================== ЗАГРУЗКА ДАННЫХ ====================
async function loadData() {
    try {
        const url = currentFloor !== 'all' ? `/api/residents?floor=${currentFloor}` : '/api/residents';
        const response = await apiFetch(url);
        if (!response.ok) throw new Error('Ошибка загрузки');
        allResidents = await response.json();
        filteredResidents = [...allResidents];
        renderRooms();
    } catch (error) {
        console.error(error);
        showToast('error', 'Ошибка загрузки данных');
    }
}

async function loadFloors() {
    try {
        const resp = await apiFetch('/api/floors');
        if (!resp.ok) return;
        const floors = await resp.json();
        const container = document.getElementById('floorTabs');
        let html = `<button class="floor-tab active" data-floor="all" onclick="filterByFloor('all')">Все</button>`;
        floors.forEach(f => {
            html += `<button class="floor-tab" data-floor="${f}" onclick="filterByFloor('${f}')">${f}</button>`;
        });
        container.innerHTML = html;
    } catch (e) {
        console.error(e);
    }
}

async function updateStats() {
    try {
        const response = await apiFetch('/api/report');
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
    if (!isoDate || isoDate === '-') return '';
    try {
        const d = new Date(isoDate + 'T00:00:00');
        if (isNaN(d.getTime())) return '';
        const day = String(d.getDate()).padStart(2, '0');
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const year = d.getFullYear();
        return `${year}-${month}-${day}`;
    } catch {
        return '';
    }
}

function formatDateDisplay(isoDate) {
    if (!isoDate || isoDate === '-') return '-';
    try {
        const d = new Date(isoDate + 'T00:00:00');
        if (isNaN(d.getTime())) return isoDate;
        return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
    } catch {
        return isoDate;
    }
}

function dateFromInput(val) {
    if (!val) return '-';
    const [y, m, d] = val.split('-');
    return `${d}.${m}.${y}`;
}

// ==================== ФИЛЬТРАЦИЯ ====================
function filterByFloor(floor) {
    currentFloor = floor;
    document.querySelectorAll('.floor-tab').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.floor === String(floor));
    });
    loadData();
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
    applyFilters();
}

function applyFilters() {
    searchQuery = document.getElementById('searchInput').value.toLowerCase().trim();
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
                <div style="font-size:48px;margin-bottom:16px;">
                    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#666" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="11" cy="11" r="8"></circle>
                        <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                    </svg>
                </div>
                <div>Ничего не найдено</div>
            </div>`;
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
                    <span class="room-name">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:6px;">
                            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
                            <polyline points="9 22 9 12 15 12 15 22"></polyline>
                        </svg>
                        Комната ${escapeHtml(room)}
                    </span>
                    <span class="room-stats">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:4px;">
                            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                            <circle cx="9" cy="7" r="4"></circle>
                            <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
                            <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
                        </svg>
                        ${occupied} / ${totalPlaces} · 
                        <span class="occupied-badge">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#88dd88" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:2px;">
                                <circle cx="12" cy="12" r="10"></circle>
                                <path d="M12 6v6l4 2"></path>
                            </svg>
                            ${occupied}
                        </span> · 
                        <span class="free-badge">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ff8888" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:2px;">
                                <circle cx="12" cy="12" r="10"></circle>
                                <line x1="15" y1="9" x2="9" y2="15"></line>
                                <line x1="9" y1="9" x2="15" y2="15"></line>
                            </svg>
                            ${free}
                        </span>
                    </span>
                </div>
                <div class="residents-list">`;
        residents.sort((a, b) => a.place - b.place);
        residents.forEach(r => {
            const isFreePlace = r.full_name === '(свободно)';
            const nameEscaped = escapeHtml(r.full_name);
            const groupEscaped = escapeHtml(r.group_name);
            const phoneEscaped = escapeHtml(r.phone);
            const checkInDisplay = formatDateDisplay(r.check_in);
            const regDisplay = formatDateDisplay(r.registration);
            
            // В гостевом режиме клик по жильцу ничего не делает
            const clickHandler = !isGuest && !isFreePlace ? `onclick="editResident(${r.id})"` : '';
            
            html += `
                <div class="resident-item" ${clickHandler}>
                    <span class="resident-place">${r.place}</span>
                    <div class="resident-info">
                        <div class="resident-name ${isFreePlace ? 'free' : ''}">
                            ${isFreePlace ? 
                                `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ff8888" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:4px;">
                                    <circle cx="12" cy="12" r="10"></circle>
                                    <line x1="15" y1="9" x2="9" y2="15"></line>
                                    <line x1="9" y1="9" x2="15" y2="15"></line>
                                </svg> свободно` 
                                : nameEscaped}
                        </div>
                        ${!isFreePlace ? `
                            <div class="resident-details">
                                <span class="resident-group">${groupEscaped}</span>
                                <span>
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:2px;">
                                        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                                        <line x1="16" y1="2" x2="16" y2="6"></line>
                                        <line x1="8" y1="2" x2="8" y2="6"></line>
                                        <line x1="3" y1="10" x2="21" y2="10"></line>
                                    </svg>
                                    ${checkInDisplay}
                                </span>
                                ${regDisplay && regDisplay !== '-' ? `
                                <span>
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:2px;">
                                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                                        <polyline points="14 2 14 8 20 8"></polyline>
                                        <line x1="12" y1="18" x2="12" y2="12"></line>
                                        <line x1="9" y1="15" x2="15" y2="15"></line>
                                    </svg>
                                    ${regDisplay}
                                </span>
                                ` : ''}
                                ${r.phone && r.phone !== '-' ? `
                                    <span class="resident-phone">
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:2px;">
                                            <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"></path>
                                        </svg>
                                        ${phoneEscaped}
                                    </span>
                                ` : ''}
                            </div>
                        ` : ''}
                    </div>
                    ${!isFreePlace && !isGuest ? `
                        <div class="resident-actions">
                            <button class="btn-action" onclick="event.stopPropagation(); editResident(${r.id})" title="Редактировать">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#4a9eff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                                </svg>
                            </button>
                            <button class="btn-action" onclick="event.stopPropagation(); freePlace(${r.id}, '${nameEscaped}')" title="Освободить">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#4a9eff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <polyline points="3 6 5 6 21 6"></polyline>
                                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                                    <line x1="10" y1="11" x2="10" y2="17"></line>
                                    <line x1="14" y1="11" x2="14" y2="17"></line>
                                </svg>
                            </button>
                        </div>
                    ` : ''}
                </div>`;
        });
        html += `</div></div>`;
    });
    container.innerHTML = html;
}

// ==================== РЕДАКТИРОВАНИЕ ====================
async function editResident(id) {
    if (isGuest) {
        showToast('error', 'Гостевой режим: редактирование запрещено');
        return;
    }
    try {
        const response = await apiFetch(`/api/residents/${id}`);
        if (!response.ok) throw new Error('Ошибка загрузки жильца');
        const r = await response.json();
        const modal = document.getElementById('modalContent');
        modal.innerHTML = `
            <div class="modal-header">
                <span class="modal-title">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:8px;">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                    </svg>
                    Редактирование
                </span>
                <button class="modal-close" onclick="confirmCloseModal()">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                </button>
            </div>
            <form onsubmit="saveEdit(event, ${r.id})" oninput="hasUnsavedChanges=true">
                <div class="form-group">
                    <label class="form-label">Группа</label>
                    <input class="form-control" id="editGroup" value="${escapeHtml(r.group_name)}" list="groupList">
                    <datalist id="groupList"></datalist>
                </div>
                <div class="form-group">
                    <label class="form-label">ФИО</label>
                    <input class="form-control" id="editName" value="${escapeHtml(r.full_name)}" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Дата заезда</label>
                    <input type="date" class="form-control" id="editCheckIn" value="${formatDate(r.check_in)}">
                </div>
                <div class="form-group">
                    <label class="form-label">Регистрация до</label>
                    <input type="date" class="form-control" id="editRegistration" value="${formatDate(r.registration)}">
                </div>
                <div class="form-group">
                    <label class="form-label">Телефон</label>
                    <input class="form-control" id="editPhone" value="${escapeHtml(r.phone)}" placeholder="+7...">
                </div>
                <div class="form-group">
                    <label class="form-label">Примечание</label>
                    <input class="form-control" id="editNote" value="${escapeHtml(r.note)}" placeholder="Примечание">
                </div>
                <div class="btn-row">
                    <button type="submit" class="btn-primary">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:6px;">
                            <path d="M20 6L9 17l-5-5"></path>
                        </svg>
                        Сохранить
                    </button>
                    <button type="button" class="btn-primary btn-secondary" onclick="showMoveForm(${r.id})">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:6px;">
                            <path d="M5 12h14M12 5l7 7-7 7"></path>
                        </svg>
                        Переселить
                    </button>
                </div>
            </form>`;
        loadGroups('groupList');
        hasUnsavedChanges = false;
        openModal();
    } catch (error) {
        showToast('error', 'Ошибка загрузки данных');
        console.error(error);
    }
}

async function saveEdit(event, id) {
    event.preventDefault();
    const data = {
        group_name: document.getElementById('editGroup').value || '-',
        full_name: document.getElementById('editName').value,
        check_in: dateFromInput(document.getElementById('editCheckIn').value),
        registration: dateFromInput(document.getElementById('editRegistration').value),
        phone: document.getElementById('editPhone').value || '-',
        note: document.getElementById('editNote').value || '-'
    };
    try {
        const response = await apiFetch(`/api/residents/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
        if (response.ok) {
            closeModal();
            showToast('success', 'Данные сохранены');
            loadData();
            updateStats();
        } else {
            const err = await response.json();
            showToast('error', err.error || 'Ошибка сохранения');
        }
    } catch (error) {
        showToast('error', 'Ошибка сети');
        console.error(error);
    }
}

// ==================== ПЕРЕСЕЛЕНИЕ ====================
async function showMoveForm(id) {
    if (isGuest) {
        showToast('error', 'Гостевой режим: переселение запрещено');
        return;
    }
    const resp = await apiFetch(`/api/residents/${id}`);
    const resident = await resp.json();
    const url = currentFloor !== 'all' ? `/api/free_places?floor=${currentFloor}` : '/api/free_places';
    const freePlacesResp = await apiFetch(url);
    const freePlaces = await freePlacesResp.json();
    const modal = document.getElementById('modalContent');
    modal.innerHTML = `
        <div class="modal-header">
            <span class="modal-title">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:8px;">
                    <path d="M5 12h14M12 5l7 7-7 7"></path>
                </svg>
                Переселение
            </span>
            <button class="modal-close" onclick="confirmCloseModal()">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </button>
        </div>
        <form onsubmit="saveMove(event, ${id})" oninput="hasUnsavedChanges=true">
            <div class="form-group">
                <label class="form-label">ФИО</label>
                <input class="form-control" value="${escapeHtml(resident.full_name)}" disabled>
                <input type="hidden" id="moveName" value="${escapeHtml(resident.full_name)}">
            </div>
            <div class="form-group">
                <label class="form-label">Новая комната и место</label>
                <select class="form-control" id="movePlace" required>
                    ${freePlaces.map(p => 
                        `<option value="${escapeHtml(p.room)}|${p.place}">Комната ${escapeHtml(p.room)}, место ${p.place}</option>`
                    ).join('')}
                </select>
            </div>
            <div class="form-group">
                <label class="form-label">Группа</label>
                <input class="form-control" id="moveGroup" value="${escapeHtml(resident.group_name)}" list="groupListMove">
                <datalist id="groupListMove"></datalist>
            </div>
            <div class="form-group">
                <label class="form-label">Дата заезда</label>
                <input type="date" class="form-control" id="moveCheckIn" value="${formatDate(resident.check_in)}">
            </div>
            <div class="form-group">
                <label class="form-label">Регистрация до</label>
                <input type="date" class="form-control" id="moveRegistration" value="${formatDate(resident.registration)}">
            </div>
            <div class="form-group">
                <label class="form-label">Телефон</label>
                <input class="form-control" id="movePhone" value="${escapeHtml(resident.phone)}" placeholder="+7...">
            </div>
            <div class="form-group">
                <label class="form-label">Примечание</label>
                <input class="form-control" id="moveNote" value="${escapeHtml(resident.note)}" placeholder="Примечание">
            </div>
            <button type="submit" class="btn-primary">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:6px;">
                    <path d="M20 6L9 17l-5-5"></path>
                </svg>
                Переселить
            </button>
        </form>`;
    loadGroups('groupListMove');
    hasUnsavedChanges = false;
    openModal();
}

async function saveMove(event, fromId) {
    event.preventDefault();
    const placeValue = document.getElementById('movePlace').value;
    const [room, place] = placeValue.split('|');
    const data = {
        to_room: room,
        to_place: parseInt(place),
        group_name: document.getElementById('moveGroup').value || '-',
        full_name: document.getElementById('moveName').value,
        check_in: dateFromInput(document.getElementById('moveCheckIn').value),
        registration: dateFromInput(document.getElementById('moveRegistration').value),
        phone: document.getElementById('movePhone').value || '-',
        note: document.getElementById('moveNote').value || '-'
    };
    try {
        const response = await apiFetch(`/api/residents/${fromId}/move`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
        if (response.ok) {
            closeModal();
            showToast('success', 'Жилец переселён');
            loadData();
            updateStats();
        } else {
            const err = await response.json();
            showToast('error', err.error || 'Ошибка переселения');
        }
    } catch (error) {
        showToast('error', 'Ошибка сети');
        console.error(error);
    }
}

// ==================== ЗАСЕЛЕНИЕ ====================
function showAddForm() {
    if (isGuest) {
        showToast('error', 'Гостевой режим: заселение запрещено');
        return;
    }
    showAddFormToRoom(null, null);
}

async function showAddFormToRoom(room, place) {
    if (isGuest) {
        showToast('error', 'Гостевой режим: заселение запрещено');
        return;
    }
    try {
        const url = currentFloor !== 'all' ? `/api/free_places?floor=${currentFloor}` : '/api/free_places';
        const freePlacesResponse = await apiFetch(url);
        if (!freePlacesResponse.ok) throw new Error('Ошибка загрузки мест');
        const freePlaces = await freePlacesResponse.json();
        const modal = document.getElementById('modalContent');
        modal.innerHTML = `
            <div class="modal-header">
                <span class="modal-title">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:8px;">
                        <line x1="12" y1="5" x2="12" y2="19"></line>
                        <line x1="5" y1="12" x2="19" y2="12"></line>
                    </svg>
                    Заселение
                </span>
                <button class="modal-close" onclick="confirmCloseModal()">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                </button>
            </div>
            <form onsubmit="saveAdd(event)" oninput="hasUnsavedChanges=true">
                <div class="form-group">
                    <label class="form-label">Место</label>
                    <select class="form-control" id="addPlace" required>
                        ${freePlaces.map(p => 
                            `<option value="${escapeHtml(p.room)}|${p.place}">Комната ${escapeHtml(p.room)}, место ${p.place}</option>`
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
                    <input type="date" class="form-control" id="addCheckIn" value="${getTodayISO()}">
                </div>
                <div class="form-group">
                    <label class="form-label">Регистрация до</label>
                    <input type="date" class="form-control" id="addRegistration">
                </div>
                <div class="form-group">
                    <label class="form-label">Телефон</label>
                    <input class="form-control" id="addPhone" placeholder="+7...">
                </div>
                <div class="form-group">
                    <label class="form-label">Примечание</label>
                    <input class="form-control" id="addNote" placeholder="Примечание">
                </div>
                <button type="submit" class="btn-primary">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:6px;">
                        <path d="M20 6L9 17l-5-5"></path>
                    </svg>
                    Заселить
                </button>
            </form>`;
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
        hasUnsavedChanges = false;
        openModal();
    } catch (error) {
        showToast('error', 'Ошибка загрузки свободных мест');
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
        check_in: dateFromInput(document.getElementById('addCheckIn').value),
        registration: dateFromInput(document.getElementById('addRegistration').value),
        phone: document.getElementById('addPhone').value || '-',
        note: document.getElementById('addNote').value || '-'
    };
    try {
        const response = await apiFetch('/api/residents', {
            method: 'POST',
            body: JSON.stringify(data)
        });
        if (response.ok) {
            closeModal();
            showToast('success', 'Жилец заселён');
            loadData();
            updateStats();
        } else {
            const error = await response.json();
            showToast('error', error.error || 'Ошибка заселения');
        }
    } catch (error) {
        showToast('error', 'Ошибка сети');
        console.error(error);
    }
}

// ==================== ОСВОБОЖДЕНИЕ ====================
async function freePlace(id, name) {
    if (isGuest) {
        showToast('error', 'Гостевой режим: освобождение запрещено');
        return;
    }
    if (!confirm(`Освободить место "${name}"?`)) return;
    try {
        const response = await apiFetch(`/api/residents/${id}`, { method: 'DELETE' });
        if (response.ok) {
            showToast('success', 'Место освобождено');
            loadData();
            updateStats();
        } else {
            showToast('error', 'Ошибка');
        }
    } catch (error) {
        showToast('error', 'Ошибка сети');
        console.error(error);
    }
}

// ==================== ОТЧЁТ ====================
async function showReport() {
    try {
        const response = await apiFetch('/api/report');
        if (!response.ok) throw new Error('Ошибка отчёта');
        const data = await response.json();
        let groupsHtml = '';
        (data.groups || []).forEach(g => {
            groupsHtml += `
                <div class="report-item">
                    <div class="report-item-label">${escapeHtml(g.group_name)}</div>
                    <div class="report-item-value">${g.count}</div>
                </div>`;
        });
        const modal = document.getElementById('modalContent');
        modal.innerHTML = `
            <div class="modal-header">
                <span class="modal-title">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:8px;">
                        <path d="M21 12v-2a5 5 0 0 0-5-5H8a5 5 0 0 0-5 5v2"></path>
                        <circle cx="12" cy="16" r="5"></circle>
                        <line x1="12" y1="11" x2="12" y2="16"></line>
                        <line x1="9" y1="13" x2="12" y2="16"></line>
                        <line x1="15" y1="13" x2="12" y2="16"></line>
                    </svg>
                    Отчёт
                </span>
                <button class="modal-close" onclick="closeModal()">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                </button>
            </div>
            <div class="report-container">
                <div class="report-section">
                    <div class="report-section-title">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:6px;">
                            <path d="M21 12v-2a5 5 0 0 0-5-5H8a5 5 0 0 0-5 5v2"></path>
                            <circle cx="12" cy="16" r="5"></circle>
                            <line x1="12" y1="11" x2="12" y2="16"></line>
                            <line x1="9" y1="13" x2="12" y2="16"></line>
                            <line x1="15" y1="13" x2="12" y2="16"></line>
                        </svg>
                        Общие показатели
                    </div>
                    <div class="report-grid">
                        <div class="report-item"><div class="report-item-label">Всего мест</div><div class="report-item-value">${data.total}</div></div>
                        <div class="report-item"><div class="report-item-label"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:4px;"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>Заселено</div><div class="report-item-value" style="color:#88dd88">${data.occupied}</div></div>
                        <div class="report-item"><div class="report-item-label"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:4px;"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>Свободно</div><div class="report-item-value" style="color:#ff8888">${data.free}</div></div>
                        <div class="report-item"><div class="report-item-label">Загрузка</div><div class="report-item-value">${data.load_percent}%</div></div>
                    </div>
                </div>
                <div class="report-section">
                    <div class="report-section-title"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:6px;"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>Группы</div>
                    <div class="report-grid">${groupsHtml || '<div style="grid-column:1/-1;text-align:center;color:#666;">Нет данных</div>'}</div>
                </div>
                <div class="report-section">
                    <div class="report-section-title"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:6px;"><circle cx="12" cy="12" r="2"></circle><path d="M12 2a10 10 0 0 0 0 20 10 10 0 0 0 0-20z"></path><path d="M2 12h20"></path><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>Финансы</div>
                    <div class="report-grid">
                        <div class="report-item"><div class="report-item-label">Стирка</div><div class="report-item-value">${data.settings?.стирка || '400'} ₽</div></div>
                        <div class="report-item"><div class="report-item-label">Госпошлина</div><div class="report-item-value">${data.settings?.госпошлина || '2000'} ₽</div></div>
                    </div>
                </div>
                <div class="report-section">
                    <div class="report-section-title"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:6px;"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="3" y1="9" x2="21" y2="9"></line><line x1="9" y1="21" x2="9" y2="9"></line></svg>Постельное бельё</div>
                    <div class="report-grid">
                        <div class="report-item"><div class="report-item-label">Чистое</div><div class="report-item-value">${data.settings?.кпб_чистое || '10'}</div></div>
                        <div class="report-item"><div class="report-item-label">Грязное</div><div class="report-item-value">${data.settings?.кпб_грязное || '4'}</div></div>
                        <div class="report-item"><div class="report-item-label">Сдано</div><div class="report-item-value">${data.settings?.кпб_сдано || '0'}</div></div>
                        <div class="report-item"><div class="report-item-label">Принято</div><div class="report-item-value">${data.settings?.кпб_принято || '0'}</div></div>
                    </div>
                </div>
                <div style="text-align:center;margin-top:16px;color:#666;font-size:12px;">Отчёт: ${data.date}</div>
            </div>`;
        openModal();
    } catch (error) {
        showToast('error', 'Ошибка загрузки отчёта');
        console.error(error);
    }
}

// ==================== НАСТРОЙКИ ====================
async function showSettings() {
    if (isGuest) {
        showToast('error', 'Гостевой режим: настройки запрещены');
        return;
    }
    try {
        const response = await apiFetch('/api/settings');
        if (!response.ok) throw new Error('Ошибка настроек');
        const settings = await response.json();
        const modal = document.getElementById('modalContent');
        modal.innerHTML = `
            <div class="modal-header">
                <span class="modal-title">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:8px;">
                        <circle cx="12" cy="12" r="3"></circle>
                        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
                    </svg>
                    Настройки
                </span>
                <button class="modal-close" onclick="closeModal()">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                </button>
            </div>
            <form onsubmit="saveSettings(event)" oninput="hasUnsavedChanges=true">
                <div class="form-group">
                    <label class="form-label"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:6px;"><circle cx="12" cy="12" r="2"></circle><path d="M12 2a10 10 0 0 0 0 20 10 10 0 0 0 0-20z"></path><path d="M2 12h20"></path><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>Стирка (₽)</label>
                    <input class="form-control" id="settingWash" value="${escapeHtml(settings.стирка || '400')}">
                </div>
                <div class="form-group">
                    <label class="form-label"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:6px;"><circle cx="12" cy="12" r="2"></circle><path d="M12 2a10 10 0 0 0 0 20 10 10 0 0 0 0-20z"></path><path d="M2 12h20"></path><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>Госпошлина (₽)</label>
                    <input class="form-control" id="settingStateFee" value="${escapeHtml(settings.госпошлина || '2000')}">
                </div>
                <div class="form-group">
                    <label class="form-label"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:6px;"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="3" y1="9" x2="21" y2="9"></line><line x1="9" y1="21" x2="9" y2="9"></line></svg>Чистое КПБ</label>
                    <input class="form-control" id="settingKpbClean" value="${escapeHtml(settings.кпб_чистое || '10')}">
                </div>
                <div class="form-group">
                    <label class="form-label"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:6px;"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="3" y1="9" x2="21" y2="9"></line><line x1="9" y1="21" x2="9" y2="9"></line></svg>Грязное КПБ</label>
                    <input class="form-control" id="settingKpbDirty" value="${escapeHtml(settings.кпб_грязное || '4')}">
                </div>
                <div class="form-group">
                    <label class="form-label"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:6px;"><path d="M5 12h14M12 5l7 7-7 7"></path></svg>Сдано КПБ</label>
                    <input class="form-control" id="settingKpbGiven" value="${escapeHtml(settings.кпб_сдано || '0')}">
                </div>
                <div class="form-group">
                    <label class="form-label"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:6px;"><path d="M5 12h14M12 5l7 7-7 7"></path></svg>Принято КПБ</label>
                    <input class="form-control" id="settingKpbReceived" value="${escapeHtml(settings.кпб_принято || '0')}">
                </div>
                <button type="submit" class="btn-primary">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:6px;"><path d="M20 6L9 17l-5-5"></path></svg>
                    Сохранить
                </button>
            </form>`;
        hasUnsavedChanges = false;
        openModal();
    } catch (error) {
        showToast('error', 'Ошибка загрузки настроек');
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
        const response = await apiFetch('/api/settings', {
            method: 'POST',
            body: JSON.stringify(data)
        });
        if (response.ok) {
            closeModal();
            showToast('success', 'Настройки сохранены');
            updateStats();
        } else {
            const err = await response.json();
            showToast('error', err.error || 'Ошибка сохранения');
        }
    } catch (error) {
        showToast('error', 'Ошибка сети');
        console.error(error);
    }
}

// ==================== ГРУППЫ ====================
async function loadGroups(datalistId) {
    try {
        const response = await apiFetch('/api/groups');
        if (!response.ok) throw new Error('Ошибка групп');
        const groups = await response.json();
        const datalist = document.getElementById(datalistId);
        if (datalist) {
            datalist.innerHTML = groups.map(g => `<option value="${escapeHtml(g)}">`).join('');
        }
    } catch (error) {
        console.error('Ошибка загрузки групп:', error);
    }
}

// ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
function getTodayISO() {
    const now = new Date();
    const day = String(now.getDate()).padStart(2, '0');
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const year = now.getFullYear();
    return `${year}-${month}-${day}`;
}

function openModal() {
    document.getElementById('modalOverlay').classList.add('open');
    document.body.style.overflow = 'hidden';
}

function closeModal(event) {
    if (event && event.target !== event.currentTarget) return;
    document.getElementById('modalOverlay').classList.remove('open');
    document.body.style.overflow = '';
    hasUnsavedChanges = false;
}

function confirmCloseModal() {
    if (hasUnsavedChanges) {
        if (!confirm('Есть несохранённые изменения. Закрыть?')) return;
    }
    closeModal();
}

function showToast(type, message) {
    const toast = document.createElement('div');
    toast.className = 'toast show';
    const isSuccess = type === 'success';
    const iconColor = isSuccess ? '#88dd88' : '#ff8888';
    toast.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="${iconColor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:8px;">
            ${isSuccess 
                ? `<path d="M20 6L9 17l-5-5"></path>` 
                : `<circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line>`}
        </svg>
        ${escapeHtml(message)}`;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
