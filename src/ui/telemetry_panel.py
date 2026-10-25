from __future__ import annotations

import calendar
import random
from datetime import datetime
from typing import Dict, List
from collections import deque
import json
from pathlib import Path

from PyQt6.QtCore import pyqtSignal, Qt, QSettings
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QProgressBar,
    QGroupBox,
    QGridLayout,
    QFormLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QSizePolicy,
)

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg


MOTORS = [
    "GLM-4V",
    "Google Vision",
    "Google Docs OCR",
    "Mistral OCR-3",
    "DeepSeek-Chat",
    "Qwen",
    "OpenCode",
    "GPT-Chat",
    "Mistral (Comprehension)",
    "Otros / Próximamente",
]

ACCENT = "#0078d7"

_TELE_FILE = Path.home() / ".ocr_glm_telemetry.json"
_BACKEND_TO_MOTOR = {
    "glm": "GLM-4V",
    "google-vision": "Google Vision",
    "google-docs": "Google Docs OCR",
    "mistral-ocr-latest": "Mistral OCR-3",
    "deepseek": "DeepSeek-Chat",
    "deepseek-chat": "DeepSeek-Chat",
    "deepseek-v3.2": "DeepSeek-Chat",
    "deepseek-v3.2-chat": "DeepSeek-Chat",
    "openai": "GPT-Chat",
    "openai gpt-4o": "GPT-Chat",
    "openrouter": "OpenCode",
    "openrouter-ocr": "OpenCode",
    "openai-vision": "GPT-Chat",
}
_COST_PER_1K = {
    "glm": 0.007,
    "mistral-ocr-latest": 20.0,
    "deepseek": 0.007,
    "deepseek-chat": 0.007,
    "google-vision": 0.0,
}


