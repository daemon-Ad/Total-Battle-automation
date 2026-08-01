document.addEventListener('DOMContentLoaded', () => {
    // --- Global State ---
    let currentSortBy = 'total_score';
    let currentOrder = 'desc';
    let weeklyGoal = 700; // default, overwritten by fetch
    
    // --- Analytics State ---
    let analyticsData = null;
    let donutChartInst = null;
    let trendChartInst = null;
    let sourceChartInst = null;
    let currentTrendView = 'daily';
    let currentSourceView = 'daily';
    
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

    
    const af = document.getElementById("analytics-week-select");
    if(af) af.addEventListener("change", loadAnalytics);
    const lt = document.getElementById("leaderboard-timeframe");
    const lw = document.getElementById("leaderboard-week-select");
    if(lt) lt.addEventListener("change", () => {
        const val = lt.value;
        const lw = document.getElementById("leaderboard-week-select");
        if(val === 'daily') {
            lw.options[0].text = "Current Day";
            lw.options[1].text = "Previous Day";
            lw.options[2].text = "2 Days Ago";
        } else if(val === 'monthly') {
            lw.options[0].text = "Current Month";
            lw.options[1].text = "Previous Month";
            lw.options[2].text = "2 Months Ago";
        } else if(val === 'overall') {
            lw.options[0].text = "All Time";
            lw.options[1].text = "-";
            lw.options[2].text = "-";
        } else {
            lw.options[0].text = "Current Week";
            lw.options[1].text = "Previous Week";
            lw.options[2].text = "2 Weeks Ago";
        }
        fetchLeaderboard();
    });
    if(lw) lw.addEventListener("change", () => fetchLeaderboard());
    const hp = document.getElementById("home-performers-timeframe");
    if(hp) hp.addEventListener("change", loadPerformers);

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

    document.querySelectorAll('.back-to-home-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            switchView('home-view');
        });
    });

    document.getElementById('global-back-btn').addEventListener('click', (e) => {
        e.preventDefault();
        // If we are on player details, go back to leaderboard. Otherwise go home.
        if (document.getElementById('player-details-view').classList.contains('active')) {
            switchView('leaderboard-view');
        } else {
            switchView('home-view');
        }
    });

    
