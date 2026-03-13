/* DesignSphere Search – Premium UI */
:root {
  --search-bg: #0f0f14;
  --search-surface: rgba(255,255,255,0.92);
  --search-border: rgba(255,255,255,0.12);
  --search-accent: #c9a962;
  --search-accent-glow: rgba(201,153,98,0.35);
  --search-text: #1a1a1a;
  --search-text-muted: #6b7280;
  --search-radius: 16px;
  --search-shadow: 0 8px 32px rgba(0,0,0,0.08);
  --search-card-radius: 16px;
  --search-transition: 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.search-page-wrap {
  min-height: 100vh;
  display: flex;
  background: linear-gradient(165deg, #f8fafc 0%, #f1f5f9 50%, #eef2ff 100%);
  position: relative;
  overflow-x: hidden;
}

.search-page-wrap::before {
  content: "";
  position: absolute;
  inset: 0;
  background: 
    radial-gradient(ellipse 80% 50% at 50% 0%, rgba(201,153,98,0.06)),
    radial-gradient(ellipse 60% 40% at 100% 0%, rgba(148,163,184,0.04));
  pointer-events: none;
  z-index: 0;
}

.search-main {
  flex: 1;
  margin-left: 260px;
  padding: 2rem 2rem 3rem;
  min-height: 100vh;
  position: relative;
  z-index: 1;
}

.search-hero {
  text-align: center;
  padding: 3rem 1.5rem 2rem;
}

.search-hero h1 {
  font-size: 1.75rem;
  font-weight: 600;
  color: var(--search-text);
  letter-spacing: -0.02em;
  margin-bottom: 0.5rem;
}

.search-hero p {
  color: var(--search-text-muted);
  font-size: 0.95rem;
  margin-top: 0.25rem);
}

.search-bar-wrap {
  max-width: 560px;
  margin: 2rem auto 0;
  position: relative;
}

.search-bar-inner {
  position: relative;
  border-radius: var(--search-radius);
  background: var(--search-surface);
  border: 1px solid var(--search-border);
  box-shadow: var(--search-shadow);
  backdrop-filter: blur(12px);
  transition: box-shadow 0.3s, border-color 0.3s;
}

.search-bar-inner:focus-within {
  box-shadow: 0 0 0 0 3px var(--search-accent-glow);
  border-color: var(--search-accent);
}

.search-bar-inner::before {
  content: "";
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 1.25rem;
  height: 1.25rem;
  background: url("data:image/svg+xml,...") for icon;
  background-size: contain;
  background-repeat: no-repeat;
  pointer-events: none;
}

.search-input-premium {
  width: 100%;
  padding: 1rem 1rem 1rem 3rem;
  font-size: 1rem;
  border: none;
  background: transparent;
  color: var(--search-text);
  outline: none;
}

.search-input-premium::placeholder {
  color: var(--search-text-muted);
}

.search-results-wrap {
  max-width: 1200px;
  margin: 2.5rem auto 0;
  padding: 0 1.5rem;
}

.search-results-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1.5rem;
}

.search-card {
  background: var(--search-surface);
  border-radius: var(--search-card-radius);
  overflow: hidden;
  box-shadow: var(--search-shadow);
  border: 1px solid var(--search-border);
  transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.search-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 20px 40px rgba(0,0,0,0.12);
}

.search-card-link {
  display: block;
  text-decoration: none;
  color: inherit;
}

.search-card-image-wrap {
  position: relative;
  aspect-ratio: 1;
  overflow: hidden;
  background: linear-gradient(180deg, #f8fafc 0%, #f0f4f8 100%) for nav so we need to include home.css and add search can have its own layout structure". I'll use a similar structure to home: left-sidebar + main wrapper, then inside main: hero + results. 
- Search hero: gradient section with big search bar
- Results: grid of cards with image (avatar), title, meta, follow btn
- All IDs kept: searchInput, searchResults, searchEmpty, searchList, follow buttons with class for JS
- JS still builds .search-user-row or we change to .search-card and inner structure with .search-card-img, .search-card-title, .search-card-meta, .follow-btn
</think>

<｜tool▁calls▁begin｜><｜tool▁call▁begin｜>
Read