class TelemetryPanel(QWidget):
    """Panel de Telemetría: tarjetas por motor + gráfico diario y mensual.

    Usa matplotlib para graficar y datos simulados.
    """

    refresh_requested = pyqtSignal()
    motor_refresh_requested = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("telemetryPanel")

        root = QVBoxLayout()
        root.setSpacing(15)
        root.setContentsMargins(15, 15, 15, 15)

        # Controls (año + actualizar)
        ctrl_row = QWidget()
        ctrl_l = QHBoxLayout()
        ctrl_l.setContentsMargins(0, 0, 0, 0)
        ctrl_l.setSpacing(12)
        ctrl_row.setLayout(ctrl_l)

        self.year_cb = QComboBox()
        self.year_cb.addItems(["2024", "2025", "2026"])
        self.year_cb.setCurrentText(str(datetime.now().year))
        self.year_cb.setFixedWidth(120)
        ctrl_l.addWidget(QLabel("Año:"))
        ctrl_l.addWidget(self.year_cb)

        # Optionally a month selector
        self.month_cb = QComboBox()
        months = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
        self.month_cb.addItems(months)
        self.month_cb.setCurrentIndex(datetime.now().month - 1)
        self.month_cb.setFixedWidth(120)
        ctrl_l.addWidget(QLabel("Mes:"))
        ctrl_l.addWidget(self.month_cb)

        ctrl_l.addStretch()
        self.btn_refresh_all = QPushButton("Actualizar todos los datos")
        self.btn_refresh_all.setFixedHeight(32)
        self.btn_refresh_all.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        ctrl_l.addWidget(self.btn_refresh_all)

        # Force refresh button (explicit) so normal update does not break zeroed state
        self.btn_force_refresh = QPushButton("Forzar recarga")
        self.btn_force_refresh.setFixedHeight(28)
        self.btn_force_refresh.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        ctrl_l.addWidget(self.btn_force_refresh)

        # Reset button to zero all telemetry displays
        self.btn_reset = QPushButton("Resetear datos")
        self.btn_reset.setFixedHeight(32)
        self.btn_reset.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        ctrl_l.addWidget(self.btn_reset)

        # Resource usage widget (RAM)
        res_box = QGroupBox("Uso de Recursos")
        res_box.setObjectName("resourceBox")
        res_l = QHBoxLayout()
        res_l.setContentsMargins(8, 6, 8, 6)
        res_l.setSpacing(8)
        self.ram_label = QLabel("RAM: -- / -- (--) ")
        self.ram_bar = QProgressBar()
        # Allow progress bar to expand so percentage text is visible
        self.ram_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.ram_bar.setTextVisible(True)
        self.ram_bar.setFormat("%p%")
        self.ram_bar.setRange(0, 100)
        self.cpu_label = QLabel("CPU: -- (%)")
        self.cpu_bar = QProgressBar()
        self.cpu_bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.cpu_bar.setTextVisible(True)
        self.cpu_bar.setRange(0, 100)
        self.psutil_btn = QPushButton("Instalar psutil")
        self.psutil_btn.setFixedHeight(24)
        res_l.addWidget(self.ram_label)
        res_l.addWidget(self.ram_bar)
        res_l.addWidget(self.cpu_label)
        res_l.addWidget(self.cpu_bar)
        res_l.addWidget(self.psutil_btn)
        res_box.setLayout(res_l)
        ctrl_l.addWidget(res_box)

        root.addWidget(ctrl_row)

        # (Removed memory history) — added program consumption chart later in charts row

        # Grid of motor cards
        motors_box = QGroupBox("🤖 CONSUMO POR MOTOR DE IA")
        motors_box.setObjectName("telemetryMotors")
        motors_l = QVBoxLayout()
        motors_l.setContentsMargins(8, 8, 8, 8)
        motors_box.setLayout(motors_l)

        grid = QGridLayout()
        grid.setSpacing(12)

        self.card_labels: Dict[str, Dict[str, QLabel]] = {}

        for idx, name in enumerate(MOTORS):
            card = QGroupBox(name)
            card.setObjectName("motorCard")
            fl = QFormLayout()
            fl.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
            fl.setFormAlignment(Qt.AlignmentFlag.AlignLeft)
            lbl_tok_day = QLabel("0")
            lbl_calls_day = QLabel("0")
            lbl_cost_day = QLabel("$0.00")
            lbl_tok_month = QLabel("0")
            lbl_calls_month = QLabel("0")
            lbl_cost_month = QLabel("$0.00")
            fl.addRow("🟢 Tokens día:", lbl_tok_day)
            fl.addRow("📞 Llamadas día:", lbl_calls_day)
            fl.addRow("💰 Gasto día:", lbl_cost_day)
            fl.addRow("📅 Tokens mes:", lbl_tok_month)
            fl.addRow("📞 Llamadas mes:", lbl_calls_month)
            fl.addRow("💵 Gasto mes:", lbl_cost_month)
            btn = QPushButton("Actualizar")
            btn.setFixedHeight(26)
            btn.clicked.connect(self._make_motor_refresh_handler(name))
            fl.addRow(btn)
            card.setLayout(fl)

            # use 2 columns for a more balanced layout
            cols = 2
            r = idx // cols
            c = idx % cols
            grid.addWidget(card, r, c)
            self.card_labels[name] = {
                "tokens_day": lbl_tok_day,
                "calls_day": lbl_calls_day,
                "cost_day": lbl_cost_day,
                "tokens_month": lbl_tok_month,
                "calls_month": lbl_calls_month,
                "cost_month": lbl_cost_month,
            }

        motors_l.addLayout(grid)
        root.addWidget(motors_box)

        # Mistral-specific summary card
        self._mistral_box = QGroupBox("Mistral OCR — Estadísticas")
        mb_l = QHBoxLayout()
        mb_l.setContentsMargins(8, 6, 8, 6)
        self.mistral_docs_lbl = QLabel("Documentos procesados: 0")
        self.mistral_total_cost_lbl = QLabel("Costo total Mistral: $0.00")
        self.mistral_avg_lbl = QLabel("Costo promedio/doc: $0.00")
        mb_l.addWidget(self.mistral_docs_lbl)
        mb_l.addWidget(self.mistral_total_cost_lbl)
        mb_l.addWidget(self.mistral_avg_lbl)
        mb_l.addStretch()
        self._mistral_box.setLayout(mb_l)
        root.addWidget(self._mistral_box)

        # Charts: place one per row (stacked) and increase size for readability

        # Daily chart (fila 1)
        self.daily_box = QGroupBox(f"📈 TOKENS DIARIOS - {datetime.now():%B %Y}")
        dlay = QVBoxLayout()
        # slightly smaller figures for balance
        self.daily_fig = Figure(figsize=(7, 3.2), tight_layout=True)
        self.daily_canvas = FigureCanvasQTAgg(self.daily_fig)
        self.daily_canvas.setMinimumHeight(320)
        dlay.addWidget(self.daily_canvas)
        self.daily_box.setLayout(dlay)
        root.addWidget(self.daily_box)

        # Program consumption / Calls (fila 2)
        self.program_box = QGroupBox("📊 LLAMADAS DIARIAS - Consumo del programa")
        play = QVBoxLayout()
        self.program_fig = Figure(figsize=(7, 3.2), tight_layout=True)
        self.program_canvas = FigureCanvasQTAgg(self.program_fig)
        self.program_canvas.setMinimumHeight(320)
        play.addWidget(self.program_canvas)
        self.program_box.setLayout(play)
        root.addWidget(self.program_box)

        # Monthly chart (fila 3)
        self.monthly_box = QGroupBox(f"📊 TOKENS POR MOTOR - Año {datetime.now().year}")
        mlay = QVBoxLayout()
        self.monthly_fig = Figure(figsize=(7, 3.2), tight_layout=True)
        self.monthly_canvas = FigureCanvasQTAgg(self.monthly_fig)
        self.monthly_canvas.setMinimumHeight(320)
        mlay.addWidget(self.monthly_canvas)
        self.monthly_box.setLayout(mlay)
        root.addWidget(self.monthly_box)

        self.setLayout(root)

        # Signals
        # Normal refresh does NOT force; use 'Forzar recarga' to force
        self.btn_refresh_all.clicked.connect(lambda: self._on_refresh_all(force=False))
        self.btn_reset.clicked.connect(self._on_reset)
        self.year_cb.currentIndexChanged.connect(lambda _: self._on_refresh_all())
        self.month_cb.currentIndexChanged.connect(lambda _: self._on_refresh_all())
        self.btn_force_refresh.clicked.connect(lambda: self._on_refresh_all(force=True))

        # Initial render
        # load persisted zeroed state (if user reset previously)
        try:
            settings = QSettings("OCR-con-GLM-IA", "Telemetry")
            self._zeroed = settings.value("zeroed", False, type=bool)
        except Exception:
            self._zeroed = False
        self._on_refresh_all()

        # load persisted mistral stats if present
        try:
            cfg_path = Path.home() / ".ocr_glm_config.json"
            if cfg_path.exists():
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                ms = cfg.get("mistral_stats", {})
                month_key = datetime.now().strftime("%Y-%m")
                cur = ms.get(month_key, {})
                docs = int(cur.get("docs_processed", 0))
                total_cost = float(cur.get("total_cost", 0.0))
                avg = (total_cost / docs) if docs else 0.0
                self.update_mistral_stats(docs, total_cost, avg)
        except Exception:
            pass

        # Resource monitoring setup
        try:
            import psutil
            self._psutil = psutil
            self.psutil_btn.setVisible(False)
        except Exception:
            self._psutil = None
            # show install button
            self.psutil_btn.clicked.connect(self._install_psutil)

        # no memory history buffer (we show program consumption bars instead)

        self._res_timer = QTimer(self)
        self._res_timer.setInterval(2000)
        self._res_timer.timeout.connect(self._update_resource_usage)
        self._res_timer.start()

        # update once immediately
        self._update_resource_usage()

    def _make_motor_refresh_handler(self, name: str):
        def handler():
            self.motor_refresh_requested.emit(name)
            # For demo, refresh only that motor
            y = int(self.year_cb.currentText())
            m = self.month_cb.currentIndex() + 1
            data = self._simulate(y, m)
            self._update_card(name, data[name])
        return handler

    def _simulate(self, year: int, month: int) -> Dict[str, Dict]:
        # If UI was reset, return zeroed data until user forces refresh
        if getattr(self, '_zeroed', False):
            out: Dict[str, Dict] = {}
            days = calendar.monthrange(year, month)[1]
            for name in MOTORS:
                out[name] = {
                    "tokens_day": 0,
                    "calls_day": 0,
                    "cost_day": 0.0,
                    "tokens_month": 0,
                    "calls_month": 0,
                    "cost_month": 0.0,
                    "daily_tokens": [0] * days,
                    "daily_calls": [0] * days,
                }
            return out
        days = calendar.monthrange(year, month)[1]
        out: Dict[str, Dict] = {}
        for name in MOTORS:
            # simulate realistic token counts and calls per day
            tokens_day = random.randint(50, 2500)
            # assume average tokens per call between 50 and 400
            avg_tokens_per_call = random.randint(50, 400)
            # daily tokens series with noise
            daily_tokens = [max(0, int(tokens_day * random.uniform(0.6, 1.6))) for _ in range(days)]
            daily_calls = [max(0, int(t // avg_tokens_per_call + random.randint(0, 3))) for t in daily_tokens]
            tokens_month = sum(daily_tokens)
            calls_month = sum(daily_calls)
            cost_day = round((daily_tokens[0] if daily_tokens else tokens_day) * 0.00002, 5)
            cost_month = round(tokens_month * 0.00002, 4)
            out[name] = {
                "tokens_day": daily_tokens[0] if daily_tokens else tokens_day,
                "calls_day": daily_calls[0] if daily_calls else 0,
                "cost_day": cost_day,
                "tokens_month": tokens_month,
                "calls_month": calls_month,
                "cost_month": cost_month,
                "daily_tokens": daily_tokens,
                "daily_calls": daily_calls,
            }
        return out

    def _on_refresh_all(self, force: bool = False) -> None:
        # If UI was reset to zero, skip regenerating data unless forced
        if getattr(self, '_zeroed', False) and not force:
            self._clear_cards()
            self._clear_charts()
            return
        if force:
            self._zeroed = False
            try:
                settings = QSettings("OCR-con-GLM-IA", "Telemetry")
                settings.setValue("zeroed", False)
            except Exception:
                pass
        year = int(self.year_cb.currentText())
        month = self.month_cb.currentIndex() + 1
        data = self._load_real_month_data(year, month) or self._simulate(year, month)
        # update cards
        for k, v in data.items():
            self._update_card(k, v)
        # update charts: compute daily tokens and calls totals
        totals_tokens, totals_calls = self._compute_daily_totals(data, year, month)
        self._draw_daily_chart(totals_tokens, year, month)
        self._draw_program_consumption(totals_calls, year, month)
        self._draw_monthly_chart(data, year)
        self.refresh_requested.emit()

    def _load_real_month_data(self, year: int, month: int) -> Dict[str, Dict] | None:
        """Carga telemetría real por día/backend desde ~/.ocr_glm_telemetry.json."""
        try:
            if not _TELE_FILE.exists():
                return None
            raw = json.loads(_TELE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None

        days = calendar.monthrange(year, month)[1]
        out: Dict[str, Dict] = {}
        for name in MOTORS:
            out[name] = {
                "tokens_day": 0,
                "calls_day": 0,
                "cost_day": 0.0,
                "tokens_month": 0,
                "calls_month": 0,
                "cost_month": 0.0,
                "daily_tokens": [0] * days,
                "daily_calls": [0] * days,
            }

        month_prefix = f"{year:04d}-{month:02d}-"
        found = False
        today_key = datetime.now().strftime("%Y-%m-%d")

        for day_key, entry in (raw or {}).items():
            if not str(day_key).startswith(month_prefix):
                continue
            if not isinstance(entry, dict):
                continue
            try:
                day = int(str(day_key)[8:10])
            except Exception:
                continue
            day_idx = day - 1
            if day_idx < 0 or day_idx >= days:
                continue

            for backend, vals in entry.items():
                motor = _BACKEND_TO_MOTOR.get(str(backend).lower())
                if not motor or motor not in out:
                    continue
                if isinstance(vals, dict):
                    pt = int(vals.get("prompt", 0) or 0)
                    ct = int(vals.get("completion", 0) or 0)
                    calls = int(vals.get("calls", 0) or 0)
                else:
                    try:
                        v = int(vals)
                    except Exception:
                        v = 0
                    pt = v // 2
                    ct = v // 2
                    calls = 1 if v > 0 else 0

                total = pt + ct
                out[motor]["daily_tokens"][day_idx] += total
                out[motor]["daily_calls"][day_idx] += calls
                out[motor]["tokens_month"] += total
                out[motor]["calls_month"] += calls
                price = _COST_PER_1K.get(str(backend).lower(), 0.007)
                out[motor]["cost_month"] += (total / 1000.0) * price
                found = True

                if str(day_key) == today_key:
                    out[motor]["tokens_day"] += total
                    out[motor]["calls_day"] += calls
                    out[motor]["cost_day"] += (total / 1000.0) * price

        return out if found else None

    def _update_card(self, name: str, payload: Dict) -> None:
        labels = self.card_labels.get(name)
        if not labels:
            return
        try:
            labels["tokens_day"].setText(str(payload.get("tokens_day", 0)))
            # set calls and costs too
            labels["calls_day"].setText(str(payload.get("calls_day", 0)))
            labels["cost_day"].setText(f"${payload.get('cost_day', 0):.4f}")
            labels["tokens_month"].setText(str(payload.get("tokens_month", 0)))
            labels["calls_month"].setText(str(payload.get("calls_month", 0)))
            labels["cost_month"].setText(f"${payload.get('cost_month', 0):.4f}")
        except Exception:
            pass

    def update_mistral_stats(self, docs: int, total_cost: float, avg_cost: float) -> None:
        try:
            self.mistral_docs_lbl.setText(f"Documentos procesados: {int(docs)}")
            self.mistral_total_cost_lbl.setText(f"Costo total Mistral: ${float(total_cost):.2f}")
            self.mistral_avg_lbl.setText(f"Costo promedio/doc: ${float(avg_cost):.2f}")
        except Exception:
            pass
    def _compute_daily_totals(self, data: Dict[str, Dict], year: int, month: int):
        days = calendar.monthrange(year, month)[1]
        totals_tokens = [0] * days
        totals_calls = [0] * days
        for v in data.values():
            series_t = v.get("daily_tokens", [])
            series_c = v.get("daily_calls", [])
            for i in range(min(days, len(series_t))):
                totals_tokens[i] += series_t[i]
            for i in range(min(days, len(series_c))):
                totals_calls[i] += series_c[i]
        return totals_tokens, totals_calls

    def _draw_daily_chart(self, totals: List[float], year: int, month: int) -> None:
        days = len(totals)
        ax = self.daily_fig.subplots()
        ax.clear()
        xs = list(range(1, days + 1))
        ax.bar(xs, totals, color=ACCENT)
        ax.set_xlabel("Días del mes")
        ax.set_ylabel("Tokens")
        ax.set_title(f"Tokens diarios — {datetime(year, month, 1):%B %Y}")
        ax.set_xlim(0.5, days + 0.5)
        try:
            self.daily_fig.subplots_adjust(bottom=0.14, top=0.90)
            ax.tick_params(axis='x', rotation=30)
        except Exception:
            pass
        self.daily_canvas.draw()

    def _draw_program_consumption(self, totals_calls: List[float], year: int, month: int) -> None:
        ax = self.program_fig.subplots()
        ax.clear()
        days = len(totals_calls)
        xs = list(range(1, days + 1))
        ax.bar(xs, totals_calls, color="#2ca02c")
        ax.set_xlabel("Días del mes")
        ax.set_ylabel("Llamadas")
        ax.set_title(f"Llamadas diarias — {datetime(year, month, 1):%B %Y}")
        ax.set_xlim(0.5, days + 0.5)
        try:
            self.program_fig.subplots_adjust(bottom=0.14, top=0.90)
            ax.tick_params(axis='x', rotation=30)
        except Exception:
            pass
        self.program_canvas.draw()

    def _clear_cards(self) -> None:
        # set all motor cards to zero
        for labels in self.card_labels.values():
            try:
                labels["tokens_day"].setText("0")
                labels["calls_day"].setText("0")
                labels["cost_day"].setText("$0.00")
                labels["tokens_month"].setText("0")
                labels["calls_month"].setText("0")
                labels["cost_month"].setText("$0.00")
            except Exception:
                pass

    def _clear_charts(self) -> None:
        # draw empty daily chart
        try:
            dax = self.daily_fig.subplots()
            dax.clear()
            dax.set_title("Consumo diario — (reiniciado)")
            dax.set_xlabel("Días del mes")
            dax.set_ylabel("Gasto (USD)")
            self.daily_canvas.draw()
        except Exception:
            pass
        # draw empty program chart
        try:
            pax = self.program_fig.subplots()
            pax.clear()
            pax.set_title("Consumo del programa — (reiniciado)")
            pax.set_xlabel("Días del mes")
            pax.set_ylabel("Consumo relativo (%)")
            self.program_canvas.draw()
        except Exception:
            pass
        # draw empty monthly chart
        try:
            max_ = self.monthly_fig.subplots()
            max_.clear()
            max_.set_title(f"Consumo mensual — Año {datetime.now().year} (reiniciado)")
            max_.set_ylabel("Gasto (USD)")
            self.monthly_canvas.draw()
        except Exception:
            pass

    def _on_reset(self) -> None:
        # Reset UI displays to zero
        self._clear_cards()
        self._clear_charts()
        # persist zeroed state so it survives app restarts until user refreshes
        self._zeroed = True
        try:
            settings = QSettings("OCR-con-GLM-IA", "Telemetry")
            settings.setValue("zeroed", True)
        except Exception:
            pass

    def _draw_monthly_chart(self, data: Dict[str, Dict], year: int) -> None:
        # Show tokens per motor for the selected month
        ax = self.monthly_fig.subplots()
        ax.clear()
        labels = []
        vals = []
        for name, v in data.items():
            labels.append(name)
            vals.append(v.get("tokens_month", 0))
        ax.bar(labels, vals, color=ACCENT)
        ax.set_ylabel("Tokens (mes)")
        ax.set_title(f"Tokens por motor — {year}")
        ax.tick_params(axis='x', rotation=30)
        try:
            self.monthly_fig.subplots_adjust(bottom=0.28, top=0.90)
        except Exception:
            pass
        self.monthly_canvas.draw()

    # ---- Resource monitoring helpers ----
    def _bytes_to_human(self, n: int) -> str:
        # simple human readable
        for unit in ['B','KB','MB','GB','TB']:
            if n < 1024.0:
                return f"{n:.1f} {unit}"
            n /= 1024.0
        return f"{n:.1f} PB"

    def _update_resource_usage(self) -> None:
        try:
            if not getattr(self, '_psutil', None):
                self.ram_label.setText("RAM: psutil no instalado")
                self.ram_bar.setValue(0)
                return
            mem = self._psutil.virtual_memory()
            used = mem.used
            total = mem.total
            pct = int(mem.percent)
            self.ram_label.setText(f"RAM: {self._bytes_to_human(used)} / {self._bytes_to_human(total)} ({pct}%)")
            self.ram_bar.setValue(pct)
            # CPU
            try:
                cpu_pct = int(self._psutil.cpu_percent(interval=None))
            except Exception:
                cpu_pct = 0
            self.cpu_label.setText(f"CPU: {cpu_pct}%")
            self.cpu_bar.setValue(cpu_pct)
            # no longer maintaining memory history; resource display only
            pass
        except Exception:
            try:
                self.ram_label.setText("RAM: error al leer")
            except Exception:
                pass

    def _install_psutil(self) -> None:
        # attempt to install psutil via pip using current interpreter
        try:
            import sys, subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])  # noqa: S603
            import psutil
            self._psutil = psutil
            self.psutil_btn.setVisible(False)
            self._update_resource_usage()
        except Exception as exc:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Instalación Fallida", f"No se pudo instalar psutil: {exc}")

    def _draw_mem_history(self) -> None:
        # removed: memory history plotting is no longer used
        return


if __name__ == "__main__":
    # quick manual test
    from PyQt6.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    w = TelemetryPanel()
    w.show()
    sys.exit(app.exec())
