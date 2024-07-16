import configparser
import sys
import socket
import json
import threading
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget, QListWidget, QListWidgetItem, \
    QSystemTrayIcon, QDialog, QLabel, QDialogButtonBox
from PySide6.QtCore import Signal, QObject, Qt
from PySide6.QtGui import QIcon


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


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BrainScan Alert")
        self.setGeometry(100, 100, 400, 600)

        layout = QVBoxLayout()
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        self.setLayout(layout)

        self.result_notifier = ResultNotifier()
        self.result_notifier.new_result_signal.connect(self.handle_json_data)

        self.tray_icon = QSystemTrayIcon(QIcon("icon.png"), self)
        self.tray_icon.setVisible(True)

        self.config = configparser.ConfigParser()
        self.config.read('config.ini')

        self.condition_probabilities = self.get_condition_probabilities()

        self.list_widget.itemDoubleClicked.connect(self.show_result_details)

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
            self.add_result(patient, pathologies)

    def add_result(self, patient, pathologies):
        item = QListWidgetItem(f"Patient: {patient}")
        item.setData(Qt.ItemDataRole.UserRole, (patient, pathologies))
        self.list_widget.addItem(item)

        self.tray_icon.showMessage(
            "New Patient Result",
            f"Patient: {patient} has new results.",
            QSystemTrayIcon.MessageIcon.Information,
            5000
        )

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


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    listener_thread = threading.Thread(target=listen_for_results, args=(window.result_notifier,))
    listener_thread.daemon = True
    listener_thread.start()

    sys.exit(app.exec())
