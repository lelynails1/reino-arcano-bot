"""Bot 24/7 de Reino Arcano RPG para ArcaneChat / Delta Chat."""

import json
import logging
import os
import shutil
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from deltachat2 import (
    Bot,
    ChatType,
    EventType,
    IOTransport,
    MessageData,
    NewMsgEvent,
    Rpc,
    SpecialContactId,
    events,
    types,
)

from game_db import GameDB
from game_engine import ArcanoEngine, ActionResult, welcome_message
from webxdc_builder import build_xdc

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("arcano-bot")

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
SEED_DIR = BASE_DIR / "seed_account"
COMMANDS_BAR_MSG = "/yo · /menu · /guerra · /ayuda"

BOT_NAME = os.environ.get("BOT_NAME", "Reino Arcano RPG")
BOT_STATUS = os.environ.get(
    "BOT_STATUS",
    "Juego RPG Arcano 24/7. Verificacion E2EE activa. Usa /start para jugar.",
)


def resolve_data_dir() -> Path:
    candidates = []
    env_dir = os.environ.get("BOT_DATA_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.extend([Path("/data"), BASE_DIR / "data", Path("/tmp/arcano_data")])

    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return path
        except OSError:
            continue
    raise RuntimeError("No se encontro un directorio con permisos de escritura para datos.")


def seed_accounts_if_needed(accounts_dir: Path) -> None:
    if accounts_dir.exists() and any(accounts_dir.iterdir()):
        return
    if SEED_DIR.exists() and any(SEED_DIR.iterdir()):
        logger.info("Inicializando cuenta persistente en %s desde seed_account...", accounts_dir)
        shutil.copytree(SEED_DIR, accounts_dir, dirs_exist_ok=True)


def configure_account(rpc: Rpc) -> int:
    accounts = rpc.get_all_account_ids()
    accid = accounts[0] if accounts else rpc.add_account()

    if not rpc.is_configured(accid):
        rpc.set_config(accid, "bot", "1")
        addr = os.environ.get("BOT_ADDR", "").strip()
        password = os.environ.get("BOT_PASSWORD", "").strip()
        if addr and password:
            logger.info("Configurando cuenta con BOT_ADDR=%s", addr)
            rpc.add_transport(accid, types.EnteredLoginParam(addr=addr, password=password))
        else:
            qr_src = os.environ.get("CHATMAIL_QR", "dcaccount:arcanechat.me")
            logger.info("Creando nueva cuenta en %s ...", qr_src)
            rpc.add_transport_from_qr(accid, qr_src)

    rpc.set_config(accid, "bot", "1")
    rpc.set_config(accid, "displayname", BOT_NAME)
    rpc.set_config(accid, "selfstatus", BOT_STATUS)
    avatar_path = ASSETS_DIR / "bot_avatar.jpg"
    if avatar_path.exists():
        rpc.set_config(accid, "selfavatar", str(avatar_path))
    return accid


def send_commands_bar(bot: Bot, accid: int, chat_id: int) -> None:
    bot.rpc.send_msg(accid, chat_id, MessageData(text=COMMANDS_BAR_MSG))


def deliver_action_result(
    bot: Bot,
    accid: int,
    chat_id: int,
    result: ActionResult,
    xdc_path: str,
    db: GameDB,
    send_bar: bool = True,
) -> None:
    # 1. Main text reply
    if result.text:
        bot.rpc.send_msg(accid, chat_id, MessageData(text=result.text))

    # 2. Small castle image on every level up
    if result.leveled_up and result.castle_image:
        img_path = ASSETS_DIR / result.castle_image
        if img_path.exists():
            bot.rpc.send_msg(
                accid,
                chat_id,
                MessageData(
                    text=f"🏰 Castillo Nivel {result.new_level}: {result.castle_name}",
                    file=str(img_path),
                ),
            )

    # 3. Interactive .xdc mini-app when requested
    if result.send_xdc and os.path.exists(xdc_path):
        msg_id = bot.rpc.send_msg(
            accid,
            chat_id,
            MessageData(file=xdc_path, filename="arcano.xdc"),
        )
        db.conn.execute("UPDATE players SET xdc_msg_id = ? WHERE chat_id = ?", (msg_id, chat_id))
        db.conn.commit()
        if result.xdc_payload:
            bot.rpc.send_webxdc_status_update(
                accid,
                msg_id,
                json.dumps({"payload": result.xdc_payload}),
                "Estado inicial de Reino Arcano",
            )
    elif result.xdc_payload:
        row = db.conn.execute("SELECT xdc_msg_id FROM players WHERE chat_id = ?", (chat_id,)).fetchone()
        if row and row["xdc_msg_id"]:
            try:
                bot.rpc.send_webxdc_status_update(
                    accid,
                    int(row["xdc_msg_id"]),
                    json.dumps({"payload": result.xdc_payload}),
                    "",
                )
            except Exception:
                pass

    # 4. Separate quick-command bar message containing ONLY the commands
    if send_bar:
        send_commands_bar(bot, accid, chat_id)


def create_bot_app(
    data_dir: Path,
    db: GameDB,
    engine: ArcanoEngine,
    xdc_path: str,
) -> tuple[events.HookCollection, dict]:
    hooks = events.HookCollection()
    state = {"last_serials": {}}

    @hooks.on(events.RawEvent)
    def on_raw_event(bot: Bot, accid: int, event: EventType) -> None:
        try:
            # 1) Auto-welcome immediately after SecureJoin encryption verification completes
            if isinstance(event, types.EventTypeSecurejoinInviterProgress):
                if event.progress == 1000 and event.chat_type == ChatType.SINGLE:
                    if not db.is_welcomed(event.chat_id):
                        contact = bot.rpc.get_contact(accid, event.contact_id)
                        db.mark_welcomed(event.chat_id, event.contact_id, contact.address)
                        logger.info(
                            "Verificacion E2EE completada para chat_id=%s (%s). Enviando bienvenida.",
                            event.chat_id,
                            contact.address,
                        )
                        bot.rpc.send_msg(
                            accid,
                            event.chat_id,
                            MessageData(text=welcome_message(BOT_NAME)),
                        )
                        send_commands_bar(bot, accid, event.chat_id)

            # 2) Interactive Mini-App (.xdc) updates
            elif isinstance(event, types.EventTypeWebxdcStatusUpdate):
                msg = bot.rpc.get_message(accid, event.msg_id)
                last_s = state["last_serials"].get(event.msg_id, event.status_update_serial - 1)
                raw_updates = bot.rpc.get_webxdc_status_updates(accid, event.msg_id, last_s)
                updates = json.loads(raw_updates)
                for upd in updates:
                    serial = upd.get("serial", 0)
                    state["last_serials"][event.msg_id] = max(state["last_serials"].get(event.msg_id, 0), serial)
                    payload = upd.get("payload") or {}
                    if payload.get("action"):
                        snap, act_res = engine.handle_webxdc_action(msg.chat_id, payload)
                        if snap:
                            bot.rpc.send_webxdc_status_update(
                                accid,
                                event.msg_id,
                                json.dumps({"payload": snap}),
                                "",
                            )
                        if act_res and act_res.leveled_up and act_res.castle_image:
                            img_path = ASSETS_DIR / act_res.castle_image
                            if img_path.exists():
                                bot.rpc.send_msg(
                                    accid,
                                    msg.chat_id,
                                    MessageData(
                                        text=f"🏰 ¡Subiste al Nivel {act_res.new_level}! Castillo: {act_res.castle_name}",
                                        file=str(img_path),
                                    ),
                                )
                                send_commands_bar(bot, accid, msg.chat_id)

            elif isinstance(event, types.EventTypeError):
                logger.error("Core error: %s", event.msg)
        except Exception as exc:
            logger.exception("Error procesando RawEvent %s: %s", type(event).__name__, exc)

    @hooks.on(events.NewMessage(is_info=False))
    def on_message(bot: Bot, accid: int, event: NewMsgEvent) -> None:
        msg = event.msg
        if msg.from_id <= SpecialContactId.LAST_SPECIAL:
            return
        try:
            chat_info = bot.rpc.get_basic_chat_info(accid, msg.chat_id)
            text = (msg.text or "").strip()

            # In groups, only respond to slash commands
            if chat_info.chat_type != ChatType.SINGLE and not text.startswith("/"):
                return

            contact = bot.rpc.get_contact(accid, msg.from_id)

            # Fallback welcome if user contacted without SecureJoin QR
            if chat_info.chat_type == ChatType.SINGLE and not db.is_welcomed(msg.chat_id):
                db.mark_welcomed(msg.chat_id, msg.from_id, contact.address)
                bot.rpc.send_msg(accid, msg.chat_id, MessageData(text=welcome_message(BOT_NAME)))
                if not text.startswith("/start"):
                    send_commands_bar(bot, accid, msg.chat_id)
                    return

            result = engine.handle_command(
                chat_id=msg.chat_id,
                contact_id=msg.from_id,
                addr=contact.address,
                sender_name=contact.display_name or contact.address.split("@")[0],
                raw_text=text,
            )
            deliver_action_result(bot, accid, msg.chat_id, result, xdc_path, db, send_bar=True)
        except Exception as exc:
            logger.exception("Error procesando mensaje %s: %s", msg.id, exc)
            try:
                bot.rpc.send_msg(accid, msg.chat_id, MessageData(text="⚠️ Ocurrio un error interno. Intenta de nuevo."))
                send_commands_bar(bot, accid, msg.chat_id)
            except Exception:
                pass

    return hooks, state


def start_health_server_if_needed() -> None:
    port_str = os.environ.get("PORT", "").strip()
    if not port_str:
        return
    try:
        port = int(port_str)
    except ValueError:
        return

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'{"status":"ok","service":"Reino Arcano RPG"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Servidor HTTP healthcheck activo en 0.0.0.0:%s", port)


def run_bot() -> None:
    start_health_server_if_needed()
    data_dir = resolve_data_dir()
    accounts_dir = data_dir / "accounts"
    seed_accounts_if_needed(accounts_dir)

    db_path = str(data_dir / "game.db")
    xdc_path = str(data_dir / "arcano.xdc")
    build_xdc(xdc_path, str(ASSETS_DIR / "icon.png"))

    db = GameDB(db_path)
    engine = ArcanoEngine(db)
    hooks, _ = create_bot_app(data_dir, db, engine, xdc_path)

    rpc_bin = shutil.which("deltachat-rpc-server") or "deltachat-rpc-server"

    def handle_sig(signum, _frame):
        logger.info("Senal %s recibida. Cerrando ordenadamente...", signum)
        db.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_sig)
    signal.signal(signal.SIGINT, handle_sig)

    while True:
        try:
            with IOTransport(accounts_dir=str(accounts_dir), rpc_executable=rpc_bin) as trans:
                rpc = Rpc(trans)
                accid = configure_account(rpc)
                addr = rpc.get_config(accid, "addr")
                qr_link = rpc.get_chat_securejoin_qr_code(accid, None)
                logger.info("=========================================")
                logger.info("Reino Arcano RPG activo 24/7")
                logger.info("Cuenta Bot: %s", addr)
                logger.info("Link de invitacion: %s", qr_link)
                logger.info("Directorio de datos: %s", data_dir)
                logger.info("=========================================")
                bot = Bot(rpc, hooks)
                bot.run_forever()
        except SystemExit:
            raise
        except Exception as exc:
            logger.exception("Conexion interrumpida (%s). Reintentando en 5s...", exc)
            time.sleep(5)


if __name__ == "__main__":
    run_bot()
