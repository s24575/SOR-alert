import socket
import json
import threading
import tkinter as tk
from tkinter import messagebox
import configparser
from typing import Any, Dict, List, Tuple


def show_alert_window(pathologies: List[Tuple[str, float]]):
    message = "The following pathologies have been detected:\n"
    message += "\n".join([f"{pathology}: {int(probability * 100)}%"
                          for pathology, probability in pathologies])
    messagebox.showwarning("Alert", message)


def create_window():
    window = tk.Tk()
    window.title("SOR Early Alert")
    window.minsize(width=400, height=40)
    window.resizable(width=False, height=False)

    label = tk.Label(window, text="Listening for incoming data")
    label.pack(padx=10, pady=10)

    window.mainloop()


def handle_json_data(data: Any, condition_probabilities: Dict[str, float]):
    try:
        json_data = json.loads(data)
        results = json_data.get("AnalysisResults")
        if results is None:
            print("AnalysisResults are missing in the json file.")
            return
        
        translations = json_data.get("translation")
        if translations is None:
            print("translations are missing in the json file.")
            return

        pathologies: List[str, float] = []
        for pathology, probability in results.items():
            min_probability = condition_probabilities.get(pathology)
            translation = translations.get(pathology, pathology)
            if min_probability is None or probability >= min_probability:
                pathologies.append((translation, probability))

        if pathologies:
            show_alert_window(pathologies)

    except json.JSONDecodeError as e:
        print(f"Error decoding JSON data: {e}")


# Flag to signal the server thread to exit
exit_flag = threading.Event()


def start_server(host: str, port: int, condition_probabilities: Dict[str, float]):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.bind((host, port))
        server_socket.listen()

        print(f"Server listening on {host}:{port}")

        while not exit_flag.is_set():
            try:
                server_socket.settimeout(1)
                client_socket, client_address = server_socket.accept()
                data = client_socket.recv(4096)
                handle_json_data(data, condition_probabilities)
                client_socket.close()
            except socket.timeout:
                pass
            except socket.error as e:
                print(f"Socket binding error: {e}")


def main():
    config = configparser.ConfigParser()
    config.read('config.ini')

    host = config['SERVER']['HOST']
    port = int(config['SERVER']['PORT'])

    condition_probabilities = {key: float(value) for key, value in config['CONDITIONS'].items()}

    # Start the server in a separate thread
    server_thread = threading.Thread(target=start_server, args=(host, port, condition_probabilities))
    server_thread.start()

    # Run the Tkinter window in the main thread
    create_window()

    # Set the exit flag to signal the server thread to terminate
    exit_flag.set()

    # Wait for the server thread to finish
    server_thread.join()


if __name__ == "__main__":
    main()
