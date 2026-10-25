APP_QSS = """
QWidget { background-color: #0F172A; color: #F8FAFC; font-family: 'Segoe UI', sans-serif; font-size: 13px; }
QFrame { background-color: #1E293B; border: 1px solid #334155; border-radius: 8px; }
QGroupBox { background-color: #1E293B; border: 1px solid #334155; border-radius: 8px; margin-top: 12px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 4px 8px; color: #94A3B8; }
QPushButton { background-color: #334155; color: #F8FAFC; border: none; border-radius: 6px; padding: 8px 16px; font-weight: 500; }
QPushButton:hover { background-color: #475569; }
QPushButton#primaryBtn { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #3B82F6, stop:1 #8B5CF6); color: #FFF; }
QPushButton#primaryBtn:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #2563EB, stop:1 #7C3AED); }
QLineEdit, QComboBox, QSpinBox { background-color: #0F172A; border: 1px solid #334155; border-radius: 4px; padding: 6px 10px; color: #F8FAFC; }
QLineEdit:focus { border: 1px solid #3B82F6; }
QCheckBox::indicator { width: 18px; height: 18px; border: 2px solid #475569; border-radius: 3px; }
QCheckBox::indicator:checked { background-color: #10B981; border: 2px solid #10B981; }
QTabWidget::pane { border: 1px solid #334155; border-radius: 6px; }
QTabBar::tab { background: #1E293B; color: #94A3B8; padding: 10px 16px; border-radius: 6px 6px 0 0; }
QTabBar::tab:selected { background: #3B82F6; color: #FFF; }
QScrollBar:vertical { background: #1E293B; width: 10px; border-radius: 5px; }
QScrollBar::handle:vertical { background: #475569; border-radius: 5px; min-height: 20px; }
QLabel#statusConnected { color: #10B981; font-weight: 600; }
QLabel#statusDisconnected { color: #EF4444; font-weight: 600; }
QMessageBox { background-color: #0F172A; color: #F8FAFC; }
QMessageBox QLabel { color: #F8FAFC; min-width: 280px; }
QMessageBox QPushButton { background-color: #334155; color: #F8FAFC; min-width: 90px; }
"""

APP_QSS_LIGHT = """
QWidget { background-color: #FFFFFF; color: #0F172A; font-family: 'Segoe UI', sans-serif; font-size: 13px; }
QFrame { background-color: #F1F5F9; border: 1px solid #E2E8F0; border-radius: 8px; }
QWidget#headerBar { background-color: #FFFFFF; border-bottom: 1px solid #E5E7EB; }
QLabel#brandLabel { color: #6366F1; }
QFrame#sidebarNav { background-color: #F3F4F6; border-right: 1px solid #E5E7EB; border-radius: 0px; }
QPushButton#navItem { color: #6B7280; }
QPushButton#navItem:hover { background-color: #E5E7EB; color: #1F2937; }
QPushButton#navItem[navActive="true"] { background-color: #EEF2FF; color: #4F46E5; border-left: 4px solid #6366F1; }
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox { background-color: #FFFFFF; border: 1px solid #E2E8F0; color: #0F172A; }
QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border: 1px solid #6366F1; }
QTableWidget { background-color: #FFFFFF; alternate-background-color: #F8FAFC; border: 1px solid #E2E8F0; gridline-color: #E2E8F0; }
QTabBar::tab:selected { color: #6366F1; border-bottom: 2px solid #6366F1; }
QGroupBox { background-color: #FFFFFF; border: 1px solid #E5E7EB; color: #374151; }
QScrollBar:vertical { background: #F1F5F9; }
QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366F1, stop:1 #10B981); border-radius: 4px; }
QMessageBox { background-color: #FFFFFF; color: #0F172A; }
QMessageBox QLabel { color: #0F172A; min-width: 280px; }
QMessageBox QPushButton { background-color: #E5E7EB; color: #0F172A; min-width: 90px; }
"""
