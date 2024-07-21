import configparser
import sys
import socket
import json
import threading
from datetime import datetime
from enum import Enum

from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget, QListWidget, QListWidgetItem, \
    QSystemTrayIcon, QDialog, QLabel, QDialogButtonBox, QGridLayout, QHBoxLayout
from PySide6.QtCore import Signal, QObject, Qt
from PySide6.QtGui import QIcon

from client.client_script import send_data


class PatientStatus(Enum):
    NEW = "New"
    IN_PROGRESS = "In Progress"
    DONE = "Done"


class ResultNotifier(QObject):
    new_result_signal = Signal(dict)


class ResultDialog(QDialog):
    def __init__(self, study_description, pathologies, condition_probabilities, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{study_description} - Result Details")

        # Create the layout
        layout = QGridLayout()
        self.setLayout(layout)

        # Set up labels for headers
        layout.addWidget(QLabel("Pathology"), 0, 0)
        layout.addWidget(QLabel("Probability"), 0, 1)
        layout.addWidget(QLabel("Min Probability"), 0, 2)
        layout.addWidget(QLabel("Status"), 0, 3)

        # Sort pathologies from most to least probable
        sorted_pathologies = sorted(pathologies.items(), key=lambda x: x[1], reverse=True)

        index = 0

        # Add rows to the layout
        for index, (pathology, probability) in enumerate(sorted_pathologies, start=1):
            # Pathology name
            layout.addWidget(QLabel(pathology), index, 0)

            # Probability value
            prob_label = QLabel(f"{probability:.2f}")
            layout.addWidget(prob_label, index, 1)

            # Min probability from config
            min_prob = condition_probabilities.get(pathology, 0)
            min_prob_label = QLabel(f"{min_prob:.2f}")
            layout.addWidget(min_prob_label, index, 2)

            # Status icon or label
            if probability >= min_prob:
                status_icon_path = "images/warning_icon.png"
            else:
                status_icon_path = "images/checkmark_icon.png"

            status_icon = QLabel()
            status_icon.setPixmap(QIcon(status_icon_path).pixmap(16, 16))
            layout.addWidget(status_icon, index, 3)

        # Add the OK button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box, index + 1, 0, 1, 4)


class PatientWidget(QWidget):
    def __init__(self, patient, pathologies, time: datetime, parent=None):
        super().__init__(parent)

        # Main horizontal layout
        self.mainLayout = QHBoxLayout()
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.mainLayout.setSpacing(10)
        self.setLayout(self.mainLayout)

        # Fixed width patient label
        self.patient_label = QLabel(f"{patient}")
        self.patient_label.setFixedWidth(150)
        self.patient_label.setStyleSheet('font-weight: bold; color: rgb(0, 0, 255);')
        self.mainLayout.addWidget(self.patient_label)

        # Fixed width time label
        self.time_label = QLabel(f"{time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.time_label.setFixedWidth(150)
        self.time_label.setStyleSheet('color: rgb(150, 150, 150);')
        self.mainLayout.addWidget(self.time_label)

        # Fixed width icon label
        self.iconQLabel = QLabel()
        if pathologies:
            self.iconQLabel.setPixmap(QIcon("images/warning_icon.png").pixmap(16, 16))
        self.iconQLabel.setFixedWidth(30)
        self.mainLayout.addWidget(self.iconQLabel)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BrainScan Alert")
        self.setFixedSize(400, 500)
        self.brainscan_icon = QIcon("images/small_brainscan_icon.jpg")
        self.setWindowIcon(self.brainscan_icon)

        self.list_widget = QListWidget()
        self.results_count = QLabel()
        self.update_results_count()
        layout = QVBoxLayout()
        layout.addWidget(self.results_count)
        layout.addWidget(self.list_widget)

        self.setLayout(layout)

        self.result_notifier = ResultNotifier()
        self.result_notifier.new_result_signal.connect(self.handle_json_data)

        self.tray_icon = QSystemTrayIcon(self.brainscan_icon, self)
        self.tray_icon.setVisible(True)

        self.config = configparser.ConfigParser()
        self.config.read('config.ini')

        self.condition_probabilities = self.get_condition_probabilities()

        self.list_widget.itemDoubleClicked.connect(self.show_result_details)

    def get_condition_probabilities(self):
        return {key: float(value) for key, value in self.config['CONDITIONS_PROBABILITIES'].items()}

    def handle_json_data(self, data: dict):
        study_description = data.get("StudyDescription", "Unknown")
        results = data.get("AnalysisResults")
        if results is None:
            print("AnalysisResults are missing in the json file.")
            return

        translations = data.get("translation")
        if translations is None:
            print("translations are missing in the json file.")
            return

        if results:
            time = data.get("created")
            if time is not None:
                time = datetime.fromisoformat(time)
            self.add_result(study_description, results, time)
            self.update_results_count()

    def add_result(self, study_description, pathologies, time):
        item_widget = PatientWidget(study_description, pathologies, time)
        item = QListWidgetItem(self.list_widget)
        item.setSizeHint(item_widget.sizeHint())  # Ensure consistency
        item.setData(Qt.ItemDataRole.UserRole, (study_description, pathologies))
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, item_widget)

        self.tray_icon.showMessage(
            "New patient results",
            f"Received new results for: {study_description}",
            QSystemTrayIcon.MessageIcon.Information,
            10000
        )

    def update_results_count(self):
        self.results_count.setText(f"Results: {self.list_widget.count()}")

    def show_result_details(self, item):
        study_description, pathologies = item.data(Qt.ItemDataRole.UserRole)
        dialog = ResultDialog(study_description, pathologies, self.condition_probabilities, self)
        dialog.exec()


def listen_for_results(notifier):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('localhost', 12345))
    sock.listen(1)

    while True:
        conn, addr = sock.accept()
        with conn:
            buffer = b""
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                buffer += data
            try:
                message = buffer.decode('utf-8')
                json_data = json.loads(message)
                notifier.new_result_signal.emit(json_data)
            except json.JSONDecodeError as e:
                print(f"Failed to decode JSON: {e}")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("BrainScan Alert")

    window = MainWindow()
    window.show()

    listener_thread = threading.Thread(target=listen_for_results, args=(window.result_notifier,))
    listener_thread.daemon = True
    listener_thread.start()

    send_data("client/example-results-1.json")
    send_data("client/example-results-2.json")
    send_data("client/example-results-3.json")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
