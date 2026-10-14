import asyncio
import random
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from PySide6 import QtCore, QtGui, QtWidgets

import config
from core.actions import SpotifyBot
from core.browser import BrowserManager


ACCOUNTS_FILE = Path("accounts.txt")


def parse_proxy_string(proxy_raw: str) -> dict:
    raw = proxy_raw.strip()
    if not raw:
        raise ValueError("Proxy string is empty.")

    if raw.count(":") == 3 and "://" not in raw:
        host, port_str, username, password = (part.strip() for part in raw.split(":", 3))
        if not host or not port_str:
            raise ValueError(f"Proxy is missing host or port: {proxy_raw}")
        try:
            port = int(port_str)
        except ValueError as exc:
            raise ValueError("Port could not be cast to integer") from exc
        return {
            "server": f"http://{host}:{port}",
            "username": username or None,
            "password": password or None,
        }

    raw_with_scheme = raw if "://" in raw else f"http://{raw}"
    parsed = urlparse(raw_with_scheme)
    if not parsed.hostname or not parsed.port:
        raise ValueError(f"Proxy is missing host or port: {proxy_raw}")

    server = f"{parsed.scheme or 'http'}://{parsed.hostname}:{parsed.port}"
    return {
        "server": server,
        "username": parsed.username or None,
        "password": parsed.password or None,
    }


def build_proxy_url(proxy_config: dict) -> str:
    server = proxy_config.get("server")
    username = proxy_config.get("username")
    password = proxy_config.get("password")
    if username and password:
        scheme, rest = server.split("://", 1)
        return f"{scheme}://{username}:{password}@{rest}"
    return server


class ConsoleRedirector(QtCore.QObject):
    text_emitted = QtCore.Signal(str)

    def write(self, message: str) -> None:
        if message and not message.isspace():
            self.text_emitted.emit(message)

    def flush(self) -> None:
        pass


