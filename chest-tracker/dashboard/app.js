document.addEventListener('DOMContentLoaded', () => {
    // --- Global State ---
    let currentSortBy = 'total_score';
    let currentOrder = 'desc';
    let weeklyGoal = 700; // default, overwritten by fetch
    
    // --- DOM Elements ---
    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const navLinks = document.querySelectorAll('.nav-links li');
    const views = document.querySelectorAll('.view');
    const navBrandLink = document.getElementById('nav-brand-link');
    const homeCards = document.querySelectorAll('.nav-card');
    
    const searchInput = document.getElementById('search-input');
    const sortSelect = document.getElementById('sort-select');
    const sortOrderBtn = document.getElementById('sort-order-btn');
    
    // --- Initialization ---
    init();

    async function init() {
        await fetchSettings();
        switchView('home-view');
    }

    // --- Sidebar & Nav Logic ---
    sidebarToggle.addEventListener('click', () => {
        sidebar.classList.toggle('collapsed');
    });
    
    navBrandLink.addEventListener('click', (e) => {
        e.preventDefault();
        switchView('home-view');
    });
    
    homeCards.forEach(card => {
        card.addEventListener('click', (e) => {
            e.preventDefault();
            const viewId = card.getAttribute('data-target');
            switchView(viewId);
        });
    });

    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            const viewId = link.getAttribute('data-view');
            switchView(viewId);
        });
    });

    function switchView(viewId) {
        views.forEach(view => view.classList.remove('active'));
        document.getElementById(viewId).classList.add('active');
        
        navLinks.forEach(nav => nav.classList.remove('active'));
        const activeNav = document.querySelector(`.nav-links li[data-view="${viewId}"]`);
        if(activeNav) activeNav.classList.add('active');

        if (viewId === 'leaderboard-view') fetchLeaderboard();
        if (viewId === 'management-view') fetchPlayers();
        if (viewId === 'settings-view') populateSettingsForm();
        if (viewId === 'feedback-view') fetchAllFeedback();
    }

    // --- Settings Logic ---
    async function fetchSettings() {
        try {
            const response = await fetch('/api/settings');
            const result = await response.json();
            if (result.status === 'success' && result.data.weekly_goal) {
                weeklyGoal = parseInt(result.data.weekly_goal);
            }
        } catch (e) {
            console.error("Failed to load settings:", e);
        }
    }
    
    function populateSettingsForm() {
        document.getElementById('weekly-goal-input').value = weeklyGoal;
        document.getElementById('settings-status').textContent = '';
    }
    
    document.getElementById('save-settings-btn').addEventListener('click', async () => {
        const val = parseInt(document.getElementById('weekly-goal-input').value);
        const statusSpan = document.getElementById('settings-status');
        
        if (isNaN(val) || val < 0 || val > 90000) {
            statusSpan.style.color = '#ef4444';
            statusSpan.textContent = 'Invalid goal (must be 0 - 90,000)';
            return;
        }
        
        try {
            const response = await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ weekly_goal: val })
            });
            const result = await response.json();
            if (result.status === 'success') {
                weeklyGoal = val;
                statusSpan.style.color = '#10b981';
                statusSpan.textContent = 'Saved successfully!';
                setTimeout(() => { statusSpan.textContent = ''; }, 3000);
            } else {
                throw new Error(result.message);
            }
        } catch(e) {
            statusSpan.style.color = '#ef4444';
            statusSpan.textContent = 'Error saving.';
        }
    });

    // --- Feedback Logic ---
    document.getElementById('submit-feedback-btn').addEventListener('click', async () => {
        const username = document.getElementById('fb-username').value.trim();
        const content = document.getElementById('fb-content').value.trim();
        const statusSpan = document.getElementById('feedback-status');
        
        if (!username || !content) {
            statusSpan.style.color = '#ef4444';
            statusSpan.textContent = 'Please fill out both fields.';
            return;
        }
        
        try {
            const response = await fetch('/api/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, content })
            });
            if (response.ok) {
                statusSpan.style.color = '#10b981';
                statusSpan.textContent = 'Thank you for your feedback!';
                document.getElementById('fb-username').value = '';
                document.getElementById('fb-content').value = '';
                fetchAllFeedback(); // Refresh admin table below
                setTimeout(() => { statusSpan.textContent = ''; }, 3000);
            }
        } catch(e) {
            statusSpan.style.color = '#ef4444';
            statusSpan.textContent = 'Error submitting feedback.';
        }
    });
    
    async function fetchAllFeedback() {
        const tbody = document.getElementById('feedback-body');
        tbody.innerHTML = '<tr><td colspan="3">Loading...</td></tr>';
        try {
            const response = await fetch('/api/feedback');
            const result = await response.json();
            if(result.status === 'success') {
                tbody.innerHTML = '';
                if(result.data.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="3">No feedback yet.</td></tr>';
                    return;
                }
                result.data.forEach(fb => {
                    const tr = document.createElement('tr');
                    const date = new Date(fb.created_at).toLocaleString();
                    tr.innerHTML = `
                        <td style="white-space: nowrap; font-size: 0.9em; color: var(--text-secondary)">${date}</td>
                        <td><strong>${fb.username}</strong></td>
                        <td>${fb.content}</td>
                    `;
                    tbody.appendChild(tr);
                });
            }
        } catch(e) {
            tbody.innerHTML = '<tr><td colspan="3">Failed to load.</td></tr>';
        }
    }

    // --- Leaderboard View Logic ---
    async function fetchLeaderboard() {
        const loadingEl = document.getElementById('leaderboard-loading');
        const tbody = document.getElementById('leaderboard-body');
        loadingEl.classList.remove('hidden');
        tbody.innerHTML = '';
        
        const searchQuery = searchInput.value;
        const url = `/api/leaderboard?sort_by=${currentSortBy}&order=${currentOrder}&search=${encodeURIComponent(searchQuery)}`;
        
        try {
            const response = await fetch(url);
            const result = await response.json();
            
            if (result.status === 'success') {
                renderLeaderboard(result.data, tbody);
            } else {
                tbody.innerHTML = `<tr><td colspan="7">Error: ${result.message}</td></tr>`;
            }
        } catch (error) {
            tbody.innerHTML = `<tr><td colspan="7">Network Error</td></tr>`;
        } finally {
            loadingEl.classList.add('hidden');
        }
    }

    function renderLeaderboard(data, tbody) {
        if (data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;">No records found.</td></tr>';
            return;
        }

        data.forEach((row, index) => {
            const tr = document.createElement('tr');
            const rankHtml = `<div class="rank-badge">${index + 1}</div>`;
            
            // Apply Tints based on points vs goal
            if (row.total_score < weeklyGoal) {
                tr.classList.add('tint-warning');
            } else if (row.total_score >= 1000) {
                tr.classList.add('tint-success');
            }
            
            tr.innerHTML = `
                <td>${rankHtml}</td>
                <td><a href="#" class="player-name-link" data-id="${row.id}">${row.username}</a></td>
                <td>${row.common_chests}</td>
                <td>${row.rare_chests}</td>
                <td>${row.epic_chests}</td>
                <td>${row.event_chests}</td>
                <td class="score-col">${row.total_score}</td>
            `;
            
            // Attach click event for detailed view
            const link = tr.querySelector('.player-name-link');
            link.addEventListener('click', (e) => {
                e.preventDefault();
                openPlayerDetails(row.id);
            });
            
            tbody.appendChild(tr);
        });
    }

    // Leaderboard Event Listeners
    searchInput.addEventListener('input', debounce(fetchLeaderboard, 300));
    
    sortSelect.addEventListener('change', (e) => {
        currentSortBy = e.target.value;
        fetchLeaderboard();
    });

    sortOrderBtn.addEventListener('click', () => {
        currentOrder = currentOrder === 'desc' ? 'asc' : 'desc';
        const icon = sortOrderBtn.querySelector('i');
        icon.className = currentOrder === 'desc' ? 'bx bx-sort-down' : 'bx bx-sort-up';
        fetchLeaderboard();
    });

    // --- Player Details View Logic ---
    const backBtn = document.getElementById('back-to-leaderboard');
    backBtn.addEventListener('click', () => {
        switchView('leaderboard-view');
    });

    async function openPlayerDetails(playerId) {
        switchView('player-details-view');
        const loadingEl = document.getElementById('details-loading');
        const tbody = document.getElementById('details-body');
        const nameHeader = document.getElementById('details-player-name');
        
        loadingEl.classList.remove('hidden');
        tbody.innerHTML = '';
        nameHeader.textContent = "Loading...";

        try {
            const response = await fetch(`/api/players/${playerId}/chests`);
            const result = await response.json();
            
            if (result.status === 'success') {
                nameHeader.textContent = result.data.username + "'s Chests";
                renderPlayerDetails(result.data.chests, tbody);
            } else {
                tbody.innerHTML = `<tr><td colspan="6">Error: ${result.message}</td></tr>`;
            }
        } catch (error) {
            tbody.innerHTML = `<tr><td colspan="6">Network Error</td></tr>`;
        } finally {
            loadingEl.classList.add('hidden');
        }
    }

    function renderPlayerDetails(chests, tbody) {
        if (chests.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;">No chests logged yet.</td></tr>';
            return;
        }

        chests.forEach(chest => {
            const tr = document.createElement('tr');
            const date = new Date(chest.acquired_at).toLocaleString();
            
            // Assign color class based on chest type
            let colorClass = '';
            if (chest.chest_type === 'common') colorClass = 'chest-common';
            if (chest.chest_type === 'rare') colorClass = 'chest-rare';
            if (chest.chest_type === 'epic') colorClass = 'chest-epic';
            if (chest.chest_type === 'event') colorClass = 'chest-event';
            
            tr.innerHTML = `
                <td>${date}</td>
                <td><strong>${chest.chest_title}</strong></td>
                <td style="text-transform: capitalize" class="${colorClass}"><strong>${chest.chest_type}</strong></td>
                <td>Lvl ${chest.chest_level}</td>
                <td>${chest.source}</td>
                <td class="score-col">+${chest.points}</td>
            `;
            tbody.appendChild(tr);
        });
    }

    // --- Player Management View Logic ---
    async function fetchPlayers() {
        const loadingEl = document.getElementById('management-loading');
        const tbody = document.getElementById('management-body');
        
        loadingEl.classList.remove('hidden');
        tbody.innerHTML = '';

        try {
            const response = await fetch(`/api/players`);
            const result = await response.json();
            
            if (result.status === 'success') {
                renderManagement(result.data, tbody);
            }
        } catch (error) {
            tbody.innerHTML = `<tr><td colspan="3">Network Error</td></tr>`;
        } finally {
            loadingEl.classList.add('hidden');
        }
    }

    function renderManagement(players, tbody) {
        players.forEach(p => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>#${p.id}</td>
                <td>${p.username}</td>
                <td>
                    <button class="btn-edit" data-id="${p.id}" data-name="${p.username}"><i class='bx bx-edit'></i> Edit</button>
                    <button class="btn-danger" data-id="${p.id}"><i class='bx bx-trash'></i> Delete</button>
                </td>
            `;
            tbody.appendChild(tr);
        });

        tbody.querySelectorAll('.btn-edit').forEach(btn => {
            btn.addEventListener('click', () => editPlayer(btn.dataset.id, btn.dataset.name));
        });
        tbody.querySelectorAll('.btn-danger').forEach(btn => {
            btn.addEventListener('click', () => deletePlayer(btn.dataset.id));
        });
    }

    document.getElementById('add-player-btn').addEventListener('click', async () => {
        const input = document.getElementById('new-player-input');
        const name = input.value.trim();
        if (!name) return;
        
        await fetch('/api/players', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: name })
        });
        
        input.value = '';
        fetchPlayers();
    });

    async function editPlayer(id, oldName) {
        const newName = prompt(`Enter new name for ${oldName}:`, oldName);
        if (!newName || newName.trim() === '' || newName === oldName) return;
        
        await fetch(`/api/players/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: newName.trim() })
        });
        fetchPlayers();
    }

    async function deletePlayer(id) {
        if (!confirm("Are you sure? This will delete ALL chests logged by this player!")) return;
        
        await fetch(`/api/players/${id}`, {
            method: 'DELETE'
        });
        fetchPlayers();
    }

    // --- Utils ---
    function debounce(func, timeout = 300){
        let timer;
        return (...args) => {
            clearTimeout(timer);
            timer = setTimeout(() => { func.apply(this, args); }, timeout);
        };
    }
});
