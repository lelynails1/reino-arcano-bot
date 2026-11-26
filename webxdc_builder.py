"""Genera la Mini-App interactiva arcano.xdc (< 60 KB)."""

import os
import zipfile

MANIFEST_TOML = """name = "Reino Arcano RPG"
source_code_url = "https://arcanechat.me"
"""

INDEX_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1.0" />
  <title>Reino Arcano RPG</title>
  <link rel="stylesheet" href="style.css" />
  <script src="webxdc.js"></script>
</head>
<body>
  <header class="topbar">
    <div class="brand">
      <img src="icon.png" alt="Icon" class="logo" />
      <div>
        <h1 id="hero-name">Reino Arcano</h1>
        <small id="hero-sub">Cargando heroe...</small>
      </div>
    </div>
    <button class="btn-mini" onclick="sendAction('refresh')">↻</button>
  </header>

  <nav class="tabs">
    <button class="tab active" onclick="showTab('hero', this)">Héroe</button>
    <button class="tab" onclick="showTab('map', this)">Mapa</button>
    <button class="tab" onclick="showTab('combat', this)">Combate</button>
    <button class="tab" onclick="showTab('bag', this)">Mochila</button>
    <button class="tab" onclick="showTab('world', this)">Mundo</button>
  </nav>

  <main>
    <section id="tab-hero" class="panel active">
      <div class="card">
        <div class="bars">
          <div><span>❤️ HP</span><strong id="stat-hp">-</strong></div>
          <div><span>💧 MP</span><strong id="stat-mp">-</strong></div>
          <div><span>⭐ XP</span><strong id="stat-xp">-</strong></div>
        </div>
        <div class="grid2" id="hero-stats"></div>
      </div>
      <div class="actions">
        <button class="btn primary" onclick="sendAction('explore')">🧭 Explorar Zona</button>
        <button class="btn" onclick="sendAction('mission')">📜 Misión Facción</button>
        <button class="btn" onclick="sendAction('dungeon')">🗝️ Mazmorra</button>
        <button class="btn warn" onclick="sendAction('raid')">🐉 Atacar World Boss</button>
      </div>
    </section>

    <section id="tab-map" class="panel">
      <div id="zones-list"></div>
    </section>

    <section id="tab-combat" class="panel">
      <div id="combat-box" class="card">No estás en combate activo. Pulsa Explorar.</div>
      <div class="actions">
        <button class="btn danger" onclick="sendAction('attack')">🗡️ Atacar</button>
        <button class="btn primary" onclick="sendAction('spell_fire')">🔥 Bola Fuego</button>
        <button class="btn" onclick="sendAction('spell_drain')">🩸 Drenar Vida</button>
        <button class="btn" onclick="sendAction('spell_shield')">🛡️ Escudo</button>
        <button class="btn" onclick="sendAction('potion_hp')">🧪 Poción HP</button>
        <button class="btn" onclick="sendAction('flee')">💨 Huir</button>
      </div>
    </section>

    <section id="tab-bag" class="panel">
      <div class="actions" style="margin-bottom:10px">
        <button class="btn primary" onclick="sendCraft('pocion_hp')">⚗️ Craft Poción HP</button>
        <button class="btn" onclick="sendCraft('hoja_espectral')">🗡️ Craft Espada</button>
      </div>
      <div id="inv-list" class="card">Cargando inventario...</div>
    </section>

    <section id="tab-world" class="panel">
      <div id="world-box" class="card">Cargando estado del mundo...</div>
    </section>

    <section class="card log-box">
      <h3>📜 Crónica de Acciones</h3>
      <pre id="action-log">Pulsa cualquier acción para sincronizar con el bot...</pre>
    </section>
  </main>

  <script src="app.js"></script>
