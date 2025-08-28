import sys
import os
import re
import json
import requests
from urllib.parse import urljoin, urlparse
from pathlib import Path
import time
from datetime import datetime

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                             QProgressBar, QTextEdit, QScrollArea, QFrame,
                             QGroupBox, QGridLayout, QSpinBox, QCheckBox,
                             QMessageBox, QFileDialog, QTabWidget, QListWidget,
                             QListWidgetItem, QSplitter, QMenuBar, QMenu, QAction, QComboBox, QHBoxLayout, QWidgetAction)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer, QSize, QObject, QMutex
from PyQt5.QtGui import QPixmap, QFont, QPalette, QColor, QIcon
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from loadingspinner import * 
from nsm import *  # Network Speed Monitor
from imgdlmain import * # Main Downloader Logic
from imgprev import * # Image Preview Widget







class ZerochanDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.downloader_thread = None
        self.current_theme = 'blue'  # Default theme
        self.direct_mode = False
        self.silent_mode = False  # Track silent mode state
        self.network_monitor = NetworkSpeedMonitor()
        self.init_ui()
        self.center_window()

    def clear_main_layout(self):
        if hasattr(self, 'main_layout'):
            while self.main_layout.count():
                item = self.main_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)

    def switch_to_direct_download(self):
        self.direct_mode = True
        self.setWindowTitle("Zerochan Direct Image Downloader")
        # Remove central widget and replace with direct download UI
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        # Top input
        url_label = QLabel("Zerochan Image Page URL:")
        url_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        self.direct_url_input = QLineEdit()
        self.direct_url_input.setPlaceholderText("Paste a direct image page URL, e.g. https://www.zerochan.net/3903835")
        # Download folder
        folder_layout = QHBoxLayout()
        self.direct_folder_input = QLineEdit()
        self.direct_folder_input.setPlaceholderText("Download folder path")
        self.direct_folder_input.setText(os.path.join(os.path.expanduser("~"), "Downloads", "Zerochan"))
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(lambda: self.direct_browse_folder())
        folder_layout.addWidget(self.direct_folder_input)
        folder_layout.addWidget(browse_btn)
        # Download button
        download_btn = QPushButton("Download Image")
        download_btn.clicked.connect(self.direct_download_image)
        # Progress and log
        self.direct_progress = QProgressBar()
        self.direct_progress.setTextVisible(True)
        self.direct_progress.setValue(0)
        self.direct_log = QTextEdit()
        self.direct_log.setReadOnly(True)
        self.direct_log.setMaximumHeight(120)
        # Image preview
        self.direct_image_preview = ImagePreview()
        self.direct_image_preview.setMinimumSize(200, 200)
        self.direct_image_preview.setMaximumSize(16777215, 16777215)
        # Layout
        layout.addWidget(url_label)
        layout.addWidget(self.direct_url_input)
        layout.addLayout(folder_layout)
        layout.addWidget(download_btn)
        layout.addWidget(self.direct_progress)
        layout.addWidget(self.direct_log)
        layout.addWidget(self.direct_image_preview)
        self.apply_theme(self.current_theme)

    def switch_to_gallery_mode(self):
        self.direct_mode = False
        self.setWindowTitle("ZeroScrape - IMG Scraping & Downloader BETAv2")
        self.init_ui()
        self.apply_theme(self.current_theme)

    def direct_browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Download Folder")
        if folder:
            self.direct_folder_input.setText(folder)

    def direct_download_image(self):
        url = self.direct_url_input.text().strip()
        folder = self.direct_folder_input.text().strip()
        if not url or not url.startswith("https://www.zerochan.net/"):
            self.direct_log.append("[ERROR] Please enter a valid Zerochan image page URL.")
            return
        if not folder:
            self.direct_log.append("[ERROR] Please select a download folder.")
            return
        os.makedirs(folder, exist_ok=True)
        self.direct_progress.setValue(0)
        self.direct_log.append("[INFO] Fetching image page...")
        try:
            import requests
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            html = resp.text
            # Use the same robust extraction as gallery
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            # Try <a id="download" href="...">
            a_download = soup.find('a', id='download')
            img_url = None
            if a_download and a_download.has_attr('href'):
                img_url = a_download['href']
                if img_url.startswith('//'):
                    img_url = 'https:' + img_url
                elif img_url.startswith('/'):
                    img_url = 'https://www.zerochan.net' + img_url
            # Fallback: any <a> with image extension
            if not img_url:
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if any(href.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif']):
                        if href.startswith('//'):
                            href = 'https:' + href
                        elif href.startswith('/'):
                            href = 'https://www.zerochan.net' + href
                        img_url = href
                        break
            # Fallback: <img id="image">
            if not img_url:
                img = soup.find('img', id='image')
                if img and img.has_attr('src'):
                    img_url = img['src']
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    elif img_url.startswith('/'):
                        img_url = 'https://www.zerochan.net' + img_url
            if not img_url:
                self.direct_log.append("[ERROR] Could not find image URL on page.")
                return
            self.direct_log.append(f"[INFO] Found image: {os.path.basename(img_url)}")
            self.direct_progress.setValue(30)
            # Download image
            img_resp = requests.get(img_url, timeout=30, stream=True)
            img_resp.raise_for_status()
            filename = os.path.basename(img_url)
            file_path = os.path.join(folder, filename)
            with open(file_path, 'wb') as f:
                for chunk in img_resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            self.direct_progress.setValue(100)
            self.direct_log.append(f"[SUCCESS] Downloaded: {filename}")
            self.direct_image_preview.set_image(file_path)
        except Exception as e:
            self.direct_log.append(f"[ERROR] {str(e)}")

    def apply_theme(self, theme_name):
        # Define multiple color themes
        themes = {
            'blue': {
                'accent': '#7dcfff',
                'accent2': '#1e90ff',
                'bg': '#181a20',
                'panel': '#23242b',
                'text': '#e0e0e0',
                'danger': '#ff5c5c',
                'warn': '#ffb347',
            },
            'green': {
                'accent': '#7dffb3',
                'accent2': '#1eff90',
                'bg': '#181a20',
                'panel': '#232b23',
                'text': '#e0ffe0',
                'danger': '#ff5c5c',
                'warn': '#ffe47d',
            },
            'purple': {
                'accent': '#c77dff',
                'accent2': '#a259ff',
                'bg': '#1a1820',
                'panel': '#23202b',
                'text': '#f0e0ff',
                'danger': '#ff5c9c',
                'warn': '#ffb3e6',
            },
            'orange': {
                'accent': '#ffb47d',
                'accent2': '#ff901e',
                'bg': '#201a18',
                'panel': '#2b2320',
                'text': '#fff0e0',
                'danger': '#ff5c5c',
                'warn': '#ffe47d',
            },
        }
        t = themes.get(theme_name, themes['blue'])
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background: {t['bg']};
                color: {t['text']};
                font-family: 'Segoe UI', 'Arial', sans-serif;
                font-size: 1em;
            }}
            QMenuBar {{
                background: {t['panel']};
                color: {t['accent']};
                border: none;
            }}
            QMenuBar::item {{
                background: transparent;
                color: {t['accent']};
                padding: 6px 18px;
            }}
            QMenuBar::item:selected {{
                background: {t['panel']};
                color: {t['accent2']};
                text-shadow: 0 0 8px {t['accent2']};
            }}
            QMenuBar::item:pressed {{
                background: {t['panel']};
                color: {t['accent2']};
            }}
            QMenu {{
                background: {t['panel']};
                color: {t['accent']};
                border: 1px solid {t['accent2']};
            }}
            QMenu::item {{
                background: transparent;
                color: {t['accent']};
                padding: 6px 24px 6px 24px;
            }}
            QMenu::item:selected {{
                background: {t['panel']};
                color: {t['accent2']};
                text-shadow: 0 0 8px {t['accent2']};
            }}
            QGroupBox {{
                background: {t['panel']};
                border: 1.5px solid {t['panel']};
                border-radius: 12px;
                margin-top: 10px;
                padding-top: 10px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.12);
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: {t['accent']};
                font-weight: bold;
                font-size: 1.1em;
                background: transparent;
            }}
            QLineEdit, QTextEdit {{
                background: {t['panel']};
                border: 1.5px solid #35363c;
                border-radius: 8px;
                padding: 6px;
                font-size: 1em;
                color: {t['text']};
                selection-background-color: {t['accent']};
            }}
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {t['panel']}, stop:1 #35363c);
                color: {t['accent']};
                border: 1.5px solid #35363c;
                border-radius: 8px;
                padding: 6px 10px;
                font-weight: 600;
                font-size: 1em;
                min-width: 0;
                margin: 2px;
                transition: background 0.2s;
            }}
            QPushButton:hover {{
                background: #2d2f36;
                color: {t['accent2']};
                border: 1.5px solid {t['accent2']};
            }}
            QPushButton:pressed {{
                background: {t['bg']};
                color: {t['accent2']};
                border: 1.5px solid {t['accent2']};
            }}
            QPushButton:disabled {{
                background: {t['panel']};
                color: #555;
                border: 1.5px solid #35363c;
            }}
            QProgressBar {{
                border: 1.5px solid #35363c;
                border-radius: 8px;
                background: {t['panel']};
                text-align: center;
                font-weight: 600;
                font-size: 1em;
                color: {t['text']};
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {t['accent']}, stop:1 {t['accent2']});
                border-radius: 8px;
            }}
            QLabel {{
                background: transparent;
                color: {t['text']};
            }}
            QListWidget {{
                background: {t['panel']};
                border: 1.5px solid #35363c;
                border-radius: 8px;
                color: {t['text']};
            }}
            QScrollArea {{
                background: {t['bg']};
            }}
        """)
        self.current_theme = theme_name

    def init_ui(self):
        # Top ribbon bar
        self.setWindowTitle("Zerochan Gallery Downloader")
        self.resize(990, 590)
        self.setMinimumSize(990, 590)
        # Menu bar
        menubar = QMenuBar(self)
        self.setMenuBar(menubar)
        # Mode menu
        self.mode_menu = QMenu("Mode", self)
        menubar.addMenu(self.mode_menu)
        self.gallery_mode_action = QAction("Gallery Download", self)
        self.direct_mode_action = QAction("Direct Download", self)
        self.mode_menu.addAction(self.gallery_mode_action)
        self.mode_menu.addAction(self.direct_mode_action)
        self.gallery_mode_action.triggered.connect(self.switch_to_gallery_mode)
        self.direct_mode_action.triggered.connect(self.switch_to_direct_download)
        # Settings menu
        settings_menu = QMenu("Settings", self)
        menubar.addMenu(settings_menu)
        # Silent Mode toggle
        self.silent_mode_action = QAction("Silent Mode", self, checkable=True)
        self.silent_mode_action.setChecked(self.silent_mode)
        self.silent_mode_action.triggered.connect(self.toggle_silent_mode)
        settings_menu.addAction(self.silent_mode_action)
        # Theme switcher
        theme_action = QWidget(self)
        theme_layout = QHBoxLayout(theme_action)
        theme_layout.setContentsMargins(8, 2, 8, 2)
        theme_label = QLabel("Theme:")
        theme_label.setStyleSheet("font-weight: bold; color: #888;")
        theme_combo = QComboBox()
        theme_combo.addItems(["Blue", "Green", "Purple", "Orange"])
        theme_combo.setCurrentIndex(0)
        theme_combo.setStyleSheet("min-width: 80px;")
        theme_layout.addWidget(theme_label)
        theme_layout.addWidget(theme_combo)
        # Add theme switcher to menu
        action_widget = QWidgetAction(self)
        action_widget.setDefaultWidget(theme_action)
        settings_menu.addAction(action_widget)
        # Help menu
        help_menu = QMenu("Help", self)
        menubar.addMenu(help_menu)
        about_action = QAction("About", self)
        help_menu.addAction(about_action)
        # Connect theme switcher
        def on_theme_change(idx):
            themes = ['blue', 'green', 'purple', 'orange']
            self.apply_theme(themes[idx])
        theme_combo.currentIndexChanged.connect(on_theme_change)
        # About dialog
        def show_about():
            QMessageBox.information(self, "About", "Zerochan Gallery Downloader\nModern PyQt5 GUI\nBy hendrixbrent.com")
        about_action.triggered.connect(show_about)
        # Add network speed widget to right side of menubar
        self.net_speed_label = QLabel()
        self.net_speed_label.setStyleSheet("font-weight: bold; color: #7dcfff; padding-right: 16px;")
        self.net_speed_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        menubar.setCornerWidget(self.net_speed_label, Qt.TopRightCorner)
        self.network_monitor.speed_updated.connect(self.update_network_speed_label)
        self.update_network_speed_label(0, 0)
        # Apply default theme
        self.apply_theme('blue')
        # Central widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        # Start in gallery mode
        self.switch_to_gallery_mode()
        # Status bar
        self.statusBar().showMessage("Ready")

    def toggle_silent_mode(self):
        try:
            if self.direct_mode:
                # Prevent toggling in direct mode
                return
            self.silent_mode = self.silent_mode_action.isChecked()
            # Refresh preview pane in current mode
            self.update_gallery_preview_silent()
        except Exception as e:
            self.show_error_dialog(f"Error toggling Silent Mode: {e}")

    def show_error_dialog(self, message):
        try:
            QMessageBox.critical(self, "Error", str(message))
        except Exception:
            print(f"Error: {message}")

    def update_gallery_preview_silent(self):
        try:
            if hasattr(self, 'image_preview') and self.image_preview is not None:
                # Remove any old container (which holds spinner and status)
                if hasattr(self, '_silent_container') and self._silent_container is not None:
                    try:
                        self._silent_container.setParent(None)
                        self._silent_container.deleteLater()
                    except Exception:
                        pass
                    self._silent_container = None
                if self.silent_mode:
                    self.image_preview.clear()
                    self._silent_container = QWidget(self.image_preview)
                    layout = QVBoxLayout(self._silent_container)
                    layout.setContentsMargins(0, 0, 0, 0)
                    layout.setSpacing(8)
                    spinner = LoadingSpinner(self._silent_container)
                    status_label = QLabel("Image preview disabled (Silent Mode)", self._silent_container)
                    status_label.setStyleSheet("color: #7dcfff; font-size: 1.1em; font-weight: bold;")
                    status_label.setAlignment(Qt.AlignCenter)
                    layout.addWidget(spinner, alignment=Qt.AlignCenter)
                    layout.addWidget(status_label, alignment=Qt.AlignCenter)
                    self._silent_container.setLayout(layout)
                    self._silent_container.setGeometry(0, 0, self.image_preview.width(), self.image_preview.height())
                    self._silent_container.show()
                else:
                    self.image_preview.setText("Waiting for image...")
        except Exception as e:
            try:
                self.show_error_dialog(f"Error updating gallery preview: {e}")
            except Exception:
                print(f"Error updating gallery preview: {e}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Recenter spinner/status container if present
        if hasattr(self, '_silent_container') and self._silent_container is not None and self._silent_container.isVisible():
            self._silent_container.setGeometry(0, 0, self.image_preview.width(), self.image_preview.height())

    def update_direct_preview_silent(self):
        try:
            if hasattr(self, 'direct_image_preview') and self.direct_image_preview is not None:
                if hasattr(self, '_direct_silent_container') and self._direct_silent_container is not None:
                    try:
                        self._direct_silent_container.setParent(None)
                        self._direct_silent_container.deleteLater()
                    except Exception:
                        pass
                    self._direct_silent_container = None
                if self.silent_mode:
                    self.direct_image_preview.clear()
                    self._direct_silent_container = QWidget(self.direct_image_preview)
                    layout = QVBoxLayout(self._direct_silent_container)
                    layout.setContentsMargins(0, 0, 0, 0)
                    layout.setSpacing(8)
                    spinner = LoadingSpinner(self._direct_silent_container)
                    status_label = QLabel("Image preview disabled (Silent Mode)", self._direct_silent_container)
                    status_label.setStyleSheet("color: #7dcfff; font-size: 1.1em; font-weight: bold;")
                    status_label.setAlignment(Qt.AlignCenter)
                    layout.addWidget(spinner, alignment=Qt.AlignCenter)
                    layout.addWidget(status_label, alignment=Qt.AlignCenter)
                    self._direct_silent_container.setLayout(layout)
                    self._direct_silent_container.setGeometry(0, 0, self.direct_image_preview.width(), self.direct_image_preview.height())
                    self._direct_silent_container.show()
                else:
                    self.direct_image_preview.setText("Waiting for image...")
        except Exception as e:
            try:
                self.show_error_dialog(f"Error updating direct preview: {e}")
            except Exception:
                print(f"Error updating direct preview: {e}")

    def switch_to_gallery_mode(self):
        self.silent_mode_action.setEnabled(True)
        self.silent_mode_action.setChecked(self.silent_mode)
        self.setWindowTitle("Zerochan Gallery Downloader")
        self.clear_main_layout()
        # Left panel (controls) with scroll area
        left_panel = QWidget()
        left_panel.setMaximumWidth(400)  # Increase max width for left panel
        left_panel.setMinimumWidth(240)
        left_layout = QVBoxLayout(left_panel)

        # URL input section
        url_group = QGroupBox("Gallery URL")
        url_layout = QVBoxLayout(url_group)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter Zerochan gallery URL (e.g., https://www.zerochan.net/Sparkle?q=sparkle)")
        self.url_input.setText("")
        url_layout.addWidget(self.url_input)
        # Download folder section
        folder_layout = QHBoxLayout()
        self.folder_input = QLineEdit()
        self.folder_input.setPlaceholderText("Download folder path")
        self.folder_input.setText(os.path.join(os.path.expanduser("~"), "Downloads", "Zerochan"))
        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_folder)
        folder_layout.addWidget(self.folder_input)
        folder_layout.addWidget(self.browse_button)
        url_layout.addLayout(folder_layout)
        left_layout.addWidget(url_group)
        # Login section
        login_group = QGroupBox("Zerochan Login (for protected images)")
        login_layout = QVBoxLayout(login_group)
        self.gallery_login_username_input = QLineEdit()
        self.gallery_login_username_input.setPlaceholderText("Username (optional)")
        self.gallery_login_password_input = QLineEdit()
        self.gallery_login_password_input.setPlaceholderText("Password (optional)")
        self.gallery_login_password_input.setEchoMode(QLineEdit.Password)
        self.gallery_login_status_label = QLabel("")
        self.gallery_login_status_label.setStyleSheet("color: #ffb347; font-size: 0.95em;")
        login_layout.addWidget(self.gallery_login_username_input)
        login_layout.addWidget(self.gallery_login_password_input)
        login_layout.addWidget(self.gallery_login_status_label)
        left_layout.addWidget(login_group)
        # Settings section
        settings_group = QGroupBox("Settings")
        settings_layout = QGridLayout(settings_group)
        settings_layout.addWidget(QLabel("Max Concurrent Downloads:"), 0, 0)
        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 10)
        self.concurrent_spin.setValue(3)
        settings_layout.addWidget(self.concurrent_spin, 0, 1)
        self.create_subfolders_cb = QCheckBox("Create character subfolders")
        self.create_subfolders_cb.setChecked(True)
        settings_layout.addWidget(self.create_subfolders_cb, 1, 0, 1, 2)
        left_layout.addWidget(settings_group)
        # Control buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(4)
        button_layout.setContentsMargins(0, 8, 0, 8)
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.start_download)
        self.start_button.setMinimumWidth(0)
        self.start_button.setMaximumWidth(16777215)
        self.start_button.setSizePolicy(self.start_button.sizePolicy().horizontalPolicy(), self.start_button.sizePolicy().verticalPolicy())
        self.start_button.setStyleSheet("""
            QPushButton {
                background: #23242b;
                color: #7dcfff;
                border: 2px solid #7dcfff;
                border-radius: 8px;
                font-weight: bold;
                font-size: 1em;
                min-width: 0;
                padding: 4px 0;
            }
            QPushButton:hover {
                background: #1e222a;
                color: #fff;
                border: 2px solid #7dcfff;
            }
            QPushButton:pressed {
                background: #111216;
                color: #7dcfff;
                border: 2px solid #7dcfff;
            }
            QPushButton:disabled {
                background: #23242b;
                color: #555;
                border: 2px solid #35363c;
            }
        """)
        self.interrupt_button = QPushButton("Interrupt")
        self.interrupt_button.clicked.connect(self.interrupt_and_download)
        self.interrupt_button.setEnabled(False)
        self.interrupt_button.setMinimumWidth(0)
        self.interrupt_button.setMaximumWidth(16777215)
        self.interrupt_button.setSizePolicy(self.interrupt_button.sizePolicy().horizontalPolicy(), self.interrupt_button.sizePolicy().verticalPolicy())
        self.interrupt_button.setStyleSheet("""
            QPushButton {
                background: #ffb347;
                color: #23242b;
                border: 2px solid #ffb347;
                border-radius: 8px;
                font-weight: bold;
                font-size: 1em;
                min-width: 0;
                padding: 4px 0;
            }
            QPushButton:hover {
                background: #ff9800;
                color: #fff;
                border: 2px solid #ff9800;
            }
            QPushButton:pressed {
                background: #b26a00;
                color: #fff;
                border: 2px solid #b26a00;
            }
            QPushButton:disabled {
                background: #23242b;
                color: #555;
                border: 2px solid #35363c;
            }
        """)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_download)
        self.stop_button.setEnabled(False)
        self.stop_button.setMinimumWidth(0)
        self.stop_button.setMaximumWidth(16777215)
        self.stop_button.setSizePolicy(self.stop_button.sizePolicy().horizontalPolicy(), self.stop_button.sizePolicy().verticalPolicy())
        self.stop_button.setStyleSheet("""
            QPushButton {
                background: #ff5c5c;
                color: #fff;
                border: 2px solid #ff5c5c;
                border-radius: 8px;
                font-weight: bold;
                font-size: 1em;
                min-width: 0;
                padding: 4px 0;
            }
            QPushButton:hover {
                background: #e74c3c;
                color: #fff;
                border: 2px solid #e74c3c;
            }
            QPushButton:pressed {
                background: #a93226;
                color: #fff;
                border: 2px solid #a93226;
            }
            QPushButton:disabled {
                background: #23242b;
                color: #555;
                border: 2px solid #35363c;
            }
        """)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.interrupt_button)
        button_layout.addWidget(self.stop_button)
        left_layout.addLayout(button_layout)
        # Progress section
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)
        progress_layout.addWidget(QLabel("Scanning Progress:"))
        self.scanning_progress_bar = QProgressBar()
        self.scanning_progress_bar.setTextVisible(True)
        self.scanning_progress_bar.setFormat("Page %v - %p% (%m images found)")
        self.scanning_progress_bar.setVisible(False)
        progress_layout.addWidget(self.scanning_progress_bar)
        progress_layout.addWidget(QLabel("Download Progress:"))
        self.overall_progress = QProgressBar()
        self.overall_progress.setTextVisible(True)
        progress_layout.addWidget(self.overall_progress)
        self.progress_label = QLabel("Ready to start...")
        progress_layout.addWidget(self.progress_label)
        left_layout.addWidget(progress_group)
        # Log section
        log_group = QGroupBox("Download Log")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(200)
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        left_layout.addWidget(log_group)
        # Make left panel scrollable
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setWidget(left_panel)
        left_scroll.setMinimumWidth(240)
        left_scroll.setMaximumWidth(400)

        # Right panel (portrait preview only)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        preview_group = QGroupBox("Image Preview")
        preview_layout = QVBoxLayout(preview_group)
        self.image_preview = ImagePreview()
        self.image_preview.setMinimumSize(400, 400)  # Make preview even larger
        self.image_preview.setMaximumSize(16777215, 16777215)
        preview_layout.addWidget(self.image_preview)
        self.current_image_label = QLabel("")
        self.current_image_label.setAlignment(Qt.AlignCenter)
        self.current_image_label.setWordWrap(True)
        self.current_image_label.setStyleSheet("font-weight: bold; color: #7dcfff; font-size: 1.1em;")
        preview_layout.addWidget(self.current_image_label)
        right_layout.addWidget(preview_group)

        # Add panels to main layout with stretch factors
        self.main_layout.addWidget(left_scroll, 0)
        self.main_layout.addWidget(right_panel, 3)  # Make right panel take much more space

    def switch_to_direct_download(self):
        self.silent_mode_action.setEnabled(False)
        self.silent_mode_action.setChecked(False)
        self.silent_mode = False
        self.clear_main_layout()
        # Left panel (controls)
        left_panel = QWidget()
        left_panel.setMaximumWidth(400)
        left_panel.setMinimumWidth(240)
        left_layout = QVBoxLayout(left_panel)

        # URL input section
        url_group = QGroupBox("Direct Image URL")
        url_layout = QVBoxLayout(url_group)

        self.direct_url_input = QLineEdit()
        self.direct_url_input.setPlaceholderText("Enter Zerochan image page URL (e.g., https://www.zerochan.net/3903835)")
        self.direct_url_input.setText("")
        url_layout.addWidget(self.direct_url_input)

        # Download folder section
        folder_layout = QHBoxLayout()
        self.direct_folder_input = QLineEdit()
        self.direct_folder_input.setPlaceholderText("Download folder path")
        self.direct_folder_input.setText(os.path.join(os.path.expanduser("~"), "Downloads", "Zerochan"))

        self.direct_browse_button = QPushButton("Browse")
        self.direct_browse_button.clicked.connect(self.browse_direct_folder)

        folder_layout.addWidget(self.direct_folder_input)
        folder_layout.addWidget(self.direct_browse_button)
        url_layout.addLayout(folder_layout)

        left_layout.addWidget(url_group)

        # Login section
        login_group = QGroupBox("Zerochan Login (for protected images)")
        login_layout = QVBoxLayout(login_group)
        self.login_username_input = QLineEdit()
        self.login_username_input.setPlaceholderText("Username (optional)")
        self.login_password_input = QLineEdit()
        self.login_password_input.setPlaceholderText("Password (optional)")
        self.login_password_input.setEchoMode(QLineEdit.Password)
        self.login_status_label = QLabel("")
        self.login_status_label.setStyleSheet("color: #ffb347; font-size: 0.95em;")
        login_layout.addWidget(self.login_username_input)
        login_layout.addWidget(self.login_password_input)
        login_layout.addWidget(self.login_status_label)
        left_layout.addWidget(login_group)

        # Control buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(4)
        button_layout.setContentsMargins(0, 8, 0, 8)
        self.direct_download_button = QPushButton("Download")
        self.direct_download_button.clicked.connect(self.start_direct_download)
        self.direct_download_button.setMinimumWidth(0)
        self.direct_download_button.setMaximumWidth(16777215)
        self.direct_download_button.setStyleSheet("""
            QPushButton {
                background: #23242b;
                color: #7dcfff;
                border: 2px solid #7dcfff;
                border-radius: 8px;
                font-weight: bold;
                font-size: 1em;
                min-width: 0;
                padding: 4px 0;
            }
            QPushButton:hover {
                background: #1e222a;
                color: #7dcfff;
                border: 2px solid #7dcfff;
            }
            QPushButton:pressed {
                background: #111216;
                color: #7dcfff;
                border: 2px solid #7dcfff;
            }
            QPushButton:disabled {
                background: #23242b;
                color: #555;
                border: 2px solid #35363c;
            }
        """)
        button_layout.addWidget(self.direct_download_button)
        left_layout.addLayout(button_layout)

        # Progress section
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)

        self.direct_progress_label = QLabel("Ready to download...")
        progress_layout.addWidget(self.direct_progress_label)

        left_layout.addWidget(progress_group)

        # Log section
        log_group = QGroupBox("Download Log")
        log_layout = QVBoxLayout(log_group)

        self.direct_log_text = QTextEdit()
        self.direct_log_text.setMaximumHeight(200)
        self.direct_log_text.setReadOnly(True)
        log_layout.addWidget(self.direct_log_text)

        left_layout.addWidget(log_group)

        # Right panel (image preview)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        preview_group = QGroupBox("Image Preview")
        preview_layout = QVBoxLayout(preview_group)

        self.direct_image_preview = ImagePreview()
        self.direct_image_preview.setMinimumSize(400, 400)
        self.direct_image_preview.setMaximumSize(16777215, 16777215)
        preview_layout.addWidget(self.direct_image_preview)
        self.direct_current_image_label = QLabel("")
        self.direct_current_image_label.setAlignment(Qt.AlignCenter)
        self.direct_current_image_label.setWordWrap(True)
        self.direct_current_image_label.setStyleSheet("font-weight: bold; color: #7dcfff; font-size: 1.1em;")
        preview_layout.addWidget(self.direct_current_image_label)

        right_layout.addWidget(preview_group)

        # Add panels to main layout
        self.main_layout.addWidget(left_panel, 0)
        self.main_layout.addWidget(right_panel, 3)

    def browse_direct_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Download Folder")
        if folder:
            self.direct_folder_input.setText(folder)

    def start_direct_download(self):
        import requests, time, os
        from bs4 import BeautifulSoup
        url = self.direct_url_input.text().strip()
        folder = self.direct_folder_input.text().strip()
        username = self.login_username_input.text().strip()
        password = self.login_password_input.text()
        self.direct_log_text.clear()
        self.direct_progress_label.setText("Starting direct download...")
        self.direct_current_image_label.setText("")
        self.direct_image_preview.setText("Waiting for image...")
        self.login_status_label.setText("")
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a Zerochan image page URL")
            return
        if not folder:
            QMessageBox.warning(self, "Error", "Please select a download folder")
            return
        if not url.startswith("https://www.zerochan.net/"):
            QMessageBox.warning(self, "Error", "Please enter a valid Zerochan image page URL")
            return
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not create download folder: {str(e)}")
            return
        # Download logic
        self.direct_log_text.append("[INFO] Fetching image page...")
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        # If credentials provided, try to login first
        logged_in = False
        if username and password:
            self.login_status_label.setText("Logging in...")
            self.direct_log_text.append("[INFO] Attempting login...")
            try:
                login_url = "https://www.zerochan.net/login"
                login_page = session.get(login_url, timeout=15)
                login_page.raise_for_status()
                soup = BeautifulSoup(login_page.text, 'html.parser')
                token_input = soup.find('input', {'name': 'authenticity_token'})
                authenticity_token = token_input['value'] if token_input else ''
                # Collect all hidden fields (sometimes more than just authenticity_token)
                payload = {i['name']: i.get('value', '') for i in soup.find_all('input', {'type': 'hidden', 'name': True})}
                payload['name'] = username
                payload['password'] = password
                payload['login'] = 'Login'
                headers = {
                    'Referer': login_url,
                    'User-Agent': session.headers['User-Agent'],
                }
                resp_login = session.post(login_url, data=payload, headers=headers, timeout=15, allow_redirects=True)
                # Debug: Save login response if login fails
                if resp_login.url.endswith('/login') or 'login' in resp_login.url or 'incorrect' in resp_login.text.lower():
                    debug_path = os.path.join(folder, 'debug_login_failed.html')
                    with open(debug_path, 'w', encoding='utf-8') as f:
                        f.write("POST data: " + str(payload) + "\n\n")
                        f.write("Status code: " + str(resp_login.status_code) + "\n\n")
                        f.write("Headers:\n" + str(resp_login.headers) + "\n\n")
                        f.write("First 2000 chars of page HTML:\n" + resp_login.text[:2000])
                    self.login_status_label.setText("Login failed. Check credentials or see debug_login_failed.html.")
                    self.direct_log_text.append(f"[ERROR] Login failed. Debug info saved to {debug_path}.")
                    # Check for captcha or anti-bot
                    if 'captcha' in resp_login.text.lower():
                        self.direct_log_text.append("[ERROR] Captcha detected. Manual login required in browser.")
                    return
                if 'logout' in resp_login.text.lower() or 'profile' in resp_login.text.lower():
                    logged_in = True
                    self.login_status_label.setText("Login successful.")
                    self.direct_log_text.append("[INFO] Login successful.")
                else:
                    debug_path = os.path.join(folder, 'debug_login_failed.html')
                    with open(debug_path, 'w', encoding='utf-8') as f:
                        f.write("POST data: " + str(payload) + "\n\n")
                        f.write("Status code: " + str(resp_login.status_code) + "\n\n")
                        f.write("Headers:\n" + str(resp_login.headers) + "\n\n")
                        f.write("First 2000 chars of page HTML:\n" + resp_login.text[:2000])
                    self.login_status_label.setText("Login failed. See debug_login_failed.html.")
                    self.direct_log_text.append(f"[ERROR] Login failed. Debug info saved to {debug_path}.")
                    return
            except Exception as e:
                self.login_status_label.setText(f"Login error: {str(e)}")
                self.direct_log_text.append(f"[ERROR] Login error: {str(e)}")
                return
        try:
            time.sleep(0.7)  # Be respectful to the server
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            img_url = None
            def is_valid_image_url(u):
                if not u:
                    return False
                invalid_patterns = ['logo', 'favicon', 'avatar', 'icon', 'button', 'banner', 'thumb']
                u_lower = u.lower()
                for pat in invalid_patterns:
                    if pat in u_lower:
                        return False
                valid_exts = ['.jpg', '.jpeg', '.png', '.gif']
                if not any(u_lower.endswith(ext) for ext in valid_exts):
                    return False
                return True
            # 1. Try <a id="download" href="...">
            a_download = soup.find('a', id='download')
            if a_download and a_download.has_attr('href'):
                candidate = a_download['href']
                if candidate.startswith('//'):
                    candidate = 'https:' + candidate
                elif candidate.startswith('/'):
                    candidate = 'https://www.zerochan.net' + candidate
                if is_valid_image_url(candidate):
                    img_url = candidate
            # 2. Try all <a> with href ending in image extension, filter for valid
            if not img_url:
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if href.startswith('//'):
                        href = 'https:' + href
                    elif href.startswith('/'):
                        href = 'https://www.zerochan.net' + href
                    if is_valid_image_url(href):
                        img_url = href
                        break
            # 3. Try <img id="image"> or <img class="full ...">
            if not img_url:
                img = soup.find('img', id='image')
                if not img:
                    img = soup.find('img', class_=lambda x: x and 'full' in x)
                if img and img.has_attr('src'):
                    candidate = img['src']
                    if candidate.startswith('//'):
                        candidate = 'https:' + candidate
                    elif candidate.startswith('/'):
                        candidate = 'https://www.zerochan.net' + candidate
                    if is_valid_image_url(candidate):
                        img_url = candidate
            # 4. Try any <img> with src ending in image extension, filter for valid
            if not img_url:
                for img in soup.find_all('img', src=True):
                    src = img['src']
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = 'https://www.zerochan.net' + src
                    if is_valid_image_url(src):
                        img_url = src
                        break
            if not img_url:
                # Save debug info as plain text
                debug_path = os.path.join(folder, 'debug_last_failed_page.txt')
                with open(debug_path, 'w', encoding='utf-8') as f:
                    f.write("URL: " + url + "\n\n")
                    f.write("Status code: " + str(resp.status_code) + "\n\n")
                    f.write("Headers:\n" + str(resp.headers) + "\n\n")
                    f.write("First 2000 chars of page HTML:\n" + resp.text[:2000])
                self.direct_log_text.append(f"[ERROR] Could not find image URL on page. Debug info saved to {debug_path}.")
                self.direct_progress_label.setText("Failed to find image.")
                return
            # Download the image
            self.direct_log_text.append(f"[INFO] Downloading image: {img_url}")
            filename = os.path.basename(img_url.split('?')[0])
            file_path = os.path.join(folder, filename)
            time.sleep(0.7)  # Be respectful to the server
            img_resp = session.get(img_url, timeout=30, stream=True)
            img_resp.raise_for_status()
            with open(file_path, 'wb') as f:
                for chunk in img_resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            self.direct_log_text.append(f"[SUCCESS] Downloaded: {filename}")
            self.direct_progress_label.setText(f"Downloaded: {filename}")
            self.direct_current_image_label.setText(f"Downloaded: {filename}")
            if not self.silent_mode:
                self.direct_image_preview.set_image(file_path)
            else:
                self.update_direct_preview_silent()
        except Exception as e:
            self.direct_log_text.append(f"[ERROR] {str(e)}")
            self.direct_progress_label.setText(f"Error: {str(e)}")
        
    def center_window(self):
        """Center the window on screen"""
        screen = QApplication.desktop().screenGeometry()
        size = self.geometry()
        self.move(
            (screen.width() - size.width()) // 2,
            (screen.height() - size.height()) // 2
        )
        
    def browse_folder(self):
        """Browse for download folder"""
        folder = QFileDialog.getExistingDirectory(self, "Select Download Folder")
        if folder:
            self.folder_input.setText(folder)
            
    def start_download(self):
        """Start the download process, with optional login for protected images"""
        import requests
        from bs4 import BeautifulSoup
        url = self.url_input.text().strip()
        folder = self.folder_input.text().strip()
        username = self.gallery_login_username_input.text().strip()
        password = self.gallery_login_password_input.text()
        self.gallery_login_status_label.setText("")
        
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a gallery URL")
            return
        if not folder:
            QMessageBox.warning(self, "Error", "Please select a download folder")
            return
        if not url.startswith("https://www.zerochan.net/"):
            QMessageBox.warning(self, "Error", "Please enter a valid Zerochan URL")
            return
        # Create download folder if it doesn't exist
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not create download folder: {str(e)}")
            return
        # Prepare session for downloader
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        # If credentials provided, try to login first
        if username and password:
            self.gallery_login_status_label.setText("Logging in...")
            try:
                login_url = "https://www.zerochan.net/login"
                login_page = session.get(login_url, timeout=15)
                login_page.raise_for_status()
                soup = BeautifulSoup(login_page.text, 'html.parser')
                payload = {i['name']: i.get('value', '') for i in soup.find_all('input', {'type': 'hidden', 'name': True})}
                payload['name'] = username
                payload['password'] = password
                payload['login'] = 'Login'
                headers = {
                    'Referer': login_url,
                    'User-Agent': session.headers['User-Agent'],
                }
                resp_login = session.post(login_url, data=payload, headers=headers, timeout=15, allow_redirects=True)
                if resp_login.url.endswith('/login') or 'login' in resp_login.url or 'incorrect' in resp_login.text.lower():
                    debug_path = os.path.join(folder, 'debug_gallery_login_failed.html')
                    with open(debug_path, 'w', encoding='utf-8') as f:
                        f.write("POST data: " + str(payload) + "\n\n")
                        f.write("Status code: " + str(resp_login.status_code) + "\n\n")
                        f.write("Headers:\n" + str(resp_login.headers) + "\n\n")
                        f.write("First 2000 chars of page HTML:\n" + resp_login.text[:2000])
                    self.gallery_login_status_label.setText("Login failed. See debug_gallery_login_failed.html.")
                    self.add_log_message("[ERROR] Gallery login failed. Debug info saved to debug_gallery_login_failed.html.")
                    if 'captcha' in resp_login.text.lower():
                        self.add_log_message("[ERROR] Captcha detected. Manual login required in browser.")
                    return
                if 'logout' in resp_login.text.lower() or 'profile' in resp_login.text.lower():
                    self.gallery_login_status_label.setText("Login successful.")
                    self.add_log_message("[INFO] Gallery login successful.")
                else:
                    debug_path = os.path.join(folder, 'debug_gallery_login_failed.html')
                    with open(debug_path, 'w', encoding='utf-8') as f:
                        f.write("POST data: " + str(payload) + "\n\n")
                        f.write("Status code: " + str(resp_login.status_code) + "\n\n")
                        f.write("Headers:\n" + str(resp_login.headers) + "\n\n")
                        f.write("First 2000 chars of page HTML:\n" + resp_login.text[:2000])
                    self.gallery_login_status_label.setText("Login failed. See debug_gallery_login_failed.html.")
                    self.add_log_message("[ERROR] Gallery login failed. Debug info saved to debug_gallery_login_failed.html.")
                    return
            except Exception as e:
                self.gallery_login_status_label.setText(f"Login error: {str(e)}")
                self.add_log_message(f"[ERROR] Gallery login error: {str(e)}")
                return
        # Start download thread, pass session to ImageDownloader
        self.downloader_thread = ImageDownloader(
            url,
            folder,
            self.concurrent_spin.value(),
            network_monitor=self.network_monitor,
            session=session
        )
        # Connect signals
        self.downloader_thread.progress_updated.connect(self.update_progress)
        self.downloader_thread.image_downloaded.connect(self.on_image_downloaded)
        self.downloader_thread.log_message.connect(self.add_log_message)
        self.downloader_thread.error_occurred.connect(self.on_error)
        self.downloader_thread.current_image_signal.connect(self.update_current_image)
        self.downloader_thread.finished_download.connect(self.on_download_finished)
        self.downloader_thread.scanning_progress.connect(self.update_scanning_progress)
        self.downloader_thread.start()
        # Update UI
        self.start_button.setEnabled(False)
        self.interrupt_button.setEnabled(True)
        self.stop_button.setEnabled(True)
        self.overall_progress.setValue(0)
        self.scanning_progress_bar.setVisible(True)
        self.scanning_progress_bar.setValue(0)
        self.progress_label.setText("Starting gallery scan...")
        self.log_text.clear()
        self.statusBar().showMessage("Scanning gallery pages...")
        
    def interrupt_and_download(self):
        """Interrupt scanning and start downloading found images"""
        if self.downloader_thread and self.downloader_thread.isRunning():
            self.downloader_thread.interrupt_and_download()
            self.interrupt_button.setEnabled(False)
            self.add_log_message("Switching from scanning to download mode...")
            self.statusBar().showMessage("Interrupted scanning - starting download...")
            
    def stop_download(self):
        """Stop the download process"""
        if self.downloader_thread and self.downloader_thread.isRunning():
            self.downloader_thread.stop()
            self.add_log_message("Download stopped by user")
            self.on_download_finished()
            
    def update_scanning_progress(self, current_page, total_images):
        """Update scanning progress"""
        self.scanning_progress_bar.setValue(current_page)
        self.scanning_progress_bar.setMaximum(max(current_page, 1))
        self.scanning_progress_bar.setFormat(f"Page {current_page} - {total_images} images found")
        self.progress_label.setText(f"Scanning page {current_page} - Found {total_images} images so far")
            
    def update_progress(self, current, total):
        """Update progress bar"""
        if total > 0:
            progress = int((current / total) * 100)
            self.overall_progress.setValue(progress)
            self.progress_label.setText(f"Downloaded {current} of {total} images ({progress}%)")
            if self.scanning_progress_bar.isVisible():
                self.scanning_progress_bar.setVisible(False)
                self.statusBar().showMessage("Download in progress...")
            
    def on_image_downloaded(self, image_path, image_url):
        """Handle image download completion"""
        self.add_log_message(f"Downloaded: {os.path.basename(image_path)}")
        if not self.silent_mode:
            self.image_preview.set_image(image_path)
        else:
            self.update_gallery_preview_silent()
        
    def update_current_image(self, image_url, filename):
        """Update currently downloading image info and preview"""
        self.current_image_label.setText(f"Downloading: {filename}")
        if not self.silent_mode:
            self.image_preview.set_current_downloading(filename, image_url=image_url)
        else:
            self.update_gallery_preview_silent()

    def add_log_message(self, message):
        """Add message to log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        self.log_text.append(formatted_message)
        
    def on_error(self, error_message):
        """Handle errors"""
        self.add_log_message(f"ERROR: {error_message}")
        QMessageBox.critical(self, "Error", error_message)
        self.on_download_finished()
        
    def on_download_finished(self):
        """Handle download completion"""
        self.start_button.setEnabled(True)
        self.interrupt_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.scanning_progress_bar.setVisible(False)
        self.statusBar().showMessage("Download completed")
        self.add_log_message("Download process finished")
        
    def closeEvent(self, event):
        """Handle application close"""
        if self.downloader_thread and self.downloader_thread.isRunning():
            self.downloader_thread.stop()
            self.downloader_thread.wait()
        event.accept()

    def update_network_speed_label(self, download_bps, upload_bps):
        # Helper to format speed
        def fmt_speed(bps):
            if bps >= 1024 * 1024:
                return f"{bps / (1024*1024):.2f} MB/s"
            elif bps >= 1024:
                return f"{bps / 1024:.1f} KB/s"
            else:
                return f"{bps:.0f} B/s"
        down = fmt_speed(download_bps)
        up = fmt_speed(upload_bps)
        # Unicode: 53D (down arrow), 53C (up arrow) or use 193 and 191
        self.net_speed_label.setText(f'<span style="color:#7dcfff;">&#8595; {down} &nbsp; &#8593; {up}</span>')

def main():
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("ZeroScrape Version 6.2Beta")
    app.setApplicationVersion("6.2")
    app.setOrganizationName("ImageDownloader")
    
    # Create and show main window
    window = ZerochanDownloader()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

# Global exception hook for robust error management
import sys
from PyQt5.QtWidgets import QApplication, QMessageBox
import sip

def excepthook(type, value, traceback):
    msg = f"{type.__name__}: {value}"
    app = QApplication.instance()
    if app:
        QMessageBox.critical(None, "Unhandled Exception", msg)
    else:
        print(msg)

sys.excepthook = excepthook
