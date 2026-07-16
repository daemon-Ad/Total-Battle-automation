document.addEventListener('DOMContentLoaded', () => {
    fetchLeaderboard();
});

async function fetchLeaderboard() {
    const loadingEl = document.getElementById('loading');
    const tbody = document.getElementById('leaderboard-body');
    
    try {
        const response = await fetch('/api/leaderboard');
        const result = await response.json();
        
        if (result.status === 'success') {
            loadingEl.classList.add('hidden');
            renderTable(result.data, tbody);
        } else {
            loadingEl.textContent = 'Failed to load data: ' + result.message;
        }
    } catch (error) {
        loadingEl.textContent = 'Error connecting to server.';
        console.error('Fetch error:', error);
    }
}

function renderTable(data, tbody) {
    tbody.innerHTML = '';
    
    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:var(--text-muted)">No chests logged this week yet.</td></tr>';
        return;
    }

    data.forEach((row, index) => {
        const tr = document.createElement('tr');
        
        // Rank formatting
        const rank = index + 1;
        let rankHtml = `<div class="rank-badge">${rank}</div>`;
        
        tr.innerHTML = `
            <td>${rankHtml}</td>
            <td class="player-name">${row.username}</td>
            <td>${row.common_chests || 0}</td>
            <td>${row.rare_chests || 0}</td>
            <td>${row.epic_chests || 0}</td>
            <td>${row.event_chests || 0}</td>
            <td class="score-col">${row.total_score || 0}</td>
        `;
        
        tbody.appendChild(tr);
    });
}
