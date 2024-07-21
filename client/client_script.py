import socket


def send_data(result_path: str):
    # Set up the socket
    host = '127.0.0.1'
    port = 12345

    # Create a socket object
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Connect to the server
    client_socket.connect((host, port))

    # Read the example json file
    with open(result_path, "r") as f:
        data = f.read()

    # Send data to the server
    client_socket.send(data.encode('utf-8'))

    # Close the connection
    client_socket.close()


if __name__ == "__main__":
    send_data("client/example-results-1.json")
