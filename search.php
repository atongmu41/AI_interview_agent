<?php
require_once __DIR__ . '/core/auth_init.php';

$user_id = $_SESSION['user_id'];
$sid_param = !empty($current_sid) ? '?sid=' . urlencode($current_sid) : '';
$sid_amp = !empty($current_sid) ? '&sid=' . urlencode($current_sid) : '';

$notification_count = 0;
$stmt = $conn->prepare("SELECT COUNT(*) FROM notifications WHERE user_id=? AND read_at IS NULL");
$stmt->bind_param("i", $user_id);
$stmt->execute();
$notification_count = (int)$stmt->get_result()->fetch_row()[0];

$myRole = '';
$stmt = $conn->prepare("SELECT role FROM users WHERE id=?");
$stmt->bind_param("i", $user_id);
$stmt->execute();
$r = $stmt->get_result()->fetch_assoc();
if ($r) $myRole = strtolower(trim((string)($r['role'] ?? '')));
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Search | DesignSphere</title>
    <link rel="stylesheet" href="assets/css/common.css">
    <link rel="stylesheet" href="assets/css/home.css">
    <link rel="stylesheet" href="assets/css/search.css">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="assets/js/append_sid.js"></script>
</head>
<body class="design-home-body search-page-body">

<aside class="left-sidebar" id="leftSidebar">
    <a href="home.php<?php echo $sid_param; ?>" class="sidebar-logo">
        <img src="assets/images/logo.png" alt="DesignSphere">
    </a>
    <nav class="sidebar-nav">
        <a href="home.php<?php echo $sid_param; ?>" class="nav-item">
            <span class="nav-icon"><img src="assets/images/icons/icon-home.svg" alt=""></span>
            <span>Home</span>
        </a>
        <a href="search.php<?php echo $sid_param; ?>" class="nav-item active">
            <span class="nav-icon"><img src="assets/images/icons/icon-search.svg" alt=""></span>
            <span>Search</span>
        </a>
        <a href="explore_designs.php<?php echo $sid_param; ?>" class="nav-item">
            <span class="nav-icon"><img src="assets/images/icons/icon-search.svg" alt=""></span>
            <span>Explore</span>
        </a>
        <a href="contests.php<?php echo $sid_param; ?>" class="nav-item">
            <span class="nav-icon"><img src="assets/images/icons/icon-trophy.svg" alt=""></span>
            <span>Contests</span>
        </a>
        <a href="saved.php<?php echo $sid_param; ?>" class="nav-item">
            <span class="nav-icon"><img src="assets/images/icons/icon-bookmark.svg" alt=""></span>
            <span>Saved</span>
        </a>
        <a href="messages.php<?php echo $sid_param; ?>" class="nav-item">
            <span class="nav-icon"><img src="assets/images/icons/icon-message.svg" alt=""></span>
            <span>Messages</span>
        </a>
        <a href="notifications.php<?php echo $sid_param; ?>" class="nav-item" title="Notifications">
            <span class="nav-icon"><img src="assets/images/icons/icon-bell.svg" alt=""></span>
            <span>Notifications</span>
            <?php if ($notification_count > 0): ?><span class="nav-badge"><?php echo $notification_count > 99 ? '99+' : $notification_count; ?></span><?php endif; ?>
        </a>
        <a href="profile.php?id=<?php echo (int)$user_id . $sid_amp; ?>" class="nav-item">
            <span class="nav-icon"><img src="assets/images/icons/icon-user.svg" alt=""></span>
            <span>Profile</span>
        </a>
        <a href="settings.php<?php echo $sid_param; ?>" class="nav-item">
            <span class="nav-icon"><img src="assets/images/icons/icon-settings.svg" alt=""></span>
            <span>Settings</span>
        </a>
    </nav>
    <a href="process/logout.php<?php echo $sid_param; ?>" class="sidebar-logout">Logout</a>
</aside>

<div class="search-page-wrap">
    <main class="search-main">
        <header class="search-hero">
            <h1>Discover</h1>
            <p>Find people and creators on DesignSphere</p>
        </header>

        <div class="search-bar-wrap">
            <div class="search-bar-inner">
                <input type="text" id="searchInput" class="search-input-premium" placeholder="Search designs, styles, or inspirations…" autocomplete="off">
            </div>
        </div>

        <div class="search-results-wrap">
            <div id="searchResults">
                <div class="search-empty" id="searchEmpty">Type to search for people</div>
                <div id="searchList" class="search-results-grid"></div>
            </div>
        </div>
    </main>
</div>

<script>
const searchInput = document.getElementById('searchInput');
const searchList = document.getElementById('searchList');
const searchEmpty = document.getElementById('searchEmpty');

let debounceTimer;
searchInput.addEventListener('input', function() {
    clearTimeout(debounceTimer);
    const q = this.value.trim();
    if (q.length < 1) {
        searchList.innerHTML = '';
        searchList.classList.remove('search-results-grid');
        searchEmpty.style.display = 'block';
        searchEmpty.textContent = 'Type to search for people';
        return;
    }
    debounceTimer = setTimeout(() => fetchUsers(q), 300);
});

async function fetchUsers(q) {
    searchEmpty.style.display = 'block';
    searchEmpty.textContent = 'Searching…';
    searchList.innerHTML = '';
    searchList.classList.remove('search-results-grid');
    const r = await fetch('api/api_search_users.php?q=' + encodeURIComponent(q) + (window.SID ? '&sid=' + encodeURIComponent(window.SID) : ''));
    const j = await r.json();
    if (j.success && j.users && j.users.length > 0) {
        searchEmpty.style.display = 'none';
        searchList.classList.add('search-results-grid');
        const sid = window.SID ? '&sid=' + encodeURIComponent(window.SID) : '';
        searchList.innerHTML = j.users.map(u => `
            <article class="search-card">
                <a href="profile.php?id=${u.id}${sid}" class="search-card-link">
                    <div class="search-card-image-wrap">
                        <img src="${escapeHtml(u.profile_picture)}" alt="${escapeHtml(u.full_name)}">
                    </div>
                    <div class="search-card-body">
                        <h3 class="search-card-title">${escapeHtml(u.full_name)}</h3>
                        <p class="search-card-meta">${u.followers_count} followers · ${escapeHtml(u.role || 'Member')}</p>
                    </div>
                </a>
                <div class="search-card-actions">
                    <button type="button" class="search-follow-btn ${u.i_follow ? 'following' : ''}" data-user-id="${u.id}" data-following="${u.i_follow ? '1' : '0'}">${u.i_follow ? 'Following' : 'Follow'}</button>
                </div>
            </article>
        `).join('');
        searchList.querySelectorAll('.search-follow-btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                toggleFollow(this, parseInt(this.dataset.userId, 10));
            });
        });
    } else {
        searchEmpty.textContent = q ? 'No people found' : 'Type to search for people';
    }
}

async function toggleFollow(btn, userId) {
    const fd = new FormData();
    fd.append('user_id', userId);
    const r = await fetch('api/api_follow.php' + (window.SID ? '?sid=' + encodeURIComponent(window.SID) : ''), { method: 'POST', body: fd });
    const j = await r.json();
    if (j.success) {
        btn.dataset.following = j.following ? '1' : '0';
        btn.classList.toggle('following', j.following);
        btn.textContent = j.following ? 'Following' : 'Follow';
    }
}

function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
}

(function() {
    const params = new URLSearchParams(window.location.search);
    const q = params.get('q');
    if (q && searchInput) {
        searchInput.value = q;
        fetchUsers(q.trim());
    }
})();
</script>

</body>
</html>
