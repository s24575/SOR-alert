import configparser
import sys
import socket
import json
import threading
from datetime import datetime

from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget, QListWidget, QListWidgetItem, \
    QSystemTrayIcon, QDialog, QLabel, QDialogButtonBox, QHBoxLayout, QGridLayout
from PySide6.QtCore import Signal, QObject, Qt
from PySide6.QtGui import QIcon

from client.client_script import send_data


class ResultNotifier(QObject):
    new_result_signal = Signal(dict)


class ResultDialog(QDialog):
    def __init__(self, patient, pathologies, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Patient: {patient} - Result Details")

        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"Patient: {patient}"))

        for pathology, probability in pathologies:
            layout.addWidget(QLabel(f"{pathology}: {probability}"))

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        self.setLayout(layout)


class PatientWidget(QWidget):
    def __init__(self, patient, pathologies, time: datetime, parent=None):
        super().__init__(parent)

        # Main layout
        self.mainLayout = QGridLayout()

        # Patient name label
        self.patient_label = QLabel(f"Patient: {patient}")
        self.patient_label.setStyleSheet('font-weight: bold; color: rgb(0, 0, 255);')
        self.mainLayout.addWidget(self.patient_label, 0, 0)

        # Time label
        self.time_label = QLabel(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.time_label.setStyleSheet('color: rgb(150, 150, 150);')
        self.mainLayout.addWidget(self.time_label, 0, 1)

        # Icon (if pathologies detected)
        self.iconQLabel = QLabel()
        if pathologies:
            self.iconQLabel.setPixmap(QIcon("images/warning_icon.png").pixmap(16, 16))
        self.mainLayout.addWidget(self.iconQLabel, 0, 2)

        self.setLayout(self.mainLayout)
        self.setStyleSheet('''
            QWidget {
                border: 1px solid rgb(200, 200, 200);
                border-radius: 5px;
                margin: 5px;
                padding: 5px;
                background-color: rgb(245, 245, 245);
            }
        ''')


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BrainScan Alert")
        self.setGeometry(100, 100, 400, 500)

        self.list_widget = QListWidget()
        self.results_count = QLabel()
        self.update_results_count()
        layout = QVBoxLayout()
        layout.addWidget(self.results_count)
        layout.addWidget(self.list_widget)

        self.setLayout(layout)

        self.result_notifier = ResultNotifier()
        self.result_notifier.new_result_signal.connect(self.handle_json_data)

        self.tray_icon = QSystemTrayIcon(QIcon("images/small_brainscan_icon.jpg"), self)
        self.tray_icon.setVisible(True)

        self.config = configparser.ConfigParser()
        self.config.read('config.ini')

        self.condition_probabilities = self.get_condition_probabilities()

        self.list_widget.itemDoubleClicked.connect(self.show_result_details)
        self.list_widget.itemChanged.connect(self.update_results_count)

    def get_condition_probabilities(self):
        return {key: float(value) for key, value in self.config['CONDITIONS_PROBABILITIES'].items()}

    def handle_json_data(self, data: dict):
        patient = data.get("StudyDescription", "Unknown")
        results = data.get("AnalysisResults")
        if results is None:
            print("AnalysisResults are missing in the json file.")
            return

        translations = data.get("translation")
        if translations is None:
            print("translations are missing in the json file.")
            return

        pathologies: list[tuple[str, float]] = []
        for pathology, probability in results.items():
            min_probability = self.condition_probabilities.get(pathology)
            translation = translations.get(pathology, pathology)
            if min_probability is None or probability >= min_probability:
                pathologies.append((translation, probability))

        if pathologies:
            time = data.get("created")
            if time is not None:
                time = datetime.fromisoformat(time)
            self.add_result(patient, pathologies, time)
            self.update_results_count()

    def add_result(self, patient, pathologies, time):
        item_widget = PatientWidget(patient, pathologies, time)
        item = QListWidgetItem(self.list_widget)
        item.setSizeHint(item_widget.sizeHint())
        item.setData(Qt.ItemDataRole.UserRole, (patient, pathologies))
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, item_widget)

        self.tray_icon.showMessage(
            "New Patient Result",
            f"Patient: {patient} has new results.",
            QSystemTrayIcon.MessageIcon.Information,
            10000
        )

    def update_results_count(self):
        self.results_count.setText(f"Results: {self.list_widget.count()}")

    def show_result_details(self, item):
        patient, pathologies = item.data(Qt.ItemDataRole.UserRole)
        dialog = ResultDialog(patient, pathologies, self)
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

    window = MainWindow()
    window.show()

    listener_thread = threading.Thread(target=listen_for_results, args=(window.result_notifier,))
    listener_thread.daemon = True
    listener_thread.start()

    send_data()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