</body>
</html>
"""

STYLE_CSS = """
:root { --bg:#0d1021; --card:#171c36; --border:#2b3363; --txt:#edf0ff; --mut:#9aa5d6; --acc:#7c5cff; --gold:#f5c542; --red:#e55353; }
* { box-sizing:border-box; margin:0; padding:0; font-family:system-ui,-apple-system,sans-serif; }
body { background:var(--bg); color:var(--txt); padding:10px; font-size:14px; }
.topbar { display:flex; justify-content:space-between; align-items:center; padding:8px 10px; background:var(--card); border:1px solid var(--border); border-radius:12px; margin-bottom:8px; }
.brand { display:flex; gap:10px; align-items:center; }
.logo { width:38px; height:38px; border-radius:10px; }
h1 { font-size:15px; color:var(--gold); }
small { color:var(--mut); font-size:12px; }
.tabs { display:flex; gap:4px; margin-bottom:10px; overflow-x:auto; }
.tab { flex:1; padding:8px 6px; border:1px solid var(--border); background:var(--card); color:var(--mut); border-radius:8px; font-size:12px; font-weight:600; cursor:pointer; }
.tab.active { background:var(--acc); color:#fff; border-color:var(--acc); }
.panel { display:none; }
.panel.active { display:block; }
.card { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:12px; margin-bottom:10px; }
.bars { display:grid; grid-template-columns:repeat(3,1fr); gap:6px; margin-bottom:10px; text-align:center; }
.bars div { background:#10142a; padding:6px; border-radius:8px; }
.bars span { display:block; font-size:11px; color:var(--mut); }
.grid2 { display:grid; grid-template-columns:1fr 1fr; gap:6px; font-size:13px; }
.actions { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:10px; }
.btn { padding:10px; border:1px solid var(--border); background:#20274c; color:#fff; border-radius:10px; font-weight:600; cursor:pointer; }
.btn.primary { background:var(--acc); border-color:var(--acc); }
.btn.danger { background:var(--red); border-color:var(--red); }
.btn.warn { background:#c77d1a; border-color:#c77d1a; }
.btn-mini { padding:6px 10px; background:#20274c; color:#fff; border:1px solid var(--border); border-radius:8px; cursor:pointer; }
.zone-card { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:10px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center; gap:8px; }
.log-box h3 { font-size:13px; color:var(--gold); margin-bottom:6px; }
pre { white-space:pre-wrap; font-family:inherit; font-size:12px; color:#d7ddf7; line-height:1.4; }
"""

APP_JS = """
let latestState = null;

function showTab(id, btn) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + id).classList.add('active');
  if (btn) btn.classList.add('active');
}

function sendAction(action, extra) {
  const payload = Object.assign({ action }, extra || {});
  if (window.webxdc) {
    window.webxdc.sendUpdate({ payload }, 'Accion: ' + action);
  }
}

function sendCraft(recipe_key) {
  sendAction('craft', { recipe_key });
}

function renderState(s) {
  latestState = s;
  const p = s.player;
  if (!p) return;
  document.getElementById('hero-name').textContent = p.name + ' (Nv.' + p.level + ')';
  document.getElementById('hero-sub').textContent = p.castle_name + ' · ' + p.path_class + (p.specialization ? ' / ' + p.specialization : '');
  document.getElementById('stat-hp').textContent = p.hp + '/' + p.max_hp;
  document.getElementById('stat-mp').textContent = p.mp + '/' + p.max_mp;
  document.getElementById('stat-xp').textContent = p.xp + '/' + p.xp_next;

  document.getElementById('hero-stats').innerHTML = [
    '🗡️ ATQ: ' + p.eff_atk,
    '🔮 MAG: ' + p.eff_mag,
    '🛡️ DEF: ' + p.eff_def,
    '💨 VEL: ' + p.spd,
    '🪙 Oro: ' + p.gold,
    '💎 Cristales: ' + p.crystals,
    '✨ Ecos: ' + p.echoes,
    '🌑 Corrupción: ' + p.corruption + '%'
  ].map(x => '<div>' + x + '</div>').join('');

  const c = s.combat;
  document.getElementById('combat-box').innerHTML = c
    ? '<strong>👹 ' + c.enemy_name + '</strong><br>HP: ' + c.enemy_hp + ' / ' + c.enemy_max_hp + ' · ATQ: ' + c.enemy_atk + ' · Turno ' + c.turn_num
    : 'No estás en combate activo. Pulsa Explorar.';

  document.getElementById('zones-list').innerHTML = (s.zones || []).map(z => {
    const unlocked = p.level >= z.min_level;
    return '<div class="zone-card"><div><strong>' + (unlocked ? '📍 ' : '🔒 ') + z.name + '</strong><br><small>Nv.' + z.min_level + '-' + z.max_level + ' · ' + z.weather + ' · ' + z.mana_tide + '</small></div>' +
      (unlocked ? '<button class="btn-mini" onclick="sendAction(\\'travel\\',{zone_id:' + z.id + '})">Ir</button>' : '<small>Bloq.</small>') + '</div>';
  }).join('');

  document.getElementById('inv-list').innerHTML = (s.inventory || []).length
    ? s.inventory.map(i => '<div>• <strong>' + i.name + '</strong> x' + i.qty + ' [' + i.rarity + ']' + (i.equipped ? ' ✅' : '') + '</div>').join('')
    : 'Mochila vacía.';

  const w = s.world || {};
  const r = s.raid;
  document.getElementById('world-box').innerHTML =
    '<strong>⏳ ' + (w.era_name || '') + '</strong> (Día ' + (w.era_day || 1) + ')<br>' +
    '🌙 ' + (w.lunar_phase || '') + '<br>⚡ ' + (w.world_event || '') +
    (r ? '<hr style="margin:8px 0;border-color:#2b3363">🐉 <strong>World Boss:</strong> ' + r.boss_name + ' (' + r.hp + '/' + r.max_hp + ' HP)' : '');

  if (s.last_log) {
    document.getElementById('action-log').textContent = s.last_log;
  }
}

if (window.webxdc) {
  window.webxdc.setUpdateListener(function(update) {
    if (update && update.payload && update.payload.type === 'state') {
      renderState(update.payload);
    }
  });
}
"""


def build_xdc(output_path: str, icon_path: str) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.toml", MANIFEST_TOML)
        zf.writestr("index.html", INDEX_HTML)
        zf.writestr("style.css", STYLE_CSS)
        zf.writestr("app.js", APP_JS)
        if os.path.exists(icon_path):
            zf.write(icon_path, "icon.png")
    return output_path