class BotWorker(QtCore.QThread):
    log_signal = QtCore.Signal(str)
    status_signal = QtCore.Signal(str, str)
    threads_signal = QtCore.Signal(int)
    accounts_signal = QtCore.Signal(int)
    finished_signal = QtCore.Signal()

    def __init__(self, max_threads: int, headless: bool, delay: float, filler_tracks: list, accounts_path: Path) -> None:
        super().__init__()
        self.max_threads = max_threads
        self.headless = headless
        self.delay = delay
        self.filler_tracks = filler_tracks
        self.accounts_path = accounts_path
        self.is_running = True

    def stop(self) -> None:
        self.is_running = False

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._run_async())
        except Exception as exc:
            self.log_signal.emit(f"Worker error: {exc}")
        finally:
            loop.run_until_complete(asyncio.sleep(0))
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
            self.finished_signal.emit()

    async def _run_async(self) -> None:
        config.HEADLESS = self.headless
        config.MAX_CONCURRENT_SESSIONS = self.max_threads

        accounts = self._load_accounts()
        self.accounts_signal.emit(len(accounts))
        self.threads_signal.emit(self.max_threads)
        self.status_signal.emit("RUNNING", "#1DB954")

        if not accounts:
            self.log_signal.emit("No accounts found in accounts.txt.")
            return

        browser_manager = BrowserManager()
        await browser_manager.init_playwright()
        semaphore = asyncio.Semaphore(self.max_threads)

        target_songs = getattr(config, "TARGET_SONGS", [])
        if not target_songs:
            target_songs = ["Target Track"]

        filler_tracks = self.filler_tracks or getattr(config, "FILLER_TRACKS", [])
        if not filler_tracks:
            filler_tracks = target_songs

        async def run_account(account: dict) -> None:
            username = account["username"]
            password = account["password"]
            proxy_raw = account["proxy_raw"]

            if not self.is_running:
                return

            try:
                proxy_config = parse_proxy_string(proxy_raw)
            except ValueError as exc:
                self.log_signal.emit(f"[{username}] Invalid proxy: {exc}")
                return

            async with semaphore:
                if not self.is_running:
                    return

                context = page = None
                try:
                    _, context, page = await browser_manager.create_browser(proxy=proxy_config, username=username)
                    bot = SpotifyBot(page, username, password)
                    await bot.login()

                    target_turn = True
                    while self.is_running:
                        try:
                            if target_turn:
                                song = random.choice(target_songs)
                                await bot.play_track(song, duration_range=(130, 190))
                            else:
                                filler = random.choice(filler_tracks)
                                await bot.play_track(filler, duration_range=(40, 60))

                            target_turn = not target_turn
                            await asyncio.sleep(max(0.1, self.delay))
                        except Exception as exc_inner:
                            self.log_signal.emit(f"[{username}] Error in session loop: {exc_inner}")
                            try:
                                await page.reload()
                            except Exception:
                                pass
                            await asyncio.sleep(5)
                except Exception as exc:
                    self.log_signal.emit(f"[{username}] Session crashed: {exc}")
                finally:
                    if context:
                        try:
                            await context.close()
                        except Exception:
                            pass

        tasks = [asyncio.create_task(run_account(account)) for account in accounts]

        try:
            await asyncio.gather(*tasks)
        finally:
            await browser_manager.close()

    def _load_accounts(self) -> list:
        accounts = []
        if not self.accounts_path.exists():
            self.log_signal.emit("accounts.txt not found.")
            return accounts

        with self.accounts_path.open("r", encoding="utf-8") as file:
            for line_number, raw_line in enumerate(file, start=1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = line.split(":", 2)
                if len(parts) != 3:
                    self.log_signal.emit(f"Skipping line {line_number}: expected 'email:password:proxy'.")
                    continue

                username, password, proxy_raw = (part.strip() for part in parts)
                if not username or not password or not proxy_raw:
                    self.log_signal.emit(f"Skipping line {line_number}: username, password, and proxy required.")
                    continue

                accounts.append({
                    "username": username,
                    "password": password,
                    "proxy_raw": proxy_raw,
                })

        return accounts


class ProxyCheckerWorker(QtCore.QThread):
    status_signal = QtCore.Signal(int, str, str)
    finished_signal = QtCore.Signal()

    def __init__(self, proxies: list, timeout: float = 6.0) -> None:
        super().__init__()
        self.proxies = proxies
        self.timeout = timeout
        self.is_running = True

    def stop(self) -> None:
        self.is_running = False

    def run(self) -> None:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._run_async())
        finally:
            loop.run_until_complete(asyncio.sleep(0))
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
            self.finished_signal.emit()

    async def _run_async(self) -> None:
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            semaphore = asyncio.Semaphore(8)

            async def check_proxy(index: int, proxy_raw: str) -> None:
                if not self.is_running:
                    return

                start = time.perf_counter()
                try:
                    proxy_config = parse_proxy_string(proxy_raw)
                    proxy_url = build_proxy_url(proxy_config)
                except Exception:
                    self.status_signal.emit(index, "Dead", "#E53935")
                    return

                async with semaphore:
                    if not self.is_running:
                        return
                    try:
                        async with session.get("https://www.google.com/generate_204", proxy=proxy_url) as response:
                            if response.status != 204:
                                raise Exception("bad status")
                        latency_ms = int((time.perf_counter() - start) * 1000)
                        self.status_signal.emit(index, f"Alive ({latency_ms} ms)", "#1DB954")
                    except Exception:
                        self.status_signal.emit(index, "Dead", "#E53935")

            tasks = [asyncio.create_task(check_proxy(index, proxy)) for index, proxy in enumerate(self.proxies)]
            await asyncio.gather(*tasks)


