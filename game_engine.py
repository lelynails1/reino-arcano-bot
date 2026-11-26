"""Motor completo de Reino Arcano RPG."""

import json
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from game_db import GameDB


CASTLE_TIERS = {
    1: ("Torre de la Arboleda", "castle_1.jpg"),
    2: ("Bastion del Pantano", "castle_2.jpg"),
    3: ("Fortaleza de Cristal", "castle_3.jpg"),
    4: ("Ciudadela Flotante", "castle_4.jpg"),
    5: ("Trono del Renacimiento", "castle_5.jpg"),
}

ZONE_MONSTERS = {
    1: [
        ("Lobo de Sombra", 55, 11, 4, 3, 11, 35, 18),
        ("Ciervo Corrupto", 70, 13, 5, 4, 13, 45, 22),
        ("Duende de la Arboleda", 60, 12, 4, 5, 14, 40, 25),
    ],
    2: [
        ("Espectro del Pantano", 130, 22, 8, 12, 16, 90, 48),
        ("Golem de Cieno", 170, 25, 14, 8, 10, 110, 55),
        ("Cazador de Almas", 150, 27, 9, 11, 19, 105, 60),
    ],
    3: [
        ("Elemental de Cristal", 240, 36, 15, 18, 18, 180, 95),
        ("Quimera Prismatica", 280, 40, 16, 15, 22, 210, 110),
        ("Centinela del Canon", 260, 38, 18, 14, 20, 195, 105),
    ],
    4: [
        ("Caballero de la Ciudadela", 390, 52, 22, 22, 24, 320, 175),
        ("Demonio del Eclipse", 440, 58, 20, 28, 27, 370, 210),
        ("Cazador de Sombras Mayor", 410, 55, 21, 24, 30, 350, 190),
    ],
}

WEATHERS = ["Soleado", "Tormenta Arcana", "Niebla Espectral", "Ventisca de Cristal"]
MANA_TIDES = ["Equilibrada", "Alta Marea Arcana", "Sequia de Mana"]
LUNAR_PHASES = ["Luna Nueva", "Luna Creciente", "Luna Llena", "Luna de Sangre"]


@dataclass
class ActionResult:
    text: str
    leveled_up: bool = False
    new_level: int = 1
    castle_tier: int = 1
    castle_name: str = ""
    castle_image: str = ""
    send_xdc: bool = False
    xdc_payload: Optional[Dict[str, Any]] = None


def castle_tier_for_level(level: int, rebirths: int = 0) -> int:
    if level >= 50 or rebirths > 0 and level >= 45:
        return 5
    if level >= 30:
        return 4
    if level >= 20:
        return 3
    if level >= 10:
        return 2
    return 1


def welcome_message(bot_name: str = "Reino Arcano RPG") -> str:
    return (
        f"🏰 *¡Bienvenido a {bot_name}!*\n"
        "🔒 Tu chat ha sido verificado con cifrado de extremo a extremo.\n\n"
        "📜 *Reglas sencillas del Reino:*\n"
        "1️⃣ Usa */start* para crear tu heroe y recibir tu Mini-App (.xdc).\n"
        "2️⃣ Explora zonas (*/mapa*, */explorar*), combate por turnos (*/atacar*, */lanzar*) y sube de nivel para mejorar tu Castillo.\n"
        "3️⃣ Desbloquea sendas al Nv.10, crafteo al Nv.15, especializacion al Nv.20, gremios al Nv.25, guerras/raids al Nv.30 y Renacimiento al Nv.50.\n"
        "4️⃣ Respeta las alianzas y cuida tu nivel de Corrupcion.\n\n"
        "⚡ Toca o escribe */start* ahora para comenzar tu aventura."
    )