async function loadPerformers() {
    const timeframe = document.getElementById("home-performers-timeframe")?.value || "weekly";
    try {
        const response = await fetch(`/api/leaderboard?sort_by=total_score&order=desc&timeframe=${timeframe}&offset=0`);
        const data = await response.json();
        if (data.status === 'success') {
            const players = data.data;
            const top10 = players.slice(0, 10);
            const bottom10 = players.slice(-10).reverse();
            
            let topHtml = "";
            top10.forEach((p, i) => {
                topHtml += `<tr><td>${i+1}</td><td>${p.username}</td><td>${p.total_score}</td></tr>`;
            });
            document.getElementById("top-performers-body").innerHTML = topHtml;
            
            let botHtml = "";
            bottom10.forEach((p, i) => {
                botHtml += `<tr><td>${players.length - i}</td><td>${p.username}</td><td>${p.total_score}</td></tr>`;
            });
            document.getElementById("bottom-performers-body").innerHTML = botHtml;
        }
    } catch(e) { console.error(e); }
}

    function switchView(viewId) {
        views.forEach(view => view.classList.remove('active'));
        document.getElementById(viewId).classList.add('active');
        
        navLinks.forEach(nav => nav.classList.remove('active'));
        const activeNav = document.querySelector(`.nav-links li[data-view="${viewId}"]`);
        if(activeNav) activeNav.classList.add('active');

        // Global Back Button visibility
        const backBtn = document.getElementById('global-back-btn');
        if (viewId === 'home-view') {
            loadPerformers();
            backBtn.style.display = 'none';
        } else {
            backBtn.style.display = 'flex';
        }

        if (viewId === 'reports-view') loadReportsPreview();
        if (viewId === 'analytics-view') loadAnalytics();
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
    
    async function fetchLeaderboard(searchVal = "") {
        const timeframe = document.getElementById("leaderboard-timeframe")?.value || "weekly";
        const offset = document.getElementById("leaderboard-week-select")?.value || "0";
        const loadingEl = document.getElementById('leaderboard-loading');
        const tbody = document.getElementById('leaderboard-body');
        loadingEl.classList.remove('hidden');
        
        const searchParam = searchVal ? `&search=${encodeURIComponent(searchVal)}` : '';
        
        try {
            const response = await fetch(`/api/leaderboard?sort_by=${currentSortBy}&order=${currentOrder}&timeframe=${timeframe}&offset=${offset}${searchParam}`);
            const result = await response.json();
            
            if (result.status === 'success') {
                tbody.innerHTML = '';
                if (result.data.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="10">No data found.</td></tr>`;
                    return;
                }
                
                result.data.forEach((p, index) => {
                    // Number Formatting K
                    let formattedScore = p.total_score >= 1000 ? (p.total_score/1000).toFixed(1) + 'K' : p.total_score;
                    if(String(formattedScore).endsWith('.0K')) formattedScore = formattedScore.replace('.0K', 'K');
                    
                    let purePts = p.pure_crypt_points || 0;
                    let formattedPureScore = purePts >= 1000 ? (purePts/1000).toFixed(1) + 'K' : purePts;
                    if(String(formattedPureScore).endsWith('.0K')) formattedPureScore = formattedPureScore.replace('.0K', 'K');
                    
                    // Chests Logic
                    let totalChests = (p.common_chests||0) + (p.rare_chests||0) + (p.epic_chests||0) + (p.event_chests||0);
                    
                    // Status styling
                    let isWarn = false;
                    let isPass = false;
                    
                    if (timeframe === 'weekly') {
                        if (p.total_score < weeklyGoal - 500) {
                            isWarn = true;
                        } else if (p.total_score >= weeklyGoal) {
                            isPass = true;
                        }
                    }
                    
                    let rowClass = '';
                    let statusIcon = '';
                    if(isPass) {
                        rowClass = 'ct-target-pass';
                        statusIcon = "<i class='bx bx-check-circle' style='color: #065f46; font-size: 1.2rem;'></i>";
                    } else if (isWarn) {
                        rowClass = 'ct-target-warn';
                        statusIcon = "<i class='bx bx-error' style='color: #92400e; font-size: 1.2rem;'></i>";
                    }
                    
                    const tr = document.createElement('tr');
                    tr.className = rowClass;
                    tr.innerHTML = `
                        <td>${index + 1}</td>
                        <td><strong><a href="#" onclick="openPlayerHistory(${p.id}, '${p.username}'); return false;" style="color: inherit; text-decoration: underline; cursor: pointer;">${p.username}</a></strong></td>
                        <td>${formattedScore}</td>
                        <td>${statusIcon}</td>
                        <td>${totalChests}</td>
                        <td>${p.common_chests || 0}</td>
                        <td>${p.rare_chests || 0}</td>
                        <td>${p.epic_chests || 0}</td>
                        <td>${p.event_chests || 0}</td>
                        <td><strong>${formattedPureScore}</strong></td>
                    `;
                    tbody.appendChild(tr);
                });
            }
        } catch (error) {
            tbody.innerHTML = `<tr><td colspan="10">Network Error</td></tr>`;
        } finally {
            loadingEl.classList.add('hidden');
        }
    }

    // Leaderboard Event Listeners
    searchInput.addEventListener('input', debounce((e) => fetchLeaderboard(e.target.value), 300));
    
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

    let allManagementPlayers = [];
    let showPastMembers = false;

    // --- Player Management View Logic ---
    
    const pastBtn = document.getElementById("open-past-modal-btn");
    const closePast = document.getElementById("close-past-modal");
    if(pastBtn) pastBtn.addEventListener("click", () => {
        document.getElementById("past-members-modal").classList.remove("hidden");
        fetchPlayers(); // This updates allManagementPlayers
    });
    if(closePast) closePast.addEventListener("click", () => {
        document.getElementById("past-members-modal").classList.add("hidden");
    });

    async function fetchPlayers() {
        const loadingEl = document.getElementById('management-loading');
        
        loadingEl.classList.remove('hidden');

        try {
            const response = await fetch(`/api/players`);
            const result = await response.json();
            
            if (result.status === 'success') {
                allManagementPlayers = result.data;
                renderManagement();
            }
        } catch (error) {
            tbody.innerHTML = `<tr><td colspan="3">Network Error</td></tr>`;
        } finally {
            loadingEl.classList.add('hidden');
        }
    }

    document.getElementById('management-rank-filter').addEventListener('change', () => {
        renderManagement();
    });

    document.getElementById('management-search').addEventListener('input', () => {
        renderManagement();
    });

    function fuzzyMatch(pattern, str) {
        pattern = '.*' + pattern.split('').join('.*') + '.*';
        const re = new RegExp(pattern, 'i');
        return re.test(str);
    }

    
    function renderManagement() {
        const tbody = document.getElementById('management-body');
        const pastBody = document.getElementById('past-members-body');
        tbody.innerHTML = '';
        if(pastBody) pastBody.innerHTML = '';
        
        const filterRank = document.getElementById('management-rank-filter').value;
        const searchQuery = document.getElementById('management-search').value.trim().toLowerCase();
        
        const filteredPlayers = allManagementPlayers.filter(p => {
            const matchesRank = filterRank === 'All' || p.rank === filterRank;
            const matchesSearch = !searchQuery || fuzzyMatch(searchQuery, p.username);
            return matchesRank && matchesSearch;
        });

        let count = 0;
        filteredPlayers.forEach(p => {
            if (p.is_active === false) {
                if(pastBody) {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `<td>${p.username}</td><td><button class="btn-primary" onclick="reactivatePlayer(${p.id})">Activate</button></td>`;
                    pastBody.appendChild(tr);
                }
            } else {
                count++;
                let armyLevel = `G${p.guardsman_level || 0}-S${p.specialist_level || 0}-M${p.monster_level || 0}`;
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>#${p.id}</td>
                    <td>${p.username}</td>
                    <td><span class="rank-badge-text">${p.rank || 'Officer'}</span></td>
                    <td>${armyLevel}</td>
                    <td>
                        <button class="btn-edit" data-id="${p.id}" data-name="${p.username}" data-rank="${p.rank}"><i class='bx bx-edit'></i> Edit</button>
                        <button class="btn-danger" data-id="${p.id}"><i class='bx bx-trash'></i> Delete</button>
                    </td>
                `;
                tbody.appendChild(tr);
            }
        });

        const totalBadge = document.getElementById('management-total-players');
        if (totalBadge) totalBadge.innerText = `${count} Players`;

        tbody.querySelectorAll('.btn-edit').forEach(btn => {
            btn.addEventListener('click', () => editPlayer(btn.dataset.id, btn.dataset.name, btn.dataset.rank));
        });
        tbody.querySelectorAll('.btn-danger').forEach(btn => {
            btn.addEventListener('click', () => deletePlayer(btn.dataset.id));
        });
    }
    
    window.reactivatePlayer = async function(id) {
        if(!confirm("Reactivate this past member?")) return;
        try {
            const response = await fetch(`/api/players/${id}/reactivate`, { method: 'POST', headers: {'Authorization': 'Basic ' + btoa('Shanks:shanks123')} });
            if (response.ok) { fetchPlayers(); }
        } catch(e) {}
    }


    document.getElementById('add-player-submit-btn').addEventListener('click', async () => {
        const input = document.getElementById('new-player-input');
        const rankInput = document.getElementById('new-player-rank');
        const name = input.value.trim();
        const rank = rankInput.value;
        
        const guardsman = parseInt(document.getElementById('new-player-guardsman').value || 0);
        const specialist = parseInt(document.getElementById('new-player-specialist').value || 0);
        const monster = parseInt(document.getElementById('new-player-monster').value || 0);
        
        if (!name) return;
        
        const response = await fetch('/api/players', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': 'Basic ' + btoa('Shanks:shanks123') },
            body: JSON.stringify({ 
                username: name, 
                rank: rank,
                guardsman_level: guardsman,
                specialist_level: specialist,
                monster_level: monster
            })
        });
        
        const result = await response.json();
        if (result.status === 'error') {
            alert("Error adding player: " + result.message);
        } else {
            input.value = '';
            document.getElementById('new-player-rank').value = 'Veteran';
            document.getElementById('new-player-guardsman').value = '0';
            document.getElementById('new-player-specialist').value = '0';
            document.getElementById('new-player-monster').value = '0';
            document.getElementById('add-player-modal').classList.add('hidden');
            fetchPlayers();
        }
    });

    
    const openAddBtn = document.getElementById("open-add-modal-btn");
    const closeAddBtn = document.getElementById("close-add-modal");
    if(openAddBtn) openAddBtn.addEventListener("click", () => document.getElementById("add-player-modal").classList.remove("hidden"));
    if(closeAddBtn) closeAddBtn.addEventListener("click", () => document.getElementById("add-player-modal").classList.add("hidden"));

    let currentEditingPlayerId = null;

    function editPlayer(id, oldName, oldRank) {
        currentEditingPlayerId = id;
        document.getElementById('edit-player-name').value = oldName;
        document.getElementById('edit-player-rank').value = oldRank || 'Officer';
        document.getElementById('edit-player-modal').classList.remove('hidden');
    }

    document.getElementById('cancel-edit-btn').addEventListener('click', () => {
        document.getElementById('edit-player-modal').classList.add('hidden');
        currentEditingPlayerId = null;
    });

    document.getElementById('save-edit-btn').addEventListener('click', async () => {
        if (!currentEditingPlayerId) return;
        
        const newName = document.getElementById('edit-player-name').value.trim();
        const newRank = document.getElementById('edit-player-rank').value;
        
        if (!newName) return;
        
        await fetch(`/api/players/${currentEditingPlayerId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: newName, rank: newRank })
        });
        
        document.getElementById('edit-player-modal').classList.add('hidden');
        currentEditingPlayerId = null;
        fetchPlayers();
    });

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

    // --- Analytics Logic ---
    async function loadAnalytics() {
        const offset = document.getElementById("analytics-week-select")?.value || "0";
        try {
            const response = await fetch(`/api/analytics?offset=${offset}`);
            const result = await response.json();
            if (result.status === 'success') {
                analyticsData = result.data;
                renderAnalytics();
            }
        } catch (e) {
            console.error("Failed to load analytics:", e);
        }
    }

    function renderAnalytics() {
        if (!analyticsData) return;

        // 1. Targets
        const targetPercentStr = analyticsData.targets.total_goal > 0 
            ? ((analyticsData.targets.total_score / analyticsData.targets.total_goal) * 100).toFixed(0) 
            : 0;
        document.getElementById('target-percent').textContent = targetPercentStr + '%';
        if(analyticsData.week_label) {
            const h = document.querySelector('#analytics-view .view-header p');
            if(h) h.textContent = `Detailed breakdown for ${analyticsData.week_label}`;
        }
    
        document.getElementById('target-text').textContent = `${analyticsData.targets.total_score} / ${analyticsData.targets.total_goal} points`;
        document.getElementById('target-bar').style.width = Math.min(targetPercentStr, 100) + '%';

        // 2. Summary
        document.getElementById('needs-attention-count').textContent = analyticsData.summary.needs_attention_count;
        document.getElementById('total-members-text').textContent = analyticsData.summary.total_members;

        if (donutChartInst) donutChartInst.destroy();
        const ctxDonut = document.getElementById('donutChart').getContext('2d');
        donutChartInst = new Chart(ctxDonut, {
            type: 'doughnut',
            data: {
                labels: ['On Track', 'Needs Attention'],
                datasets: [{
                    data: [analyticsData.summary.on_track_count, analyticsData.summary.needs_attention_count],
                    backgroundColor: ['#10b981', '#f59e0b'],
                    borderWidth: 0,
                    hoverOffset: 4
                }]
            },
            options: { cutout: '75%', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } }
        });

        // 3. Lists
        const renderList = (containerId, players, isAttention) => {
            const container = document.getElementById(containerId);
            container.innerHTML = players.map(p => {
                const percent = Math.min((p.score / p.goal) * 100, 100).toFixed(0);
                return `
                    <div class="member-item ${isAttention ? 'needs-attention' : ''}">
                        <div class="member-info">
                            <h4>${p.username}</h4>
                            <p>${isAttention ? Math.abs(p.diff) + ' points to go' : '+' + p.diff + ' over'}</p>
                        </div>
                        <div class="member-stats">
                            ${p.score} / ${p.goal}
                            <p>${percent}%</p>
                        </div>
                    </div>
                    <div class="member-progress-bg">
                        <div class="member-progress-fill" style="width: ${percent}%"></div>
                    </div>
                `;
            }).join('');
        };
        
        // Render only the Needs Attention list
        renderList('needs-attention-list', analyticsData.summary.needs_attention_players, true);

        // 4. Trends
        renderTrends();

        // 5. Sources
        renderSources();
    }

    function renderSources() {
        if (!analyticsData) return;
        
        const rawData = analyticsData.sources[currentSourceView] || [];
        
        if (sourceChartInst) sourceChartInst.destroy();
        const ctxSource = document.getElementById('sourceChart').getContext('2d');
        sourceChartInst = new Chart(ctxSource, {
            type: 'bar',
            data: {
                labels: rawData.map(s => s.category),
                datasets: [{
                    label: 'Chests',
                    data: rawData.map(s => s.count),
                    backgroundColor: ['#6366f1', '#10b981', '#ef4444', '#6b7280', '#06b6d4', '#3b82f6', '#d946ef']
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: '#9ca3af' } },
                    y: { grid: { display: false }, ticks: { color: '#e5e7eb' } }
                }
            }
        });
    }

    function renderTrends() {
        if (!analyticsData) return;
        const dataKey = currentTrendView; // 'daily' or 'weekly'
        const rawData = analyticsData.trends[dataKey];

        if (trendChartInst) trendChartInst.destroy();
        const ctxTrend = document.getElementById('trendChart').getContext('2d');
        
        trendChartInst = new Chart(ctxTrend, {
            type: 'line',
            data: {
                labels: rawData.map(d => d.time_label),
                datasets: [
                    {
                        label: 'Points Score',
                        data: rawData.map(d => d.score),
                        borderColor: '#a855f7',
                        backgroundColor: '#a855f7',
                        yAxisID: 'y1',
                        tension: 0.4
                    },
                    {
                        label: 'Chests Count',
                        data: rawData.map(d => d.chests),
                        borderColor: '#10b981',
                        backgroundColor: '#10b981',
                        yAxisID: 'y',
                        tension: 0.4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: { legend: { labels: { color: '#e5e7eb' } } },
                scales: {
                    x: { grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: '#9ca3af' } },
                    y: { type: 'linear', display: true, position: 'left', grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: '#10b981' } },
                    y1: { type: 'linear', display: true, position: 'right', grid: { drawOnChartArea: false }, ticks: { color: '#a855f7' } }
                }
            }
        });
    }

    // Trend toggles
    const trendDailyBtn = document.getElementById('trend-daily-btn');
    if (trendDailyBtn) {
        trendDailyBtn.addEventListener('click', (e) => {
            currentTrendView = 'daily';
            trendDailyBtn.classList.add('active');
            renderTrends();
        });
    }
    
    

    // Source toggles
    ['daily', 'weekly', 'monthly'].forEach(view => {
        const btn = document.getElementById(`source-${view}-btn`);
        if(btn) {
            btn.addEventListener('click', () => {
                currentSourceView = view;
                ['daily', 'weekly', 'monthly'].forEach(v => {
                    document.getElementById(`source-${v}-btn`).classList.remove('active');
                });
                btn.classList.add('active');
                renderSources();
            });
        }
    });
});


    // --- Player History Modal Logic ---
    window.openPlayerHistory = async function(playerId, username) {
        const modal = document.getElementById('player-history-modal');
        const title = document.getElementById('ph-title');
        const tbody = document.getElementById('ph-tbody');
        
        title.textContent = `${username}'s Chest History`;
        tbody.innerHTML = '<tr><td colspan="4">Loading...</td></tr>';
        modal.classList.remove('hidden');
        
        try {
            const response = await fetch(`/api/players/${playerId}/chests`);
            const result = await response.json();
            
            if (result.status === 'success') {
                tbody.innerHTML = '';
                if (result.data.chests.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="4">No chests logged.</td></tr>';
                    return;
                }
                
                result.data.chests.forEach(chest => {
                    const tr = document.createElement('tr');
                    const dateObj = new Date(chest.acquired_at);
                    
                    // Simple formatting without seconds
                    const dateStr = dateObj.toLocaleDateString();
                    const timeStr = dateObj.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
                    
                    let typeColor = 'var(--text-secondary)';
                    if(chest.chest_type === 'rare') typeColor = '#3b82f6';
                    if(chest.chest_type === 'epic' || chest.chest_type === 'event') typeColor = '#a855f7';
                    
                    tr.innerHTML = `
                        <td><span style="color: ${typeColor}; text-transform: capitalize;">${chest.chest_type}</span> <br><small style="color: var(--text-secondary)">${chest.chest_title || chest.source}</small></td>
                        <td>${chest.chest_level}</td>
                        <td><strong>${chest.points}</strong></td>
                        <td>${dateStr} <br><small>${timeStr}</small></td>
                    `;
                    tbody.appendChild(tr);
                });
            } else {
                tbody.innerHTML = '<tr><td colspan="4">Failed to load history.</td></tr>';
            }
        } catch(e) {
            tbody.innerHTML = '<tr><td colspan="4">Network error.</td></tr>';
        }
    };

    window.closePlayerHistory = function() {
        document.getElementById('player-history-modal').classList.add('hidden');
    };


    // --- Reports View Logic ---
    const reportsWeekSelect = document.getElementById("reports-week-select");
    if(reportsWeekSelect) reportsWeekSelect.addEventListener("change", loadReportsPreview);

    window.triggerDirectDownload = function(url) {
        const a = document.createElement('a');
        a.href = url;
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    };

    window.downloadBothWeeklyReports = function() {
        const offset = document.getElementById("reports-week-select")?.value || "0";
        window.triggerDirectDownload(`/api/reports/normal-weekly?offset=${offset}`);
        setTimeout(() => {
            window.triggerDirectDownload(`/api/reports/pure-crypting?offset=${offset}`);
        }, 600);
    };

    window.downloadReport = function(endpoint) {
        const offset = document.getElementById("reports-week-select")?.value || "0";
        window.triggerDirectDownload(`${endpoint}?offset=${offset}`);
    };

    window.loadReportsPreview = async function() {
        const offset = document.getElementById("reports-week-select")?.value || "0";
        try {
            const response = await fetch(`/api/reports/preview?offset=${offset}`);
            const result = await response.json();
            
            if (result.status === 'success') {
                renderEventPreview("olympus", result.olympus);
                renderEventPreview("ragnarok", result.ragnarok);
                renderEventPreview("ancients", result.ancients);
            }
        } catch(e) {
            console.error("Failed to load reports preview:", e);
        }
    };

    function renderEventPreview(eventKey, eventData) {
        const infoEl = document.getElementById(`${eventKey}-window-info`);
        const tbody = document.getElementById(`${eventKey}-preview-body`);
        
        if (!infoEl || !tbody) return;
        
        if (eventData.event_start) {
            const s = new Date(eventData.event_start).toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'});
            const e = new Date(eventData.event_end).toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'});
            infoEl.innerHTML = `<span style="color: var(--primary-hover); font-weight: 500;">Active Window:</span> ${s} to ${e}`;
        } else {
            infoEl.innerHTML = `<span style="color: var(--text-secondary);">No event logged in past 14 days</span>`;
        }
        
        tbody.innerHTML = '';
        if (!eventData.data || eventData.data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3">No active players</td></tr>';
            return;
        }
        
        eventData.data.forEach(item => {
            const tr = document.createElement('tr');
            const isYes = item.participated === "Yes";
            const badge = isYes 
                ? `<span style="color: #10b981; font-weight: 600;"><i class='bx bx-check'></i> Yes</span>` 
                : `<span style="color: var(--text-secondary);">No</span>`;
                
            tr.innerHTML = `
                <td><strong>${item.username}</strong></td>
                <td>${badge}</td>
                <td>${item.chest_count}</td>
            `;
            tbody.appendChild(tr);
        });
    }