class App(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.is_running = False
        self.worker = None
        self.proxy_worker = None
        self.console_redirector = ConsoleRedirector()
        self.console_redirector.text_emitted.connect(self.append_console)
        self._drag_offset = None
        self.title_bar = None

        self.filler_tracks = []

        self.setWindowTitle("AuraStream")
        self.resize(1100, 700)
        self.setMinimumSize(960, 640)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.Window)
        self.setWindowOpacity(0.95)

        self._apply_theme()
        self._build_ui()
        self._load_accounts()

        sys.stdout = self.console_redirector
        sys.stderr = self.console_redirector

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            "QWidget { background-color: #121212; color: #E6E6E6; font-family: 'Segoe UI'; }"
            "QFrame#Sidebar { background-color: #0F0F0F; }"
            "QFrame#TitleBar { background-color: #0F0F0F; }"
            "QFrame#Card { background-color: #151515; border: 1px solid #2A2A2A; border-radius: 10px; }"
            "QPushButton { background-color: #1E1E1E; border: 1px solid #2A2A2A; border-radius: 10px; padding: 10px 14px; }"
            "QPushButton#TitleBtn { background-color: transparent; border: none; padding: 6px 8px; }"
            "QPushButton#Start { background-color: #1DB954; color: #0B0B0B; border: none; }"
            "QPushButton#Stop { background-color: #E53935; color: white; border: none; }"
            "QTableWidget { background-color: #151515; border: 1px solid #2A2A2A; border-radius: 10px; }"
            "QHeaderView::section { background-color: #1B1B1B; padding: 6px; border: none; }"
            "QTextEdit { background-color: #151515; border: 1px solid #2A2A2A; border-radius: 10px; }"
            "QLineEdit, QSpinBox, QDoubleSpinBox { background-color: #1A1A1A; border: 1px solid #2A2A2A; border-radius: 8px; padding: 6px; }"
            "QGroupBox { border: 1px solid #2A2A2A; border-radius: 10px; margin-top: 10px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }"
        )

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        outer_layout = QtWidgets.QVBoxLayout(central)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        title_bar = self._build_title_bar()
        outer_layout.addWidget(title_bar)

        main_layout = QtWidgets.QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = QtWidgets.QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(200)
        sidebar_layout = QtWidgets.QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(16, 16, 16, 16)
        sidebar_layout.setSpacing(12)

        logo = QtWidgets.QLabel("AuraStream")
        logo.setStyleSheet("font-size: 18px; font-weight: 600;")

        self.btn_dashboard = QtWidgets.QPushButton("Dashboard")
        self.btn_accounts = QtWidgets.QPushButton("Accounts")
        self.btn_settings = QtWidgets.QPushButton("Settings")
        self.btn_dashboard.clicked.connect(lambda: self._switch_tab(0))
        self.btn_accounts.clicked.connect(lambda: self._switch_tab(1))
        self.btn_settings.clicked.connect(lambda: self._switch_tab(2))

        sidebar_layout.addWidget(logo)
        sidebar_layout.addSpacing(8)
        sidebar_layout.addWidget(self.btn_dashboard)
        sidebar_layout.addWidget(self.btn_accounts)
        sidebar_layout.addWidget(self.btn_settings)
        sidebar_layout.addStretch()

        self.stack = QtWidgets.QStackedWidget()
        self.stack.addWidget(self._build_dashboard_tab())
        self.stack.addWidget(self._build_accounts_tab())
        self.stack.addWidget(self._build_settings_tab())

        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.stack)
        outer_layout.addLayout(main_layout)
        self.setCentralWidget(central)

    def _build_title_bar(self) -> QtWidgets.QFrame:
        bar = QtWidgets.QFrame()
        bar.setObjectName("TitleBar")
        bar.setFixedHeight(44)
        layout = QtWidgets.QHBoxLayout(bar)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        title = QtWidgets.QLabel("AuraStream")
        title.setStyleSheet("font-size: 12px; font-weight: 600;")

        btn_min = QtWidgets.QPushButton("_")
        btn_min.setObjectName("TitleBtn")
        btn_min.setFixedSize(24, 24)
        btn_min.clicked.connect(self.showMinimized)

        btn_max = QtWidgets.QPushButton("[]")
        btn_max.setObjectName("TitleBtn")
        btn_max.setFixedSize(24, 24)
        btn_max.clicked.connect(self._toggle_maximize)

        btn_close = QtWidgets.QPushButton("X")
        btn_close.setObjectName("TitleBtn")
        btn_close.setFixedSize(24, 24)
        btn_close.clicked.connect(self.close)

        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(btn_min)
        layout.addWidget(btn_max)
        layout.addWidget(btn_close)
        bar.installEventFilter(self)
        self.title_bar = bar
        return bar

    def _build_dashboard_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QtWidgets.QLabel("AuraStream Dashboard")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")

        cards_layout = QtWidgets.QHBoxLayout()
        cards_layout.setSpacing(12)
        self.card_status = self._build_card("Status", "IDLE", "#9E9E9E")
        self.card_threads = self._build_card("Threads", "0", "#1DB954")
        self.card_accounts = self._build_card("Accounts", "0", "#7AA2F7")
        cards_layout.addWidget(self.card_status)
        cards_layout.addWidget(self.card_threads)
        cards_layout.addWidget(self.card_accounts)

        console_label = QtWidgets.QLabel("Live Console")
        console_label.setStyleSheet("font-size: 14px; font-weight: 600;")

        self.console = QtWidgets.QTextEdit()
        self.console.setReadOnly(True)

        buttons_layout = QtWidgets.QHBoxLayout()
        buttons_layout.addStretch()
        self.btn_start = QtWidgets.QPushButton("START")
        self.btn_start.setObjectName("Start")
        self.btn_stop = QtWidgets.QPushButton("STOP")
        self.btn_stop.setObjectName("Stop")
        self.btn_stop.setEnabled(False)
        self.btn_start.clicked.connect(self.start_process)
        self.btn_stop.clicked.connect(self.stop_process)
        buttons_layout.addWidget(self.btn_start)
        buttons_layout.addWidget(self.btn_stop)

        layout.addWidget(title)
        layout.addLayout(cards_layout)
        layout.addWidget(console_label)
        layout.addWidget(self.console)
        layout.addLayout(buttons_layout)
        return widget

    def _build_accounts_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QtWidgets.QLabel("Accounts")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")

        self.accounts_table = QtWidgets.QTableWidget(0, 3)
        self.accounts_table.setHorizontalHeaderLabels(["Email", "Proxy", "Status"])
        self.accounts_table.horizontalHeader().setStretchLastSection(True)
        self.accounts_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.accounts_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.accounts_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.accounts_table.verticalHeader().setVisible(False)
        self.accounts_table.setShowGrid(False)

        buttons_layout = QtWidgets.QHBoxLayout()
        buttons_layout.addStretch()
        refresh = QtWidgets.QPushButton("Refresh")
        refresh.clicked.connect(self._load_accounts)
        self.btn_check_proxies = QtWidgets.QPushButton("CHECK PROXIES")
        self.btn_check_proxies.clicked.connect(self.check_proxies)
        buttons_layout.addWidget(refresh)
        buttons_layout.addWidget(self.btn_check_proxies)

        layout.addWidget(title)
        layout.addWidget(self.accounts_table)
        layout.addLayout(buttons_layout)
        return widget

    def _build_settings_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QtWidgets.QLabel("Settings")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")

        form = QtWidgets.QFormLayout()
        self.chk_headless = QtWidgets.QCheckBox("Headless Mode")
        self.chk_headless.setChecked(config.HEADLESS)
        self.spin_threads = QtWidgets.QSpinBox()
        self.spin_threads.setRange(1, 100)
        self.spin_threads.setValue(config.MAX_CONCURRENT_SESSIONS)
        self.spin_delay = QtWidgets.QDoubleSpinBox()
        self.spin_delay.setRange(0.1, 30.0)
        self.spin_delay.setSingleStep(0.1)
        self.spin_delay.setValue(2.0)

        form.addRow(self.chk_headless)
        form.addRow("Max Threads", self.spin_threads)
        form.addRow("Task Delay (seconds)", self.spin_delay)

        filler_group = QtWidgets.QGroupBox("Filler Tracks Source")
        filler_layout = QtWidgets.QVBoxLayout(filler_group)
        self.btn_load_fillers = QtWidgets.QPushButton("Load .txt")
        self.btn_load_fillers.clicked.connect(self.load_filler_file)
        self.input_filler_link = QtWidgets.QLineEdit()
        self.input_filler_link.setPlaceholderText("Paste Spotify URL (Playlist/Album/Track)")
        self.btn_add_filler = QtWidgets.QPushButton("Add Link")
        self.btn_add_filler.clicked.connect(self.add_filler_link)
        self.lbl_filler_count = QtWidgets.QLabel("Loaded Fillers: 0")

        filler_row = QtWidgets.QHBoxLayout()
        filler_row.addWidget(self.input_filler_link)
        filler_row.addWidget(self.btn_add_filler)

        filler_layout.addWidget(self.btn_load_fillers)
        filler_layout.addLayout(filler_row)
        filler_layout.addWidget(self.lbl_filler_count)

        hint = QtWidgets.QLabel("If no fillers are loaded, config.py defaults are used.")
        hint.setStyleSheet("color: #9E9E9E;")

        layout.addWidget(title)
        layout.addLayout(form)
        layout.addWidget(filler_group)
        layout.addWidget(hint)
        layout.addStretch()
        return widget

    def _build_card(self, title: str, value: str, color: str) -> QtWidgets.QFrame:
        frame = QtWidgets.QFrame()
        frame.setObjectName("Card")
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        value_label = QtWidgets.QLabel(value)
        value_label.setStyleSheet("font-size: 18px; font-weight: 600; color: #FFFFFF;")
        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet("color: #9E9E9E;")

        indicator = QtWidgets.QLabel("●")
        indicator.setStyleSheet(f"color: {color}; font-size: 14px;")

        top_row = QtWidgets.QHBoxLayout()
        top_row.addWidget(indicator)
        top_row.addStretch()

        layout.addLayout(top_row)
        layout.addWidget(value_label)
        layout.addWidget(title_label)

        frame.value_label = value_label
        frame.indicator = indicator
        return frame

    def _switch_tab(self, index: int) -> None:
        self.stack.setCurrentIndex(index)

    def _load_accounts(self) -> None:
        self.accounts_table.setRowCount(0)
        self.accounts_data = []
        count = 0
        if ACCOUNTS_FILE.exists():
            with ACCOUNTS_FILE.open("r", encoding="utf-8") as file:
                for line in file:
                    line = line.strip()
                    if not line or line.startswith("#") or ":" not in line:
                        continue
                    parts = line.split(":", 2)
                    if len(parts) != 3:
                        continue
                    email, password, proxy_raw = (part.strip() for part in parts)
                    if not email or not password or not proxy_raw:
                        continue

                    row = self.accounts_table.rowCount()
                    self.accounts_table.insertRow(row)
                    self.accounts_table.setItem(row, 0, QtWidgets.QTableWidgetItem(email))
                    self.accounts_table.setItem(row, 1, QtWidgets.QTableWidgetItem(proxy_raw))
                    status_item = QtWidgets.QTableWidgetItem("Ready")
                    status_item.setForeground(QtGui.QColor("#1DB954"))
                    self.accounts_table.setItem(row, 2, status_item)
                    self.accounts_data.append({
                        "email": email,
                        "password": password,
                        "proxy_raw": proxy_raw,
                    })
                    count += 1

        self.card_accounts.value_label.setText(str(count))

    def load_filler_file(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load Filler Tracks", "", "Text Files (*.txt)")
        if not file_path:
            return
        fillers = []
        with open(file_path, "r", encoding="utf-8") as file:
            for line in file:
                value = line.strip()
                if value and not value.startswith("#"):
                    fillers.append(value)
        self.filler_tracks = fillers
        self._update_filler_count()
        print(f"Loaded {len(fillers)} filler tracks from file.")

    def add_filler_link(self) -> None:
        link = self.input_filler_link.text().strip()
        if not link:
            return
        self.filler_tracks.append(link)
        self.input_filler_link.clear()
        self._update_filler_count()
        print(f"Added filler link: {link}")

    def _update_filler_count(self) -> None:
        self.lbl_filler_count.setText(f"Loaded Fillers: {len(self.filler_tracks)}")

    def check_proxies(self) -> None:
        if not getattr(self, "accounts_data", None):
            self._load_accounts()
        proxies = [account["proxy_raw"] for account in self.accounts_data]
        if not proxies:
            print("No proxies found to check.")
            return
        if self.proxy_worker and self.proxy_worker.isRunning():
            print("Proxy check already running.")
            return

        self.btn_check_proxies.setEnabled(False)
        self.proxy_worker = ProxyCheckerWorker(proxies)
        self.proxy_worker.status_signal.connect(self._update_proxy_status)
        self.proxy_worker.finished_signal.connect(self._on_proxy_check_finished)
        self.proxy_worker.start()

    def _update_proxy_status(self, row: int, text: str, color: str) -> None:
        item = QtWidgets.QTableWidgetItem(text)
        item.setForeground(QtGui.QColor(color))
        self.accounts_table.setItem(row, 2, item)

    def _on_proxy_check_finished(self) -> None:
        self.btn_check_proxies.setEnabled(True)
        print("Proxy check completed.")

    def start_process(self) -> None:
        if self.is_running:
            print("Engine already running.")
            return

        self.is_running = True
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._set_status("RUNNING", "#1DB954")
        self.card_threads.value_label.setText(str(self.spin_threads.value()))

        max_threads = int(self.spin_threads.value())
        headless = bool(self.chk_headless.isChecked())
        delay = float(self.spin_delay.value())

        if self.input_filler_link.text().strip():
            self.add_filler_link()

        filler_tracks = list(self.filler_tracks)
        self.worker = BotWorker(max_threads, headless, delay, filler_tracks, ACCOUNTS_FILE)
        self.worker.log_signal.connect(self.append_console)
        self.worker.status_signal.connect(self._set_status)
        self.worker.threads_signal.connect(lambda value: self.card_threads.value_label.setText(str(value)))
        self.worker.accounts_signal.connect(lambda value: self.card_accounts.value_label.setText(str(value)))
        self.worker.finished_signal.connect(self._on_worker_finished)
        self.worker.start()

        print("Starting AuraStream engine...")

    def stop_process(self) -> None:
        if not self.is_running:
            print("Engine is not running.")
            return
        print("Stop requested.")
        self.is_running = False
        self.btn_stop.setEnabled(False)
        self._set_status("STOPPING", "#E53935")
        if self.worker:
            self.worker.stop()

    def _on_worker_finished(self) -> None:
        self.is_running = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._set_status("IDLE", "#9E9E9E")
        self.card_threads.value_label.setText("0")

    def _set_status(self, text: str, color: str) -> None:
        self.card_status.value_label.setText(text)
        self.card_status.indicator.setStyleSheet(f"color: {color}; font-size: 14px;")

    def append_console(self, message: str) -> None:
        cursor = self.console.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        cursor.insertText(message)
        if not message.endswith("\n"):
            cursor.insertText("\n")
        self.console.setTextCursor(cursor)
        self.console.ensureCursorVisible()

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if obj is self.title_bar:
            if event.type() == QtCore.QEvent.MouseButtonPress:
                if event.button() == QtCore.Qt.LeftButton:
                    self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                    return True
            elif event.type() == QtCore.QEvent.MouseMove and self._drag_offset is not None:
                if event.buttons() & QtCore.Qt.LeftButton:
                    self.move(event.globalPosition().toPoint() - self._drag_offset)
                    return True
            elif event.type() == QtCore.QEvent.MouseButtonRelease:
                self._drag_offset = None
                return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(2000)
        if self.proxy_worker and self.proxy_worker.isRunning():
            self.proxy_worker.stop()
            self.proxy_worker.wait(2000)
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        super().closeEvent(event)


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