class ArcanoEngine:
    def __init__(self, db: GameDB) -> None:
        self.db = db

    def _tick_world_director(self) -> Optional[str]:
        ws = self.db.get_world_state()
        ticks = int(ws.get("tick_counter", "0")) + 1
        self.db.set_world_state("tick_counter", str(ticks))
        note = None
        if ticks % 12 == 0:
            day = int(ws.get("era_day", "1")) + 1
            self.db.set_world_state("era_day", str(day))
            phase = LUNAR_PHASES[day % len(LUNAR_PHASES)]
            self.db.set_world_state("lunar_phase", phase)

            # Update dynamic weather & mana tides in zones
            for zid in (1, 2, 3, 4):
                w = random.choice(WEATHERS)
                m = random.choice(MANA_TIDES)
                self.db.conn.execute(
                    "UPDATE zones SET weather = ?, mana_tide = ? WHERE id = ?",
                    (w, m, zid),
                )

            # World Director checks economy gold inflation
            avg_row = self.db.conn.execute("SELECT AVG(gold) as ag FROM players").fetchone()
            avg_gold = avg_row["ag"] if avg_row and avg_row["ag"] else 0
            if avg_gold > 1500:
                self.db.set_world_state("world_event", "La Burbuja de Cristal estalla (precios +25%)")
                self.db.set_world_state("economy_multiplier", "1.25")
                note = "🌐 *Director del Mundo:* Exceso de oro detectado — ¡La Burbuja de Cristal ha estallado!"
            elif phase == "Luna de Sangre":
                self.db.set_world_state("world_event", "Luna de Sangre: Nigromantes +20% poder")
                self.db.set_world_state("economy_multiplier", "1.0")
                note = "🌑 *Director del Mundo:* ¡La Luna de Sangre ilumina el cielo!"
            else:
                self.db.set_world_state("world_event", "Flujo Estacional Estable")
                self.db.set_world_state("economy_multiplier", "1.0")
            self.db.conn.commit()
        return note

    def _ensure_player(self, chat_id: int, contact_id: int, addr: str, name: str) -> Tuple[Dict[str, Any], bool]:
        p = self.db.get_player(chat_id)
        if p:
            return p, False
        now = int(time.time())
        clean_name = (name or "Aventurero").strip()[:28] or "Aventurero"
        self.db.conn.execute(
            """INSERT INTO players (chat_id, contact_id, addr, name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (chat_id, contact_id, addr, clean_name, now, now),
        )
        # Starter items
        starter = [
            (chat_id, "pocion_hp", "Pocion de Vida Arcana", "consumible", "Comun", 3, 0, 0, 0, "Restaura 65 HP.", 0),
            (chat_id, "pocion_mp", "Elixir de Mana", "consumible", "Comun", 2, 0, 0, 0, "Restaura 35 MP.", 0),
            (chat_id, "espada_novato", "Daga del Aprendiz", "arma", "Comun", 1, 5, 2, 0, "Arma basica de la Arboleda.", 1),
            (chat_id, "hierba", "Hierba Luminosa", "material", "Comun", 3, 0, 0, 0, "Ingrediente de alquimia.", 0),
        ]
        self.db.conn.executemany(
            """INSERT OR IGNORE INTO inventory
            (chat_id, item_key, name, category, rarity, qty, atk_bonus, mag_bonus, def_bonus, lore, equipped)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            starter,
        )
        for fid in ("conclave", "sombra", "sanadores"):
            self.db.conn.execute(
                "INSERT OR IGNORE INTO player_reputation (chat_id, faction_id, rep) VALUES (?, ?, 0)",
                (chat_id, fid),
            )
        self.db.conn.commit()
        return self.db.get_player(chat_id), True

    def _equip_bonuses(self, chat_id: int) -> Tuple[int, int, int]:
        row = self.db.conn.execute(
            "SELECT COALESCE(SUM(atk_bonus),0) as a, COALESCE(SUM(mag_bonus),0) as m, COALESCE(SUM(def_bonus),0) as d "
            "FROM inventory WHERE chat_id = ? AND equipped = 1",
            (chat_id,),
        ).fetchone()
        return int(row["a"]), int(row["m"]), int(row["d"])

    def _add_item(
        self,
        chat_id: int,
        item_key: str,
        name: str,
        category: str,
        rarity: str = "Comun",
        qty: int = 1,
        atk_bonus: int = 0,
        mag_bonus: int = 0,
        def_bonus: int = 0,
        lore: str = "",
        equipped: int = 0,
    ) -> None:
        existing = self.db.conn.execute(
            "SELECT id, qty FROM inventory WHERE chat_id = ? AND item_key = ? AND rarity = ? AND name = ?",
            (chat_id, item_key, rarity, name),
        ).fetchone()
        if existing:
            self.db.conn.execute(
                "UPDATE inventory SET qty = qty + ? WHERE id = ?",
                (qty, existing["id"]),
            )
        else:
            self.db.conn.execute(
                """INSERT INTO inventory
                (chat_id, item_key, name, category, rarity, qty, atk_bonus, mag_bonus, def_bonus, lore, equipped)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (chat_id, item_key, name, category, rarity, qty, atk_bonus, mag_bonus, def_bonus, lore, equipped),
            )
        self.db.conn.commit()

    def _grant_xp(self, p: Dict[str, Any], xp_gain: int) -> Tuple[Dict[str, Any], bool, int]:
        nodes = json.loads(p["legacy_nodes"] or "[]")
        if "memoria_sangre" in nodes:
            xp_gain = int(xp_gain * 1.15)
        xp = p["xp"] + xp_gain
        level = p["level"]
        xp_next = p["xp_next"]
        max_hp = p["max_hp"]
        max_mp = p["max_mp"]
        atk = p["atk"]
        mag = p["mag"]
        def_s = p["def_stat"]
        res_s = p["res_stat"]
        spd = p["spd"]
        leveled = False

        while xp >= xp_next and level < 50:
            xp -= xp_next
            level += 1
            xp_next = int(xp_next * 1.28) + 30
            max_hp += 22
            max_mp += 10
            atk += 3
            mag += 3
            def_s += 2
            res_s += 2
            spd += 1
            leveled = True

        tier = castle_tier_for_level(level, p["rebirth_count"])
        hp = max_hp if leveled else p["hp"]
        mp = max_mp if leveled else p["mp"]
        self.db.conn.execute(
            """UPDATE players SET level=?, xp=?, xp_next=?, hp=?, max_hp=?, mp=?, max_mp=?,
            atk=?, mag=?, def_stat=?, res_stat=?, spd=?, castle_tier=?, updated_at=? WHERE chat_id=?""",
            (level, xp, xp_next, hp, max_hp, mp, max_mp, atk, mag, def_s, res_s, spd, tier, int(time.time()), p["chat_id"]),
        )
        self.db.conn.commit()
        return self.db.get_player(p["chat_id"]), leveled, tier

    def build_xdc_snapshot(self, chat_id: int) -> Dict[str, Any]:
        p = self.db.get_player(chat_id)
        if not p:
            return {"type": "state", "player": None}
        combat = self.db.conn.execute("SELECT * FROM combats WHERE chat_id = ?", (chat_id,)).fetchone()
        zones = [dict(z) for z in self.db.conn.execute("SELECT * FROM zones ORDER BY id").fetchall()]
        inv = [dict(i) for i in self.db.conn.execute("SELECT * FROM inventory WHERE chat_id = ? AND qty > 0", (chat_id,)).fetchall()]
        ws = self.db.get_world_state()
        raid = self.db.conn.execute("SELECT * FROM raids WHERE active = 1 ORDER BY id DESC LIMIT 1").fetchone()
        tier_name, _ = CASTLE_TIERS.get(p["castle_tier"], CASTLE_TIERS[1])
        ea, em, ed = self._equip_bonuses(chat_id)
        return {
            "type": "state",
            "player": {
                **p,
                "eff_atk": p["atk"] + ea,
                "eff_mag": p["mag"] + em,
                "eff_def": p["def_stat"] + ed,
                "castle_name": tier_name,
            },
            "combat": dict(combat) if combat else None,
            "zones": zones,
            "inventory": inv[:25],
            "world": ws,
            "raid": dict(raid) if raid else None,
        }

    def handle_command(
        self,
        chat_id: int,
        contact_id: int,
        addr: str,
        sender_name: str,
        raw_text: str,
    ) -> ActionResult:
        text = (raw_text or "").strip()
        if not text:
            return ActionResult(text="Escribe */menu* o */ayuda* para ver las opciones disponibles.")

        director_note = self._tick_world_director()
        parts = text.split()
        cmd = parts[0].lower()
        if "@" in cmd:
            cmd = cmd.split("@", 1)[0]
        args = parts[1:]

        p, created = self._ensure_player(chat_id, contact_id, addr, sender_name)

        if cmd == "/start":
            tier_name, _ = CASTLE_TIERS[p["castle_tier"]]
            msg = (
                f"⚔️ *¡Tu leyenda comienza, {p['name']}!*\n"
                f"📍 Zona inicial: *Arboleda de los Susurros* (Nv. 1–9)\n"
                f"🏰 Castillo actual: *{tier_name}* (Rango {p['castle_tier']})\n"
                f"❤️ HP: {p['hp']}/{p['max_hp']} · 💧 MP: {p['mp']}/{p['max_mp']} · 🪙 Oro: {p['gold']}\n\n"
                "🎒 Recibiste: *Daga del Aprendiz*, *3x Pocion de Vida*, *2x Elixir de Mana* y *3x Hierba Luminosa*.\n"
                "📱 Te envio tambien la Mini-App interactiva *Reino Arcano (.xdc)*.\n"
                "👉 Prueba ahora */explorar* para iniciar tu primer combate o recoleccion."
            )
            return ActionResult(text=msg, send_xdc=True, xdc_payload=self.build_xdc_snapshot(chat_id))

        if cmd in ("/yo", "/perfil"):
            return ActionResult(text=self._cmd_profile(p), xdc_payload=self.build_xdc_snapshot(chat_id))

        if cmd == "/menu":
            return ActionResult(text=self._cmd_menu(p), xdc_payload=self.build_xdc_snapshot(chat_id))

        if cmd == "/ayuda":
            return ActionResult(text=self._cmd_help())

        if cmd == "/app":
            return ActionResult(
                text="📱 Aqui tienes la Mini-App interactiva *Reino Arcano (.xdc)* sincronizada con tu personaje.",
                send_xdc=True,
                xdc_payload=self.build_xdc_snapshot(chat_id),
            )

        if cmd == "/mapa":
            return ActionResult(text=self._cmd_map(p))

        if cmd == "/explorar":
            res = self._cmd_explore(p, args)
            if director_note:
                res.text += f"\n\n{director_note}"
            res.xdc_payload = self.build_xdc_snapshot(chat_id)
            return res

        if cmd == "/atacar":
            res = self._cmd_combat_attack(p)
            res.xdc_payload = self.build_xdc_snapshot(chat_id)
            return res

        if cmd == "/lanzar":
            spell = args[0].lower() if args else "bola_fuego"
            res = self._cmd_combat_spell(p, spell)
            res.xdc_payload = self.build_xdc_snapshot(chat_id)
            return res

        if cmd == "/objeto":
            item_key = args[0].lower() if args else "pocion_hp"
            res = self._cmd_use_item(p, item_key)
            res.xdc_payload = self.build_xdc_snapshot(chat_id)
            return res

        if cmd == "/huir":
            res = self._cmd_flee(p)
            res.xdc_payload = self.build_xdc_snapshot(chat_id)
            return res

        if cmd == "/clase":
            return ActionResult(text=self._cmd_class(p, args), xdc_payload=self.build_xdc_snapshot(chat_id))

        if cmd == "/pacto":
            return ActionResult(text=self._cmd_pact(p, args), xdc_payload=self.build_xdc_snapshot(chat_id))

        if cmd == "/purificar":
            return ActionResult(text=self._cmd_purify(p), xdc_payload=self.build_xdc_snapshot(chat_id))

        if cmd == "/renacer":
            res = self._cmd_rebirth(p)
            res.xdc_payload = self.build_xdc_snapshot(chat_id)
            return res

        if cmd == "/inventario":
            return ActionResult(text=self._cmd_inventory(p))

        if cmd in ("/craft", "/recetas"):
            return ActionResult(text=self._cmd_craft(p, args), xdc_payload=self.build_xdc_snapshot(chat_id))

        if cmd == "/experimentar":
            return ActionResult(text=self._cmd_experiment(p, args), xdc_payload=self.build_xdc_snapshot(chat_id))

        if cmd == "/mercado":
            return ActionResult(text=self._cmd_market(p))

        if cmd == "/vender":
            return ActionResult(text=self._cmd_sell(p, args))

        if cmd == "/comprar":
            return ActionResult(text=self._cmd_buy(p, args))

        if cmd in ("/faccion", "/reputacion"):
            return ActionResult(text=self._cmd_faction(p, args))

        if cmd == "/mision":
            res = self._cmd_mission(p)
            res.xdc_payload = self.build_xdc_snapshot(chat_id)
            return res

        if cmd == "/gremio":
            return ActionResult(text=self._cmd_guild(p, args))

        if cmd == "/guerra":
            return ActionResult(text=self._cmd_war(p, args), xdc_payload=self.build_xdc_snapshot(chat_id))

        if cmd in ("/arena", "/desafiar"):
            return ActionResult(text=self._cmd_arena(p, args))

        if cmd in ("/raid", "/raids"):
            res = self._cmd_raid(p)
            res.xdc_payload = self.build_xdc_snapshot(chat_id)
            return res

        if cmd in ("/mazmorra", "/avanzar"):
            res = self._cmd_dungeon(p, cmd == "/avanzar")
            res.xdc_payload = self.build_xdc_snapshot(chat_id)
            return res

        if cmd in ("/top", "/guildtop", "/era", "/cronica", "/mundo", "/estado"):
            return ActionResult(text=self._cmd_meta(p, cmd))

        if cmd in ("/prestamo", "/negro"):
            return ActionResult(text=self._cmd_contracts(p, cmd, args))

        # Mensaje libre en chat privado sin comando reconocido
        return ActionResult(
            text=(
                f"✨ Saludos, *{p['name']}* (Nv.{p['level']}).\n"
                "Usa */explorar* para aventurarte, */yo* para ver tu personaje, */menu* para abrir todas las funciones o */app* para recibir la Mini-App `.xdc`."
            ),
            xdc_payload=self.build_xdc_snapshot(chat_id),
        )

    def _cmd_profile(self, p: Dict[str, Any]) -> str:
        ea, em, ed = self._equip_bonuses(p["chat_id"])
        tier_name, _ = CASTLE_TIERS[p["castle_tier"]]
        zone = self.db.conn.execute("SELECT name FROM zones WHERE id = ?", (p["zone_id"],)).fetchone()["name"]
        guild_name = "Sin gremio"
        if p["guild_id"]:
            g = self.db.conn.execute("SELECT name FROM guilds WHERE id = ?", (p["guild_id"],)).fetchone()
            if g:
                guild_name = g["name"]
        cls_txt = p["path_class"]
        if p["specialization"]:
            cls_txt += f" -> {p['specialization']}"
        if p["secondary_class"]:
            cls_txt += f" (+ {p['secondary_class']})"
        return (
            f"🧙 *{p['name']}* | Nv. *{p['level']}* ({p['xp']}/{p['xp_next']} XP)\n"
            f"🏰 Castillo (Tier {p['castle_tier']}): *{tier_name}*\n"
            f"🛡️ Senda: *{cls_txt}* | 🤝 Pacto: *{p['pact_id'] or 'Ninguno'}*\n"
            f"📍 Zona: *{zone}* | ⚔️ Gremio: *{guild_name}*\n\n"
            f"❤️ HP: {p['hp']}/{p['max_hp']}  |  💧 MP: {p['mp']}/{p['max_mp']}  |  ⚡ Energia: {p['energy']}/100\n"
            f"🗡️ ATQ: {p['atk']}+{ea}  |  🔮 MAG: {p['mag']}+{em}  |  🛡️ DEF: {p['def_stat']}+{ed}  |  💨 VEL: {p['spd']}\n"
            f"🪙 Oro: {p['gold']}  |  💎 Cristales: {p['crystals']}  |  ✨ Ecos: {p['echoes']}  |  🌑 Corrupcion: {p['corruption']}%\n"
            f"🏆 ELO Arena: {p['elo']}  |  🔄 Renacimientos: {p['rebirth_count']}"
        )

    def _cmd_menu(self, p: Dict[str, Any]) -> str:
        return (
            f"📜 *MENU DE REINO ARCANO* (Nv.{p['level']})\n\n"
            "🧭 *Aventura y Combate*\n"
            "• /mapa — Zonas, clima y flujo de mana\n"
            "• /explorar [1-4] — Recolectar o combatir\n"
            "• /atacar · /lanzar <hechizo> · /objeto · /huir\n"
            "• /mazmorra · /avanzar — Salas procedurales\n\n"
            "🧙 *Personaje y Poder*\n"
            "• /yo — Hoja completa y castillo\n"
            "• /clase — Elegir senda (Nv.10) y subclase (Nv.20)\n"
            "• /pacto — Pactos con entidades arcanas\n"
            "• /app — Recibir Mini-App interactiva (.xdc)\n\n"
            "⚒️ *Economia y Crafteo*\n"
            "• /inventario · /craft · /experimentar · /recetas\n"
            "• /mercado · /vender · /comprar · /negro · /prestamo\n\n"
            "🛡️ *Social, Facciones y Guerra*\n"
            "• /faccion · /mision · /gremio · /guerra\n"
            "• /arena · /desafiar · /raid · /top · /era · /mundo"
        )

    def _cmd_help(self) -> str:
        return (
            "📖 *GUIA RAPIDA DE REINO ARCANO*\n\n"
            "1. *Progresion de Zonas y Castillos:*\n"
            "   • Nv 1–9: Arboleda de los Susurros (Torre)\n"
            "   • Nv 10–19: Pantano de las Almas (Bastion + Senda)\n"
            "   • Nv 20–29: Canon de Cristal (Fortaleza + Subclase)\n"
            "   • Nv 30–49: Ciudadela Flotante (Raids, GvG, Arena)\n"
            "   • Nv 50: /renacer (Ecos, Legado y Clase Hibrida)\n\n"
            "2. *Combate por Turnos:*\n"
            "   Usa /explorar para hallar enemigos. En combate:\n"
            "   • /atacar (genera +10 MP)\n"
            "   • /lanzar bola_fuego | drenar_vida | escudo_arcano | eclipse\n"
            "   • /objeto pocion_hp | pocion_mp\n"
            "   • /huir\n\n"
            "3. *Cada vez que subas de nivel* recibiras la imagen de tu Castillo evolutivo."
        )

    def _cmd_map(self, p: Dict[str, Any]) -> str:
        zones = self.db.conn.execute("SELECT * FROM zones ORDER BY id").fetchall()
        lines = ["🗺️ *MAPA DEL MUNDO ARCANO*\n"]
        for z in zones:
            locked = "🔒" if p["level"] < z["min_level"] else ("📍" if p["zone_id"] == z["id"] else "✅")
            ruin_cnt = self.db.conn.execute(
                "SELECT COUNT(*) FROM world_ruins WHERE zone_id = ? AND claimed = 0", (z["id"],)
            ).fetchone()[0]
            lines.append(
                f"{locked} *[{z['id']}] {z['name']}* (Nv.{z['min_level']}–{z['max_level']})\n"
                f"   ☁️ {z['weather']} · 🌊 Mana: {z['mana_tide']} · 🏚️ Ruinas: {ruin_cnt}"
            )
        lines.append("\nUsa */explorar <num>* para viajar o explorar la zona actual.")
        return "\n".join(lines)

    def _cmd_explore(self, p: Dict[str, Any], args: List[str]) -> ActionResult:
        combat = self.db.conn.execute("SELECT * FROM combats WHERE chat_id = ?", (p["chat_id"],)).fetchone()
        if combat:
            return ActionResult(
                text=f"⚔️ ¡Ya estas en combate contra *{combat['enemy_name']}* ({combat['enemy_hp']}/{combat['enemy_max_hp']} HP)! Usa /atacar, /lanzar o /huir."
            )

        zone_id = p["zone_id"]
        if args and args[0].isdigit():
            req_z = int(args[0])
            z = self.db.conn.execute("SELECT * FROM zones WHERE id = ?", (req_z,)).fetchone()
            if not z:
                return ActionResult(text="❌ Zona inexistente. Usa /mapa para ver zonas 1–4.")
            if p["level"] < z["min_level"]:
                return ActionResult(text=f"🔒 *{z['name']}* requiere nivel {z['min_level']}. Tu nivel es {p['level']}.")
            zone_id = req_z
            self.db.conn.execute("UPDATE players SET zone_id = ? WHERE chat_id = ?", (zone_id, p["chat_id"]))
            self.db.conn.commit()

        zone = dict(self.db.conn.execute("SELECT * FROM zones WHERE id = ?", (zone_id,)).fetchone())

        # Check fallen hero ruins first
        ruin = self.db.conn.execute(
            "SELECT * FROM world_ruins WHERE zone_id = ? AND claimed = 0 ORDER BY id LIMIT 1", (zone_id,)
        ).fetchone()
        if ruin and random.random() < 0.35:
            self.db.conn.execute("UPDATE world_ruins SET claimed = 1 WHERE id = ?", (ruin["id"],))
            self.db.conn.execute("UPDATE players SET gold = gold + ? WHERE chat_id = ?", (ruin["gold_loot"], p["chat_id"]))
            self._add_item(p["chat_id"], "reliquia_ruina", ruin["item_name"], "material", "Raro", 1)
            self.db.conn.commit()
            return ActionResult(
                text=f"🏚️ ¡Encontraste las *Ruinas del Heroe Caido ({ruin['hero_name']})* en {zone['name']}!\n"
                     f"Saqueaste +{ruin['gold_loot']} Oro y *{ruin['item_name']}*."
            )

        roll = random.random()
        if roll < 0.65:
            # Start encounter
            m_name, m_hp, m_atk, m_def, m_res, m_spd, m_xp, m_gold = random.choice(ZONE_MONSTERS[zone_id])
            if zone["mana_tide"] == "Alta Marea Arcana":
                m_atk = int(m_atk * 1.12)
                m_xp = int(m_xp * 1.2)
            self.db.conn.execute(
                """INSERT INTO combats
                (chat_id, enemy_name, enemy_hp, enemy_max_hp, enemy_atk, enemy_def, enemy_res, enemy_spd, xp_reward, gold_reward, zone_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (p["chat_id"], m_name, m_hp, m_hp, m_atk, m_def, m_res, m_spd, m_xp, m_gold, zone_id),
            )
            # Ecological impact
            self.db.conn.execute("UPDATE zones SET predator_pop = MAX(10, predator_pop - 1) WHERE id = ?", (zone_id,))
            self.db.conn.commit()
            return ActionResult(
                text=(
                    f"⚔️ *¡Emboscada en {zone['name']}!* ({zone['weather']})\n"
                    f"👹 Enemigo: *{m_name}* — ❤️ {m_hp}/{m_hp} HP | ATQ {m_atk}\n"
                    "Elige: */atacar*, */lanzar bola_fuego*, */lanzar drenar_vida*, */objeto pocion_hp* o */huir*."
                )
            )
        else:
            # Gathering resources + XP
            mat_map = {
                1: ("hierba", "Hierba Luminosa"),
                2: ("esencia", "Esencia Espectral"),
                3: ("mineral", "Mineral Arcano"),
                4: ("cristal_bruto", "Cristal de Mana Bruto"),
            }
            m_key, m_name = mat_map[zone_id]
            qty = random.randint(1, 3)
            gold_found = random.randint(12, 30) * zone_id
            xp_found = 25 * zone_id
            crystals_found = 1 if zone_id >= 3 and random.random() < 0.4 else 0
            self._add_item(p["chat_id"], m_key, m_name, "material", "Comun", qty)
            self.db.conn.execute(
                "UPDATE players SET gold = gold + ?, crystals = crystals + ? WHERE chat_id = ?",
                (gold_found, crystals_found, p["chat_id"]),
            )
            p_after, leveled, tier = self._grant_xp(p, xp_found)
            txt = (
                f"🌿 *Exploracion en {zone['name']}* ({zone['mana_tide']})\n"
                f"Recolectaste *{qty}x {m_name}*, +{gold_found} Oro y +{xp_found} XP."
            )
            if crystals_found:
                txt += f" (+{crystals_found} 💎 Cristal de Mana)"
            return self._check_level_up_result(txt, p_after, leveled, tier)

    def _check_level_up_result(self, text: str, p: Dict[str, Any], leveled: bool, tier: int) -> ActionResult:
        if not leveled:
            return ActionResult(text=text)
        tier_name, tier_img = CASTLE_TIERS[tier]
        lvl_banner = (
            f"\n\n🎉 *¡SUBISTE AL NIVEL {p['level']}!*\n"
            f"🏰 Tu Castillo: *{tier_name}* (Tier {tier})\n"
            f"❤️ Max HP: {p['max_hp']} · 💧 Max MP: {p['max_mp']} · 🗡️ ATQ: {p['atk']} · 🔮 MAG: {p['mag']}"
        )
        if p["level"] == 10 and p["path_class"] == "Aprendiz":
            lvl_banner += "\n✨ ¡Desbloqueaste *Eleccion de Senda*! Usa: */clase teurgo* o */clase nigromante*"
        elif p["level"] == 15:
            lvl_banner += "\n⚒️ ¡Desbloqueaste *Crafteo y Mercado*! Prueba */craft* y */mercado*"
        elif p["level"] == 20 and not p["specialization"]:
            lvl_banner += "\n🔥 ¡Desbloqueaste *Especializacion*! Usa */clase piromante*, */clase invocador* o */clase clerigo*"
        elif p["level"] == 25:
            lvl_banner += "\n🛡️ ¡Desbloqueaste *Gremios*! Usa */gremio crear <nombre>*"
        elif p["level"] == 30:
            lvl_banner += "\n🐉 ¡Desbloqueaste la *Ciudadela Flotante*, *Raids* (/raid), *Mazmorras* (/mazmorra) y *Arena* (/arena)!"
        elif p["level"] == 50:
            lvl_banner += "\n🌟 ¡NIVEL MAXIMO ALCANZADO! Ya puedes realizar el rito de */renacer*."

        return ActionResult(
            text=text + lvl_banner,
            leveled_up=True,
            new_level=p["level"],
            castle_tier=tier,
            castle_name=tier_name,
            castle_image=tier_img,
        )

    def _resolve_enemy_turn(self, p: Dict[str, Any], combat: Dict[str, Any], log_lines: List[str]) -> ActionResult:
        if combat["enemy_hp"] <= 0:
            # Victory!
            self.db.conn.execute("DELETE FROM combats WHERE chat_id = ?", (p["chat_id"],))
            gold_gain = combat["gold_reward"]
            xp_gain = combat["xp_reward"]
            self.db.conn.execute(
                "UPDATE players SET gold = gold + ?, era_shards = era_shards + 1 WHERE chat_id = ?",
                (gold_gain, p["chat_id"]),
            )
            # Rare ancient fragment drop
            drop_msg = ""
            if random.random() < 0.25:
                self._add_item(p["chat_id"], "fragmento_antiguo", "Fragmento de Texto Antiguo", "material", "Raro", 1)
                drop_msg = "\n📜 ¡Botin raro: *1x Fragmento de Texto Antiguo*!"
            self.db.conn.commit()
            p_after, leveled, tier = self._grant_xp(p, xp_gain)
            log_lines.append(
                f"\n🏆 *¡Victoria sobre {combat['enemy_name']}!*\n"
                f"Ganaste +{xp_gain} XP, +{gold_gain} Oro y +1 Fragmento de Era.{drop_msg}"
            )
            return self._check_level_up_result("\n".join(log_lines), p_after, leveled, tier)

        # Enemy attacks back
        _, _, ed = self._equip_bonuses(p["chat_id"])
        raw_dmg = max(3, combat["enemy_atk"] - (p["def_stat"] + ed) // 2 + random.randint(-2, 3))
        if combat["shield_turns"] > 0:
            raw_dmg = max(1, raw_dmg // 2)
            self.db.conn.execute(
                "UPDATE combats SET shield_turns = shield_turns - 1, turn_num = turn_num + 1 WHERE chat_id = ?",
                (p["chat_id"],),
            )
        else:
            self.db.conn.execute("UPDATE combats SET turn_num = turn_num + 1 WHERE chat_id = ?", (p["chat_id"],))

        new_hp = p["hp"] - raw_dmg
        log_lines.append(f"👹 {combat['enemy_name']} contraataca por *{raw_dmg}* de dano.")

        if new_hp <= 0:
            # Player defeated -> leave Fallen Hero Ruin if level >= 5
            self.db.conn.execute("DELETE FROM combats WHERE chat_id = ?", (p["chat_id"],))
            lost_gold = min(p["gold"], max(10, p["gold"] // 5))
            if p["level"] >= 5:
                self.db.conn.execute(
                    "INSERT INTO world_ruins (zone_id, hero_name, gold_loot, item_name, created_at) VALUES (?, ?, ?, ?, ?)",
                    (combat["zone_id"], p["name"], lost_gold, "Reliquia del Caido", int(time.time())),
                )
            self.db.conn.execute(
                "UPDATE players SET hp = ?, mp = ?, gold = gold - ? WHERE chat_id = ?",
                (p["max_hp"] // 2, p["max_mp"] // 2, lost_gold, p["chat_id"]),
            )
            self.db.conn.commit()
            log_lines.append(
                f"\n💀 *Has caido en combate.* Despiertas en tu Castillo con 50% HP/MP (-{lost_gold} Oro)."
            )
            return ActionResult(text="\n".join(log_lines))

        self.db.conn.execute("UPDATE players SET hp = ? WHERE chat_id = ?", (new_hp, p["chat_id"]))
        self.db.conn.commit()
        log_lines.append(
            f"❤️ Tu HP: {new_hp}/{p['max_hp']} · 💧 MP: {p['mp']}/{p['max_mp']} | "
            f"👹 {combat['enemy_name']}: {combat['enemy_hp']}/{combat['enemy_max_hp']} HP"
        )
        return ActionResult(text="\n".join(log_lines))

    def _cmd_combat_attack(self, p: Dict[str, Any]) -> ActionResult:
        row = self.db.conn.execute("SELECT * FROM combats WHERE chat_id = ?", (p["chat_id"],)).fetchone()
        if not row:
            return ActionResult(text="No estas en combate. Usa */explorar* para buscar enemigos.")
        combat = dict(row)
        ea, _, _ = self._equip_bonuses(p["chat_id"])
        crit_hit = random.randint(1, 100) <= p["crit"]
        dmg = max(5, (p["atk"] + ea) - combat["enemy_def"] // 2 + random.randint(0, 5))
        if crit_hit:
            dmg = int(dmg * 1.6)
        combat["enemy_hp"] = max(0, combat["enemy_hp"] - dmg)
        new_mp = min(p["max_mp"], p["mp"] + 10)
        self.db.conn.execute("UPDATE combats SET enemy_hp = ? WHERE chat_id = ?", (combat["enemy_hp"], p["chat_id"]))
        self.db.conn.execute("UPDATE players SET mp = ? WHERE chat_id = ?", (new_mp, p["chat_id"]))
        self.db.conn.commit()
        p["mp"] = new_mp
        crit_txt = " 💥¡CRITICO!" if crit_hit else ""
        return self._resolve_enemy_turn(p, combat, [f"🗡️ Atacas a {combat['enemy_name']} por *{dmg}* de dano{crit_txt} (+10 MP)."])

    def _cmd_combat_spell(self, p: Dict[str, Any], spell: str) -> ActionResult:
        row = self.db.conn.execute("SELECT * FROM combats WHERE chat_id = ?", (p["chat_id"],)).fetchone()
        if not row:
            return ActionResult(text="No estas en combate. Usa */explorar* primero.")
        combat = dict(row)
        zone = dict(self.db.conn.execute("SELECT * FROM zones WHERE id = ?", (combat["zone_id"],)).fetchone())
        cost_mult = 1.3 if zone["mana_tide"] == "Sequia de Mana" else (0.85 if zone["mana_tide"] == "Alta Marea Arcana" else 1.0)
        pwr_mult = 1.2 if zone["mana_tide"] == "Alta Marea Arcana" else 1.0

        spells = {
            "bola_fuego": (14, "🔥 Bola de Fuego", 1.5),
            "drenar_vida": (16, "🩸 Drenar Vida", 1.25),
            "escudo_arcano": (12, "🛡️ Escudo Arcano", 0.0),
            "eclipse": (24, "🌑 Eclipse Hibrido", 2.1),
        }
        if spell not in spells:
            return ActionResult(text="Hechizos: *bola_fuego*, *drenar_vida*, *escudo_arcano*, *eclipse*")

        base_cost, s_name, mult = spells[spell]
        mp_cost = max(5, int(base_cost * cost_mult))
        if p["mp"] < mp_cost:
            return ActionResult(text=f"💧 Mana insuficiente ({p['mp']}/{mp_cost} MP). Usa */atacar* para generar mana o toma un elixir.")

        _, em, _ = self._equip_bonuses(p["chat_id"])
        logs = []
        new_mp = p["mp"] - mp_cost
        corr_gain = 0

        # Hidden Synergy bonus if alternating spells
        synergy = ""
        if combat["last_spell"] == "bola_fuego" and spell == "drenar_vida":
            mult += 0.45
            synergy = " ✨¡Sinergia Oculta: Llama Sombria!"

        if spell == "escudo_arcano":
            self.db.conn.execute("UPDATE combats SET shield_turns = 2, last_spell = ? WHERE chat_id = ?", (spell, p["chat_id"]))
            combat["shield_turns"] = 2
            logs.append(f"🛡️ Lanzas *{s_name}* (-{mp_cost} MP): reduces el dano a la mitad por 2 turnos.")
        else:
            dmg = max(8, int(((p["mag"] + em) * mult * pwr_mult) - combat["enemy_res"] // 3))
            combat["enemy_hp"] = max(0, combat["enemy_hp"] - dmg)
            self.db.conn.execute(
                "UPDATE combats SET enemy_hp = ?, last_spell = ? WHERE chat_id = ?",
                (combat["enemy_hp"], spell, p["chat_id"]),
            )
            logs.append(f"{s_name} golpea por *{dmg}* de dano magico (-{mp_cost} MP).{synergy}")
            if spell == "drenar_vida":
                heal = max(10, dmg // 2)
                p["hp"] = min(p["max_hp"], p["hp"] + heal)
                corr_gain = 3
                logs.append(f"💚 Drenas +{heal} HP (+3% Corrupcion).")
            elif spell == "eclipse":
                corr_gain = 5

        p["mp"] = new_mp
        self.db.conn.execute(
            "UPDATE players SET mp = ?, hp = ?, corruption = MIN(100, corruption + ?) WHERE chat_id = ?",
            (new_mp, p["hp"], corr_gain, p["chat_id"]),
        )
        self.db.conn.commit()
        return self._resolve_enemy_turn(p, combat, logs)

    def _cmd_use_item(self, p: Dict[str, Any], item_key: str) -> ActionResult:
        row = self.db.conn.execute(
            "SELECT * FROM inventory WHERE chat_id = ? AND item_key = ? AND qty > 0",
            (p["chat_id"], item_key),
        ).fetchone()
        if not row:
            return ActionResult(text=f"No tienes *{item_key}* en tu inventario. Usa /inventario.")
        if item_key == "pocion_hp":
            new_hp = min(p["max_hp"], p["hp"] + 65)
            self.db.conn.execute("UPDATE players SET hp = ? WHERE chat_id = ?", (new_hp, p["chat_id"]))
            msg = f"🧪 Usaste *Pocion de Vida*: ❤️ HP {new_hp}/{p['max_hp']}."
        elif item_key == "pocion_mp":
            new_mp = min(p["max_mp"], p["mp"] + 35)
            self.db.conn.execute("UPDATE players SET mp = ? WHERE chat_id = ?", (new_mp, p["chat_id"]))
            msg = f"🧪 Usaste *Elixir de Mana*: 💧 MP {new_mp}/{p['max_mp']}."
        else:
            return ActionResult(text="Consumibles validos: *pocion_hp* y *pocion_mp*.")

        self.db.conn.execute("UPDATE inventory SET qty = qty - 1 WHERE id = ?", (row["id"],))
        self.db.conn.commit()
        return ActionResult(text=msg)

    def _cmd_flee(self, p: Dict[str, Any]) -> ActionResult:
        row = self.db.conn.execute("SELECT * FROM combats WHERE chat_id = ?", (p["chat_id"],)).fetchone()
        if not row:
            return ActionResult(text="No estas en ningun combate.")
        combat = dict(row)
        chance = min(0.9, max(0.35, 0.5 + (p["spd"] - combat["enemy_spd"]) * 0.03))
        if random.random() <= chance:
            self.db.conn.execute("DELETE FROM combats WHERE chat_id = ?", (p["chat_id"],))
            self.db.conn.commit()
            return ActionResult(text=f"💨 Escapaste con exito de *{combat['enemy_name']}*.")
        p_after = self.db.get_player(p["chat_id"])
        return self._resolve_enemy_turn(p_after, combat, ["⚠️ Intentaste huir pero el enemigo te bloqueo el paso."])

    def _cmd_class(self, p: Dict[str, Any], args: List[str]) -> str:
        if p["level"] < 10:
            return f"🔒 La Eleccion de Senda se desbloquea al *Nivel 10* (tu nivel: {p['level']})."
        if not args:
            return (
                "🔮 *SENDAS Y ESPECIALIZACIONES*\n"
                "• Nv.10 — */clase teurgo* (+MAG/+MP) o */clase nigromante* (+MAG/+Drenaje)\n"
                "• Nv.20 — */clase piromante*, */clase invocador* o */clase clerigo*"
            )
        choice = args[0].lower()
        if choice in ("teurgo", "nigromante"):
            self.db.conn.execute(
                "UPDATE players SET path_class = ?, max_mp = max_mp + 20, mp = max_mp + 20, mag = mag + 6 WHERE chat_id = ?",
                (choice.capitalize(), p["chat_id"]),
            )
            self.db.conn.commit()
            return f"✨ Ahora sigues la senda de *{choice.capitalize()}* (+6 MAG, +20 Max MP)."
        if choice in ("piromante", "invocador", "clerigo"):
            if p["level"] < 20:
                return "🔒 La Especializacion requiere *Nivel 20*."
            self.db.conn.execute(
                "UPDATE players SET specialization = ?, mag = mag + 10, crit = crit + 5 WHERE chat_id = ?",
                (choice.capitalize(), p["chat_id"]),
            )
            self.db.conn.commit()
            return f"🔥 Especializacion completada: *{choice.capitalize()}* (+10 MAG, +5% Critico)."
        return "Opciones: *teurgo*, *nigromante*, *piromante*, *invocador*, *clerigo*."

    def _cmd_pact(self, p: Dict[str, Any], args: List[str]) -> str:
        if not args:
            return (
                "🤝 *PACTOS CON ENTIDADES ARCANAS*\n"
                "• */pacto espiral* — +15% Mana (clausula: no usar magia de fuego)\n"
                "• */pacto abismo* — +8 ATQ/+8 MAG (clausula: +10% Corrupcion)\n"
                "• */pacto llama* — +12 MAG/+5% Critico\n"
                "• */pacto romper* — Rompe el pacto actual (maldicion temporal -20 HP)"
            )
        choice = args[0].lower()
        if choice == "romper":
            self.db.conn.execute("UPDATE players SET pact_id = '', hp = MAX(10, hp - 20) WHERE chat_id = ?", (p["chat_id"],))
            self.db.conn.commit()
            return "⛓️ Rompiste tu pacto. Sufres una maldicion menor (-20 HP)."
        if choice in ("espiral", "abismo", "llama"):
            corr = 10 if choice == "abismo" else 0
            self.db.conn.execute(
                "UPDATE players SET pact_id = ?, corruption = MIN(100, corruption + ?) WHERE chat_id = ?",
                (choice.capitalize(), corr, p["chat_id"]),
            )
            self.db.conn.commit()
            return f"🕯️ Sellaste un Pacto con *{choice.capitalize()}*. Revisa tu hoja con /yo."
        return "Pactos disponibles: *espiral*, *abismo*, *llama*, *romper*."

    def _cmd_purify(self, p: Dict[str, Any]) -> str:
        cost = 100
        if p["gold"] < cost:
            return f"🕯️ Purificar tu corrupcion cuesta {cost} Oro (tienes {p['gold']})."
        self.db.conn.execute(
            "UPDATE players SET gold = gold - ?, corruption = MAX(0, corruption - 35) WHERE chat_id = ?",
            (cost, p["chat_id"]),
        )
        self.db.conn.commit()
        return "✨ Ritual de purificacion completado (-35% Corrupcion)."

    def _cmd_rebirth(self, p: Dict[str, Any]) -> ActionResult:
        if p["level"] < 50:
            return ActionResult(text=f"🌟 El Rito de Renacimiento requiere *Nivel 50* (tu nivel: {p['level']}).")
        nodes = json.loads(p["legacy_nodes"] or "[]")
        if "memoria_sangre" not in nodes:
            nodes.append("memoria_sangre")
        prev_class = p["specialization"] or p["path_class"]
        self.db.conn.execute(
            """UPDATE players SET level=1, xp=0, xp_next=100, gold=150, echoes=echoes+5,
            rebirth_count=rebirth_count+1, secondary_class=?, legacy_nodes=?, castle_tier=1,
            hp=140, max_hp=140, mp=80, max_mp=80 WHERE chat_id=?""",
            (prev_class, json.dumps(nodes), p["chat_id"]),
        )
        self.db.conn.commit()
        return ActionResult(
            text=(
                f"🌟 *¡RITO DE DESACER COMPLETADO!*\n"
                f"Has renacido (+5 ✨ Ecos de Vidas Pasadas, Nodo *Memoria de Sangre* +15% XP).\n"
                f"Tu clase anterior (*{prev_class}*) queda sellada como Clase Secundaria Hibrida."
            ),
            leveled_up=True,
            new_level=1,
            castle_tier=5,
            castle_name=CASTLE_TIERS[5][0],
            castle_image=CASTLE_TIERS[5][1],
        )

    def _cmd_inventory(self, p: Dict[str, Any]) -> str:
        rows = self.db.conn.execute(
            "SELECT * FROM inventory WHERE chat_id = ? AND qty > 0 ORDER BY category, rarity DESC",
            (p["chat_id"],),
        ).fetchall()
        if not rows:
            return "🎒 Tu mochila esta vacia."
        lines = ["🎒 *INVENTARIO*\n"]
        for r in rows:
            eq = " [Equipado]" if r["equipped"] else ""
            stats = []
            if r["atk_bonus"]:
                stats.append(f"+{r['atk_bonus']} ATQ")
            if r["mag_bonus"]:
                stats.append(f"+{r['mag_bonus']} MAG")
            if r["def_bonus"]:
                stats.append(f"+{r['def_bonus']} DEF")
            st = f" ({', '.join(stats)})" if stats else ""
            lines.append(f"• `{r['item_key']}` x{r['qty']} — *{r['name']}* [{r['rarity']}]{st}{eq}")
        return "\n".join(lines)

    def _cmd_craft(self, p: Dict[str, Any], args: List[str]) -> str:
        recipes = self.db.conn.execute("SELECT * FROM recipes ORDER BY min_level").fetchall()
        if not args:
            lines = [f"⚒️ *MESA DE CRAFTEO* (Nivel {p['level']} | Puntos: {p['craft_points']})\n"]
            for r in recipes:
                ing = json.loads(r["ingredients"])
                ing_txt = ", ".join(f"{k}:{v}" for k, v in ing.items())
                lines.append(f"• */craft {r['key']}* — {r['name']} (Nv.{r['min_level']}, {ing_txt})")
            lines.append("\n🧪 Tambien puedes probar */experimentar hierba esencia* para descubrir recetas.")
            return "\n".join(lines)

        rkey = args[0].lower()
        r = self.db.conn.execute("SELECT * FROM recipes WHERE key = ?", (rkey,)).fetchone()
        if not r:
            return "❌ Receta no encontrada. Usa */recetas*."
        if p["level"] < r["min_level"]:
            return f"🔒 Requiere nivel {r['min_level']}."
        ing = json.loads(r["ingredients"])
        for k, needed in ing.items():
            row = self.db.conn.execute(
                "SELECT qty FROM inventory WHERE chat_id = ? AND item_key = ?", (p["chat_id"], k)
            ).fetchone()
            if not row or row["qty"] < needed:
                return f"❌ Te falta material: `{k}` (necesitas {needed})."
        for k, needed in ing.items():
            self.db.conn.execute(
                "UPDATE inventory SET qty = qty - ? WHERE chat_id = ? AND item_key = ?", (needed, p["chat_id"], k)
            )
        # Quality roll & Masterwork chance
        roll = random.random()
        rarity = "Comun"
        mult = 1.0
        item_name = r["name"]
        lore = ""
        if roll < 0.05:
            rarity = "Obra Maestra"
            mult = 1.6
            item_name = f"{r['name']} de {p['name']}"
            lore = f"Forjada en la Era I por {p['name']}."
            self.db.conn.execute(
                "INSERT INTO era_chronicle (era_name, author_name, entry, created_at) VALUES (?, ?, ?, ?)",
                ("Era I", p["name"], f"Creo la Obra Maestra: {item_name}!", int(time.time())),
            )
        elif roll < 0.25:
            rarity = "Raro"
            mult = 1.25
        elif roll < 0.55:
            rarity = "Poco Comun"
            mult = 1.1

        eq = 1 if r["category"] in ("arma", "armadura") else 0
        self._add_item(
            p["chat_id"],
            r["key"],
            item_name,
            r["category"],
            rarity,
            1,
            int(r["atk_bonus"] * mult),
            int(r["mag_bonus"] * mult),
            int(r["def_bonus"] * mult),
            lore,
            eq,
        )
        self.db.conn.execute("UPDATE players SET craft_points = craft_points + 1 WHERE chat_id = ?", (p["chat_id"],))
        self.db.conn.commit()
        return f"⚒️ ¡Creaste *{item_name}* [{rarity}]! (+1 Punto de Crafteo)"

    def _cmd_experiment(self, p: Dict[str, Any], args: List[str]) -> str:
        if len(args) < 2:
            return "Uso: */experimentar <material1> <material2>*"
        m1, m2 = args[0].lower(), args[1].lower()
        for m in (m1, m2):
            row = self.db.conn.execute(
                "SELECT qty FROM inventory WHERE chat_id = ? AND item_key = ? AND qty >= 1", (p["chat_id"], m)
            ).fetchone()
            if not row:
                return f"❌ No tienes `{m}` suficiente."
        for m in (m1, m2):
            self.db.conn.execute("UPDATE inventory SET qty = qty - 1 WHERE chat_id = ? AND item_key = ?", (p["chat_id"], m))
        if random.random() < 0.35:
            self.db.conn.execute(
                "INSERT OR IGNORE INTO player_discoveries (chat_id, recipe_key, discovered_at) VALUES (?, 'filo_eclipse', ?)",
                (p["chat_id"], int(time.time())),
            )
            self._add_item(p["chat_id"], "pocion_mp", "Elixir Experimental", "consumible", "Raro", 1)
            self.db.conn.commit()
            return "💡 ¡Descubrimiento Accidental! Obtuviste *Elixir Experimental* y anotaste la receta *filo_eclipse*."
        self._add_item(p["chat_id"], "residuo", "Objeto Fallido", "basura", "Comun", 1)
        self.db.conn.commit()
        return "💨 La mezcla fallo y produjo un *Objeto Fallido* (vendible en mercado)."

    def _cmd_market(self, p: Dict[str, Any]) -> str:
        ws = self.db.get_world_state()
        mult = float(ws.get("economy_multiplier", "1.0"))
        hp_price = int(35 * mult)
        mp_price = int(45 * mult)
        rows = self.db.conn.execute("SELECT * FROM market_listings ORDER BY id DESC LIMIT 8").fetchall()
        lines = [
            f"⚖️ *MERCADO DEL REINO* (Indice: x{mult:.2f})\n",
            f"🏪 *Tienda NPC:*\n• */comprar npc_hp* — Pocion de Vida ({hp_price} Oro)\n• */comprar npc_mp* — Elixir de Mana ({mp_price} Oro)\n",
            "📜 *Ordenes de Jugadores:*",
        ]
        if not rows:
            lines.append("(No hay listados de jugadores aun. Usa */vender <item_key> <oro>*)")
        else:
            for r in rows:
                lines.append(f"• #{r['id']} *{r['item_name']}* [{r['rarity']}] — {r['price_gold']} Oro (por {r['seller_name']}) -> */comprar {r['id']}*")
        return "\n".join(lines)

    def _cmd_sell(self, p: Dict[str, Any], args: List[str]) -> str:
        if len(args) < 2 or not args[1].isdigit():
            return "Uso: */vender <item_key> <precio_oro>*"
        key, price = args[0].lower(), max(5, int(args[1]))
        row = self.db.conn.execute(
            "SELECT * FROM inventory WHERE chat_id = ? AND item_key = ? AND qty > 0", (p["chat_id"], key)
        ).fetchone()
        if not row:
            return f"❌ No tienes `{key}`."
        self.db.conn.execute("UPDATE inventory SET qty = qty - 1 WHERE id = ?", (row["id"],))
        self.db.conn.execute(
            """INSERT INTO market_listings (seller_chat_id, seller_name, item_key, item_name, rarity, qty, price_gold, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
            (p["chat_id"], p["name"], row["item_key"], row["name"], row["rarity"], price, int(time.time())),
        )
        self.db.conn.commit()
        return f"🏷️ Publicaste *{row['name']}* en el mercado por {price} Oro."

    def _cmd_buy(self, p: Dict[str, Any], args: List[str]) -> str:
        if not args:
            return "Uso: */comprar npc_hp* | */comprar npc_mp* | */comprar <id>*"
        target = args[0].lower()
        ws = self.db.get_world_state()
        mult = float(ws.get("economy_multiplier", "1.0"))
        if target in ("npc_hp", "npc_mp"):
            price = int((35 if target == "npc_hp" else 45) * mult)
            if p["gold"] < price:
                return f"❌ Necesitas {price} Oro."
            self.db.conn.execute("UPDATE players SET gold = gold - ? WHERE chat_id = ?", (price, p["chat_id"]))
            name = "Pocion de Vida Arcana" if target == "npc_hp" else "Elixir de Mana"
            key = "pocion_hp" if target == "npc_hp" else "pocion_mp"
            self._add_item(p["chat_id"], key, name, "consumible", "Comun", 1)
            return f"🛒 Compraste *1x {name}* por {price} Oro."

        if not target.isdigit():
            return "ID invalido."
        listing = self.db.conn.execute("SELECT * FROM market_listings WHERE id = ?", (int(target),)).fetchone()
        if not listing:
            return "❌ Ese articulo ya no esta disponible."
        if p["gold"] < listing["price_gold"]:
            return f"❌ Necesitas {listing['price_gold']} Oro."
        self.db.conn.execute("UPDATE players SET gold = gold - ? WHERE chat_id = ?", (listing["price_gold"], p["chat_id"]))
        self.db.conn.execute("UPDATE players SET gold = gold + ? WHERE chat_id = ?", (listing["price_gold"], listing["seller_chat_id"]))
        self.db.conn.execute("DELETE FROM market_listings WHERE id = ?", (listing["id"],))
        self._add_item(p["chat_id"], listing["item_key"], listing["item_name"], "material", listing["rarity"], 1)
        return f"🛒 Compraste *{listing['item_name']}* a {listing['seller_name']} por {listing['price_gold']} Oro."

    def _cmd_faction(self, p: Dict[str, Any], args: List[str]) -> str:
        reps = self.db.conn.execute(
            """SELECT f.id, f.name, f.rival_id, COALESCE(pr.rep, 0) as rep
            FROM factions f LEFT JOIN player_reputation pr ON f.id = pr.faction_id AND pr.chat_id = ?""",
            (p["chat_id"],),
        ).fetchall()
        lines = ["🏛️ *FACCIONES Y REPUTACION*\n"]
        for r in reps:
            lines.append(f"• *{r['name']}* (`{r['id']}`): {r['rep']} pts")
        lines.append("\nUsa */mision* para cumplir encargos y ganar reputacion, oro y XP.")
        return "\n".join(lines)

    def _cmd_mission(self, p: Dict[str, Any]) -> ActionResult:
        fid = "conclave" if p["corruption"] < 30 else "sombra"
        rival = "sombra" if fid == "conclave" else "conclave"
        self.db.conn.execute(
            "INSERT OR REPLACE INTO player_reputation (chat_id, faction_id, rep) VALUES (?, ?, COALESCE((SELECT rep FROM player_reputation WHERE chat_id=? AND faction_id=?),0) + 15)",
            (p["chat_id"], fid, p["chat_id"], fid),
        )
        self.db.conn.execute(
            "INSERT OR REPLACE INTO player_reputation (chat_id, faction_id, rep) VALUES (?, ?, COALESCE((SELECT rep FROM player_reputation WHERE chat_id=? AND faction_id=?),0) - 5)",
            (p["chat_id"], rival, p["chat_id"], rival),
        )
        gold = 40 + p["level"] * 5
        xp = 45 + p["level"] * 6
        self.db.conn.execute("UPDATE players SET gold = gold + ? WHERE chat_id = ?", (gold, p["chat_id"]))
        p_after, leveled, tier = self._grant_xp(p, xp)
        return self._check_level_up_result(
            f"📜 *Mision de Faccion completada* ({fid.capitalize()}): +{gold} Oro, +{xp} XP, +15 Reputacion.",
            p_after, leveled, tier,
        )

    def _cmd_guild(self, p: Dict[str, Any], args: List[str]) -> str:
        if not args:
            g_txt = "No perteneces a ningun gremio."
            if p["guild_id"]:
                g = self.db.conn.execute("SELECT * FROM guilds WHERE id = ?", (p["guild_id"],)).fetchone()
                if g:
                    g_txt = (
                        f"🛡️ Gremio: *{g['name']}* (Nv.{g['level']})\n"
                        f"💰 Banco: {g['gold_bank']} Oro · 📦 Suministros: {g['supplies']}\n"
                        f"🏰 Modulos: Murallas Nv.{g['walls_lv']} · Biblioteca Nv.{g['library_lv']} · Forja Nv.{g['forge_lv']} · Altar Nv.{g['altar_lv']}"
                    )
            return (
                f"{g_txt}\n\nComandos:\n"
                "• */gremio crear <nombre>* (Nv.25+)\n"
                "• */gremio unirse <nombre>*\n"
                "• */gremio donar <oro>*\n"
                "• */gremio construir <murallas|biblioteca|forja|altar>*"
            )

        sub = args[0].lower()
        if sub == "crear":
            if p["level"] < 25:
                return f"🔒 Fundar un gremio requiere *Nivel 25* (actual: {p['level']})."
            if len(args) < 2:
                return "Uso: */gremio crear <nombre>*"
            gname = " ".join(args[1:])[:24]
            try:
                cur = self.db.conn.execute(
                    "INSERT INTO guilds (name, leader_chat_id, created_at) VALUES (?, ?, ?)",
                    (gname, p["chat_id"], int(time.time())),
                )
                gid = cur.lastrowid
                self.db.conn.execute("UPDATE players SET guild_id = ? WHERE chat_id = ?", (gid, p["chat_id"]))
                self.db.conn.commit()
                return f"🏰 ¡Fundaste el gremio *{gname}*!"
            except Exception:
                return "❌ Ya existe un gremio con ese nombre."

        if sub == "unirse" and len(args) >= 2:
            gname = " ".join(args[1:])
            g = self.db.conn.execute("SELECT id, name FROM guilds WHERE LOWER(name) = LOWER(?)", (gname,)).fetchone()
            if not g:
                return "❌ Gremio no encontrado."
            self.db.conn.execute("UPDATE players SET guild_id = ? WHERE chat_id = ?", (g["id"], p["chat_id"]))
            self.db.conn.commit()
            return f"🤝 Te uniste al gremio *{g['name']}*."

        if sub == "donar" and len(args) >= 2 and args[1].isdigit() and p["guild_id"]:
            amt = int(args[1])
            if p["gold"] < amt or amt <= 0:
                return "❌ Oro insuficiente."
            self.db.conn.execute("UPDATE players SET gold = gold - ? WHERE chat_id = ?", (amt, p["chat_id"]))
            self.db.conn.execute("UPDATE guilds SET gold_bank = gold_bank + ?, supplies = supplies + ? WHERE id = ?", (amt, amt // 10, p["guild_id"]))
            self.db.conn.commit()
            return f"💰 Donaste {amt} Oro (+{amt//10} Suministros) al almacen del gremio."

        if sub == "construir" and len(args) >= 2 and p["guild_id"]:
            mod = args[1].lower()
            col = {"murallas": "walls_lv", "biblioteca": "library_lv", "forja": "forge_lv", "altar": "altar_lv"}.get(mod)
            if not col:
                return "Modulos: *murallas*, *biblioteca*, *forja*, *altar*"
            g = self.db.conn.execute("SELECT * FROM guilds WHERE id = ?", (p["guild_id"],)).fetchone()
            if g["gold_bank"] < 200:
                return "❌ El banco del gremio necesita 200 Oro."
            self.db.conn.execute(f"UPDATE guilds SET gold_bank = gold_bank - 200, {col} = {col} + 1 WHERE id = ?", (g["id"],))
            self.db.conn.commit()
            return f"🏗️ Mejoraste *{mod.capitalize()}* del gremio!"

        return "Comando de gremio no valido."

    def _cmd_war(self, p: Dict[str, Any], args: List[str]) -> str:
        nodes = self.db.conn.execute(
            """SELECT gn.*, g.name as owner_name FROM guild_nodes gn
            LEFT JOIN guilds g ON gn.owner_guild_id = g.id ORDER BY gn.id"""
        ).fetchall()
        if args and args[0].lower() == "atacar" and len(args) >= 2 and args[1].isdigit():
            if not p["guild_id"]:
                return "🛡️ Necesitas pertenecer a un gremio (*/gremio*) para asaltar Nodos de Poder."
            nid = int(args[1])
            node = self.db.conn.execute("SELECT * FROM guild_nodes WHERE id = ?", (nid,)).fetchone()
            if not node:
                return "❌ Nodo inexistente."
            dmg = p["atk"] + p["mag"] + random.randint(15, 45)
            new_def = node["defense_hp"] - dmg
            if new_def <= 0:
                self.db.conn.execute(
                    "UPDATE guild_nodes SET owner_guild_id = ?, defense_hp = max_defense_hp WHERE id = ?",
                    (p["guild_id"], nid),
                )
                self.db.conn.commit()
                return f"🚩 ¡CONQUISTA! Tu gremio capturo *{node['name']}* tras causar {dmg} de dano."
            self.db.conn.execute("UPDATE guild_nodes SET defense_hp = ? WHERE id = ?", (new_def, nid))
            self.db.conn.commit()
            return f"⚔️ Asaltaste *{node['name']}* por {dmg} de dano (Defensa restante: {new_def}/{node['max_defense_hp']})."

        lines = ["⚔️ *CENTRO DE GUERRA TERRITORIAL (GvG) & PvP*\n"]
        for n in nodes:
            owner = n["owner_name"] or "Neutral"
            lines.append(f"• Nodo #{n['id']} *{n['name']}* — Dueño: *{owner}* ({n['defense_hp']}/{n['max_defense_hp']} DEF)")
        lines.append("\n👉 Asaltar nodo: */guerra atacar <id>*\n👉 Arena PvP: */arena* | Incursiones: */raid*")
        return "\n".join(lines)

    def _cmd_arena(self, p: Dict[str, Any], args: List[str]) -> str:
        rivals = self.db.conn.execute(
            "SELECT chat_id, name, level, atk, mag, elo FROM players WHERE chat_id != ? ORDER BY elo DESC LIMIT 5",
            (p["chat_id"],),
        ).fetchall()
        if not rivals:
            return "🏟️ *ARENA PvP*: Aun no hay otros aventureros registrados para desafiar."
        opp = rivals[0]
        if args:
            target = " ".join(args).lower()
            for r in rivals:
                if target in r["name"].lower():
                    opp = r
                    break
        my_power = p["atk"] + p["mag"] + p["level"] * 4 + random.randint(0, 25)
        opp_power = opp["atk"] + opp["mag"] + opp["level"] * 4 + random.randint(0, 25)
        if my_power >= opp_power:
            self.db.conn.execute("UPDATE players SET elo = elo + 18, gold = gold + 60 WHERE chat_id = ?", (p["chat_id"],))
            self.db.conn.commit()
            return f"🏆 *¡Victoria en la Arena!* Venciste a *{opp['name']}* ({my_power} vs {opp_power}). +18 ELO, +60 Oro."
        self.db.conn.execute("UPDATE players SET elo = MAX(800, elo - 12) WHERE chat_id = ?", (p["chat_id"],))
        self.db.conn.commit()
        return f"💥 Derrota ajustada ante *{opp['name']}* ({my_power} vs {opp_power}). -12 ELO."

    def _cmd_raid(self, p: Dict[str, Any]) -> ActionResult:
        raid = self.db.conn.execute("SELECT * FROM raids WHERE active = 1 ORDER BY id DESC LIMIT 1").fetchone()
        if not raid:
            self.db.conn.execute(
                "INSERT INTO raids (boss_name, zone_id, hp, max_hp, active, started_at) VALUES (?, 4, 3000, 3000, 1, ?)",
                ("Titan del Eclipse Arcano", int(time.time())),
            )
            self.db.conn.commit()
            raid = self.db.conn.execute("SELECT * FROM raids WHERE active = 1 ORDER BY id DESC LIMIT 1").fetchone()

        ea, em, _ = self._equip_bonuses(p["chat_id"])
        dmg = max(25, p["atk"] + ea + p["mag"] + em + random.randint(15, 50))
        new_hp = max(0, raid["hp"] - dmg)
        self.db.conn.execute(
            """INSERT INTO raid_contributions (raid_id, chat_id, damage) VALUES (?, ?, ?)
            ON CONFLICT(raid_id, chat_id) DO UPDATE SET damage = damage + ?""",
            (raid["id"], p["chat_id"], dmg, dmg),
        )
        if new_hp == 0:
            self.db.conn.execute("UPDATE raids SET hp = 0, active = 0 WHERE id = ?", (raid["id"],))
            self.db.conn.execute("UPDATE players SET gold = gold + 300, crystals = crystals + 3 WHERE chat_id = ?", (p["chat_id"],))
            self.db.conn.commit()
            p_after, leveled, tier = self._grant_xp(p, 250)
            return self._check_level_up_result(
                f"🐉 *¡WORLD BOSS DERROTADO!* Golpe final a *{raid['boss_name']}* ({dmg} dano). +300 Oro, +3 Cristales, +250 XP.",
                p_after, leveled, tier,
            )
        self.db.conn.execute("UPDATE raids SET hp = ? WHERE id = ?", (new_hp, raid["id"]))
        self.db.conn.commit()
        p_after, leveled, tier = self._grant_xp(p, 45)
        return self._check_level_up_result(
            f"🐉 Atacaste al World Boss *{raid['boss_name']}* por *{dmg}* DPS! (HP Boss: {new_hp}/{raid['max_hp']}). +45 XP.",
            p_after, leveled, tier,
        )

    def _cmd_dungeon(self, p: Dict[str, Any], advance: bool) -> ActionResult:
        d = self.db.conn.execute("SELECT * FROM dungeons WHERE chat_id = ?", (p["chat_id"],)).fetchone()
        if not d:
            seed = random.randint(1000, 99999)
            self.db.conn.execute(
                "INSERT INTO dungeons (chat_id, seed, room, max_rooms, log) VALUES (?, ?, 1, 5, 'Entrada sellada')",
                (p["chat_id"], seed),
            )
            self.db.conn.commit()
            return ActionResult(
                text=f"🗝️ Entraste a una *Mazmorra Procedural* (Semilla #{seed}, Sala 1/5). Usa */avanzar* para explorar las salas!"
            )
        if not advance:
            return ActionResult(text=f"🗝️ Estas en la Sala {d['room']}/{d['max_rooms']} (Semilla #{d['seed']}). Usa */avanzar*.")
        next_room = d["room"] + 1
        if next_room > d["max_rooms"]:
            self.db.conn.execute("DELETE FROM dungeons WHERE chat_id = ?", (p["chat_id"],))
            self._add_item(p["chat_id"], "fragmento_antiguo", "Fragmento de Texto Antiguo", "material", "Raro", 1)
            self.db.conn.execute("UPDATE players SET gold = gold + 120 WHERE chat_id = ?", (p["chat_id"],))
            p_after, leveled, tier = self._grant_xp(p, 110)
            return self._check_level_up_result(
                "🏆 *¡Mazmorra completada!* Cofre final: +120 Oro, +110 XP y *1x Fragmento de Texto Antiguo*!",
                p_after, leveled, tier,
            )
        self.db.conn.execute("UPDATE dungeons SET room = ? WHERE chat_id = ?", (next_room, p["chat_id"]))
        self.db.conn.execute("UPDATE players SET gold = gold + 30 WHERE chat_id = ?", (p["chat_id"],))
        self.db.conn.commit()
        ev = random.choice(["Cofre arcano (+30 Oro)", "Puzzle de runas superado (+30 Oro)", "Trampa esquivada (+30 Oro)"])
        return ActionResult(text=f"🗝️ Sala {next_room}/{d['max_rooms']}: {ev}. Usa */avanzar*.")

    def _cmd_meta(self, p: Dict[str, Any], cmd: str) -> str:
        ws = self.db.get_world_state()
        if cmd in ("/mundo", "/estado"):
            return (
                f"🌐 *ESTADO GLOBAL DEL MUNDO*\n"
                f"⏳ {ws.get('era_name')} (Dia {ws.get('era_day')})\n"
                f"🌙 Ciclo Lunar: {ws.get('lunar_phase')}\n"
                f"⚡ Evento: {ws.get('world_event')}\n"
                f"💹 Multiplicador Mercado: x{ws.get('economy_multiplier')}"
            )
        if cmd == "/top":
            rows = self.db.conn.execute("SELECT name, level, elo, rebirth_count FROM players ORDER BY rebirth_count DESC, level DESC, elo DESC LIMIT 10").fetchall()
            lines = ["🏆 *RANKING DE HEROES*\n"]
            for i, r in enumerate(rows, 1):
                lines.append(f"{i}. *{r['name']}* — Nv.{r['level']} | ELO {r['elo']} | 🔄 {r['rebirth_count']}")
            return "\n".join(lines)
        if cmd == "/guildtop":
            rows = self.db.conn.execute("SELECT name, level, gold_bank FROM guilds ORDER BY level DESC, gold_bank DESC LIMIT 10").fetchall()
            if not rows:
                return "🛡️ Aun no hay gremios fundados."
            return "🛡️ *TOP GREMIOS*\n" + "\n".join(f"{i}. *{r['name']}* — Nv.{r['level']} ({r['gold_bank']} Oro)" for i, r in enumerate(rows, 1))
        rows = self.db.conn.execute("SELECT author_name, entry FROM era_chronicle ORDER BY id DESC LIMIT 6").fetchall()
        return f"📜 *SALON DE LA ERA* ({ws.get('era_name')})\n" + "\n".join(f"• *{r['author_name']}*: {r['entry']}" for r in rows)

    def _cmd_contracts(self, p: Dict[str, Any], cmd: str, args: List[str]) -> str:
        if cmd == "/prestamo":
            if args and args[0].lower() == "pagar":
                if p["debt_gold"] == 0:
                    return "No tienes deudas pendientes."
                if p["gold"] < p["debt_gold"]:
                    return f"Necesitas {p['debt_gold']} Oro para saldar tu deuda."
                self.db.conn.execute("UPDATE players SET gold = gold - debt_gold, debt_gold = 0, is_delinquent = 0 WHERE chat_id = ?", (p["chat_id"],))
                self.db.conn.commit()
                return "✅ Deuda saldada por completo."
            if p["debt_gold"] > 0:
                return f"💳 Ya tienes una deuda de {p['debt_gold']} Oro. Paga con */prestamo pagar*."
            self.db.conn.execute("UPDATE players SET gold = gold + 150, debt_gold = 195 WHERE chat_id = ?", (p["chat_id"],))
            self.db.conn.commit()
            return "💳 Prestamo NPC recibido: +150 Oro (deuda con interes: 195 Oro). Usa */prestamo pagar*."
        # /negro
        if random.random() < 0.25:
            fine = min(p["gold"], 50)
            self.db.conn.execute("UPDATE players SET gold = gold - ?, corruption = MIN(100, corruption + 5) WHERE chat_id = ?", (fine, p["chat_id"]))
            self.db.conn.commit()
            return f"🚨 ¡Redada en el Mercado Negro! Pagaste multa de {fine} Oro."
        self._add_item(p["chat_id"], "esencia", "Esencia Espectral Contrabandeada", "material", "Raro", 2)
        self.db.conn.execute("UPDATE players SET gold = gold + 75, corruption = MIN(100, corruption + 4) WHERE chat_id = ?", (p["chat_id"],))
        self.db.conn.commit()
        return "🕶️ Trato cerrado en el Mercado Negro: +75 Oro y +2x Esencia Espectral (+4% Corrupcion)."

    def handle_webxdc_action(self, chat_id: int, payload: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[ActionResult]]:
        action = payload.get("action")
        if not action:
            return None, None
        p = self.db.get_player(chat_id)
        if not p:
            return None, None
        cmd_map = {
            "explore": "/explorar",
            "attack": "/atacar",
            "spell_fire": "/lanzar bola_fuego",
            "spell_drain": "/lanzar drenar_vida",
            "spell_shield": "/lanzar escudo_arcano",
            "potion_hp": "/objeto pocion_hp",
            "potion_mp": "/objeto pocion_mp",
            "flee": "/huir",
            "mission": "/mision",
            "raid": "/raid",
            "dungeon": "/avanzar" if self.db.conn.execute("SELECT 1 FROM dungeons WHERE chat_id=?", (chat_id,)).fetchone() else "/mazmorra",
            "refresh": "/yo",
        }
        if action == "travel" and payload.get("zone_id"):
            cmd_str = f"/explorar {int(payload['zone_id'])}"
        elif action == "craft" and payload.get("recipe_key"):
            cmd_str = f"/craft {payload['recipe_key']}"
        else:
            cmd_str = cmd_map.get(action, "/yo")

        res = self.handle_command(chat_id, p["contact_id"], p["addr"], p["name"], cmd_str)
        snap = self.build_xdc_snapshot(chat_id)
        snap["last_log"] = res.text
        return snap, res
