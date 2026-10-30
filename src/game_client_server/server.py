import socket
import threading
import json


CLIENT_COLORS = [
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255)
]

POSITIONAL_ACTIONS = ["W", "A", "S", "D"]
ACTION_CHANGES = {
    "W": (0, -5),
    "A": (-5, 0),
    "S": (0, 5),
    "D": (5, 0)
}


class Server:
    def __init__(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("127.0.0.1", 5100))
        self.server.listen(1)

        self.is_game_started = False
        self.game_started_event = threading.Event()

        self.client_sockets = {}
        self.client_positions = {}
        self.client_connection_statuses = {}

        self.main_thread()

    def add_client(self, client_socket):
        if self.is_game_started:
            return None
        
        client_id = len(self.client_sockets)
        self.client_sockets[client_id] = client_socket
        self.client_positions[client_id] = (client_id * 400 + (50 if client_id == 0 else 0 if client_id == 1 else -50),
                                             500 if client_id % 2 == 0 else 100)
        self.client_connection_statuses[client_id] = True

        if len(self.client_sockets) == 3:
            self.is_game_started = True
            self.game_started_event.set()

        return client_id

    def remove_client(self, id):
        if self.is_game_started:
            self.client_connection_statuses[id] = False
        else:
            del self.client_sockets[id]
            del self.client_positions[id]
            del self.client_connection_statuses[id]

    def update_active_clients(self):
        for id, status in self.client_connection_statuses.items():
            if status:
                client_socket = self.client_sockets[id]
                client_socket.sendall(json.dumps({"players": [{"x": int(pos[0]), "y": int(pos[1]), "color": CLIENT_COLORS[i]}
                                                    for i, pos in self.client_positions.items()]}).encode())

    def client_thread(self, client_id):
        self.update_active_clients()
        self.game_started_event.wait()
        while True:
            data = self.client_sockets[client_id].recv(1024)
            decoded = data.decode()
            json_data = json.loads(decoded)
            action = json_data["action"]
            if action in POSITIONAL_ACTIONS:
                dx, dy = ACTION_CHANGES[action]
                x, y = self.client_positions[client_id]
                x, y = x + dx, y + dy
                self.client_positions[client_id] = (x, y)
                self.update_active_clients()
            

    def main_thread(self):
        while True:
            client_socket, _ = self.server.accept()
            new_client_id = self.add_client(client_socket)
            if new_client_id is not None:
                threading.Thread(target=self.client_thread, args=(new_client_id,), daemon=True).start()


if __name__ == "__main__":
    server = Server()
    