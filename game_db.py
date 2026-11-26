"""Base de datos SQLite para Reino Arcano RPG."""

import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional


SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS welcomed_chats (
    chat_id INTEGER PRIMARY KEY,
    contact_id INTEGER,
    addr TEXT,
    welcomed_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS players (
    chat_id INTEGER PRIMARY KEY,
    contact_id INTEGER NOT NULL,
    addr TEXT DEFAULT '',
    name TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    xp INTEGER NOT NULL DEFAULT 0,
    xp_next INTEGER NOT NULL DEFAULT 100,
    hp INTEGER NOT NULL DEFAULT 120,
    max_hp INTEGER NOT NULL DEFAULT 120,
    mp INTEGER NOT NULL DEFAULT 60,
    max_mp INTEGER NOT NULL DEFAULT 60,
    atk INTEGER NOT NULL DEFAULT 14,
    mag INTEGER NOT NULL DEFAULT 14,
    def_stat INTEGER NOT NULL DEFAULT 8,
    res_stat INTEGER NOT NULL DEFAULT 8,
    crit INTEGER NOT NULL DEFAULT 10,
    spd INTEGER NOT NULL DEFAULT 12,
    energy INTEGER NOT NULL DEFAULT 100,
    gold INTEGER NOT NULL DEFAULT 80,
    crystals INTEGER NOT NULL DEFAULT 0,
    era_shards INTEGER NOT NULL DEFAULT 0,
    echoes INTEGER NOT NULL DEFAULT 0,
    corruption INTEGER NOT NULL DEFAULT 0,
    zone_id INTEGER NOT NULL DEFAULT 1,
    path_class TEXT NOT NULL DEFAULT 'Aprendiz',
    specialization TEXT NOT NULL DEFAULT '',
    secondary_class TEXT NOT NULL DEFAULT '',
    legacy_nodes TEXT NOT NULL DEFAULT '[]',
    pact_id TEXT NOT NULL DEFAULT '',
    crafting_spec TEXT NOT NULL DEFAULT '',
    craft_points INTEGER NOT NULL DEFAULT 0,
    elo INTEGER NOT NULL DEFAULT 1000,
    rebirth_count INTEGER NOT NULL DEFAULT 0,
    guild_id INTEGER DEFAULT NULL,
    castle_tier INTEGER NOT NULL DEFAULT 1,
    xdc_msg_id INTEGER DEFAULT NULL,
    debt_gold INTEGER NOT NULL DEFAULT 0,
    is_delinquent INTEGER NOT NULL DEFAULT 0,
    last_daily INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS zones (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    min_level INTEGER NOT NULL,
    max_level INTEGER NOT NULL,
    mana_tide TEXT NOT NULL,
    weather TEXT NOT NULL,
    prey_pop INTEGER NOT NULL DEFAULT 100,
    predator_pop INTEGER NOT NULL DEFAULT 30,
    corruption_echo INTEGER NOT NULL DEFAULT 0,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    item_key TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    rarity TEXT NOT NULL DEFAULT 'Comun',
    qty INTEGER NOT NULL DEFAULT 1,
    atk_bonus INTEGER NOT NULL DEFAULT 0,
    mag_bonus INTEGER NOT NULL DEFAULT 0,
    def_bonus INTEGER NOT NULL DEFAULT 0,
    lore TEXT DEFAULT '',
    equipped INTEGER NOT NULL DEFAULT 0,
    UNIQUE(chat_id, item_key, rarity, name)
);

CREATE TABLE IF NOT EXISTS combats (
    chat_id INTEGER PRIMARY KEY,
    enemy_name TEXT NOT NULL,
    enemy_hp INTEGER NOT NULL,
    enemy_max_hp INTEGER NOT NULL,
    enemy_atk INTEGER NOT NULL,
    enemy_def INTEGER NOT NULL,
    enemy_res INTEGER NOT NULL,
    enemy_spd INTEGER NOT NULL,
    xp_reward INTEGER NOT NULL,
    gold_reward INTEGER NOT NULL,
    zone_id INTEGER NOT NULL,
    is_boss INTEGER NOT NULL DEFAULT 0,
    is_dungeon INTEGER NOT NULL DEFAULT 0,
    shield_turns INTEGER NOT NULL DEFAULT 0,
    last_spell TEXT DEFAULT '',
    turn_num INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS factions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    rival_id TEXT DEFAULT '',
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS player_reputation (
    chat_id INTEGER NOT NULL,
    faction_id TEXT NOT NULL,
    rep INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(chat_id, faction_id)
);

CREATE TABLE IF NOT EXISTS guilds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    leader_chat_id INTEGER NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    gold_bank INTEGER NOT NULL DEFAULT 0,
    supplies INTEGER NOT NULL DEFAULT 100,
    walls_lv INTEGER NOT NULL DEFAULT 1,
    library_lv INTEGER NOT NULL DEFAULT 0,
    forge_lv INTEGER NOT NULL DEFAULT 0,
    altar_lv INTEGER NOT NULL DEFAULT 0,
    power_nodes INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS guild_nodes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    zone_id INTEGER NOT NULL,
    owner_guild_id INTEGER DEFAULT NULL,
    defense_hp INTEGER NOT NULL DEFAULT 500,
    max_defense_hp INTEGER NOT NULL DEFAULT 500
);

CREATE TABLE IF NOT EXISTS market_listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_chat_id INTEGER NOT NULL,
    seller_name TEXT NOT NULL,
    item_key TEXT NOT NULL,
    item_name TEXT NOT NULL,
    rarity TEXT NOT NULL,
    qty INTEGER NOT NULL DEFAULT 1,
    price_gold INTEGER NOT NULL,
    is_black_market INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS recipes (
    key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    ingredients TEXT NOT NULL,
    cost_points INTEGER NOT NULL DEFAULT 0,
    min_level INTEGER NOT NULL DEFAULT 15,
    atk_bonus INTEGER NOT NULL DEFAULT 0,
    mag_bonus INTEGER NOT NULL DEFAULT 0,
    def_bonus INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS player_discoveries (
    chat_id INTEGER NOT NULL,
    recipe_key TEXT NOT NULL,
    discovered_at INTEGER NOT NULL,
    PRIMARY KEY(chat_id, recipe_key)
);

CREATE TABLE IF NOT EXISTS dungeons (
    chat_id INTEGER PRIMARY KEY,
    seed INTEGER NOT NULL,
    room INTEGER NOT NULL DEFAULT 1,
    max_rooms INTEGER NOT NULL DEFAULT 5,
    log TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS world_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS world_ruins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_id INTEGER NOT NULL,
    hero_name TEXT NOT NULL,
    gold_loot INTEGER NOT NULL,
    item_name TEXT NOT NULL,
    claimed INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS raids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    boss_name TEXT NOT NULL,
    zone_id INTEGER NOT NULL,
    hp INTEGER NOT NULL,
    max_hp INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    started_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS raid_contributions (
    raid_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    damage INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(raid_id, chat_id)
);

CREATE TABLE IF NOT EXISTS era_chronicle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    era_name TEXT NOT NULL,
    author_name TEXT NOT NULL,
    entry TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
"""


class GameDB:
    def __init__(self, db_path: str) -> None:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=20.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA_SQL)
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        cur = self.conn.cursor()

        zones = [
            (1, "Arboleda de los Susurros", 1, 9, "Equilibrada", "Soleado", 120, 25, 0,
             "Bosque antiguo ideal para aprendices: recoleccion de hierbas, madera y combates iniciales."),
            (2, "Pantano de las Almas", 10, 19, "Alta Marea Arcana", "Niebla Espectral", 90, 45, 15,
             "Cienaga brumosa rica en Esencia Espectral y criaturas resistentes."),
            (3, "Canon de Cristal", 20, 29, "Alta Marea Arcana", "Tormenta Arcana", 70, 60, 10,
             "Desfiladero luminoso para crafteo de pociones, encantamientos y minerales raros."),
            (4, "Ciudadela Flotante", 30, 50, "Flujo Supremo", "Ventisca de Cristal", 60, 80, 25,
             "Fortaleza celeste de alto nivel: incursiones, mazmorras, arena PvP y guerras territoriales."),
        ]
        cur.executemany(
            """INSERT OR IGNORE INTO zones
            (id, name, min_level, max_level, mana_tide, weather, prey_pop, predator_pop, corruption_echo, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            zones,
        )

        factions = [
            ("conclave", "El Conclave de Cristal", "sombra", "Guardianes del orden arcano y el comercio justo."),
            ("sombra", "La Orden de la Sombra", "conclave", "Maestros de pactos prohibidos y contratos ocultos."),
            ("sanadores", "Sanadores Errantes", "", "Faccion oculta de alquimistas y purificadores de corrupcion."),
        ]
        cur.executemany(
            "INSERT OR IGNORE INTO factions (id, name, rival_id, description) VALUES (?, ?, ?, ?)",
            factions,
        )

        nodes = [
            (1, "Nodo Raiz Esmeralda", 1, None, 400, 400),
            (2, "Nodo Altar Espectral", 2, None, 650, 650),
            (3, "Nodo Obelisco de Maná", 3, None, 900, 900),
            (4, "Nodo Trono Celeste", 4, None, 1300, 1300),
        ]
        cur.executemany(
            "INSERT OR IGNORE INTO guild_nodes (id, name, zone_id, owner_guild_id, defense_hp, max_defense_hp) VALUES (?, ?, ?, ?, ?, ?)",
            nodes,
        )

        recipes = [
            ("pocion_hp", "Pocion de Vida Arcana", "consumible", json.dumps({"hierba": 2}), 0, 1, 0, 0, 0),
            ("pocion_mp", "Elixir de Mana", "consumible", json.dumps({"esencia": 1, "hierba": 1}), 0, 10, 0, 0, 0),
            ("hoja_espectral", "Espada Espectral", "arma", json.dumps({"mineral": 3, "esencia": 2}), 2, 15, 18, 8, 0),
            ("baculo_cristal", "Baculo de Cristal", "arma", json.dumps({"mineral": 2, "cristal_bruto": 2}), 3, 15, 6, 24, 0),
            ("coraza_runica", "Coraza Runica", "armadura", json.dumps({"mineral": 4, "esencia": 1}), 3, 15, 0, 4, 16),
            ("filo_eclipse", "Filo del Eclipse (Secreta)", "arma", json.dumps({"esencia": 3, "fragmento_antiguo": 1}), 5, 20, 26, 26, 4),
        ]
        cur.executemany(
            "INSERT OR IGNORE INTO recipes (key, name, category, ingredients, cost_points, min_level, atk_bonus, mag_bonus, def_bonus) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            recipes,
        )

        defaults = {
            "era_name": "Era I: La Plaga de Cristal",
            "era_day": "1",
            "lunar_phase": "Luna Creciente",
            "world_event": "Calma Arcana",
            "economy_multiplier": "1.0",
            "tick_counter": "0",
        }
        for k, v in defaults.items():
            cur.execute("INSERT OR IGNORE INTO world_state (key, value) VALUES (?, ?)", (k, v))

        cur.execute("SELECT COUNT(*) FROM raids WHERE active = 1")
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO raids (boss_name, zone_id, hp, max_hp, active, started_at) VALUES (?, ?, ?, ?, 1, ?)",
                ("Dragon de Cristal Abisal", 4, 2500, 2500, int(time.time())),
            )

        cur.execute("SELECT COUNT(*) FROM era_chronicle")
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO era_chronicle (era_name, author_name, entry, created_at) VALUES (?, ?, ?, ?)",
                ("Era I: La Plaga de Cristal", "Director del Mundo", "Las puertas de la Arboleda de los Susurros se han abierto para nuevos aventureros.", int(time.time())),
            )

        self.conn.commit()

    def is_welcomed(self, chat_id: int) -> bool:
        row = self.conn.execute("SELECT 1 FROM welcomed_chats WHERE chat_id = ?", (chat_id,)).fetchone()
        return row is not None

    def mark_welcomed(self, chat_id: int, contact_id: int, addr: str = "") -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO welcomed_chats (chat_id, contact_id, addr, welcomed_at) VALUES (?, ?, ?, ?)",
            (chat_id, contact_id, addr, int(time.time())),
        )
        self.conn.commit()

    def get_player(self, chat_id: int) -> Optional[Dict[str, Any]]:
        row = self.conn.execute("SELECT * FROM players WHERE chat_id = ?", (chat_id,)).fetchone()
        return dict(row) if row else None

    def get_world_state(self) -> Dict[str, str]:
        rows = self.conn.execute("SELECT key, value FROM world_state").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def set_world_state(self, key: str, value: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO world_state (key, value) VALUES (?, ?)", (key, value))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
