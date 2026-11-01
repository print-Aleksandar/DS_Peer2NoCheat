import socket, threading, json, random, time, math


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
        self.server.listen(3)

        self.is_game_started = False

        self.client_sockets = {}
        self.client_positions = {}
        self.client_connection_statuses = {}
        self.client_keys = {}

        self.resources_positions = []
        self.client_scores = {}

        self.main_thread()

    def add_client(self, client_socket):
        if not self.is_game_started:
            for i in range(3):
                        if (i not in self.client_sockets.keys() or
                            not self.client_connection_statuses[i]):
                            client_id = i
                            break

            self.client_sockets[client_id] = client_socket
            self.client_positions[client_id] = (client_id * 400 + (50 if client_id == 0 else 0 if client_id == 1 else -50),
                                                500 if client_id % 2 == 0 else 100)
            self.client_connection_statuses[client_id] = True

            while True:
                key = f"P{random.randint(0, 100):03}"
                if key not in self.client_keys.values():
                    self.client_keys[client_id] = key
                    break

            client_socket.sendall((
                json.dumps({
                    "type": "key",
                    "content": self.client_keys[client_id]
                    }
                ) + "\n"
                ).encode()
            )

            if len(self.client_sockets) == 3:
                self.is_game_started = True
                threading.Thread(target=self.spawn_resources_thread, daemon=True).start()

            return client_id

        elif self.is_game_started and len([v for _, v in self.client_connection_statuses.items() if v ]) < 3:
            client_socket.settimeout(2.0)
            try:
                data = client_socket.recv(1024)
                client_socket.settimeout(None)
            except socket.timeout:
                return None
            
            decoded = data.decode()
            json_data = json.loads(decoded)

            action = json_data["action"]
            if action != "RECONNECT":
                return None

            key = json_data["content"]
            if key not in self.client_keys.values():
                return None

            client_id = next((k for k, v in self.client_keys.items() if v == key), None)
            if client_id is None:
                return None
            
            if (client_id in self.client_sockets.keys() and 
                not self.client_connection_statuses[client_id]):

                    self.client_sockets[client_id] = client_socket
                    self.client_connection_statuses[client_id] = True

                    return client_id

        return None

    def remove_client(self, id):
        if self.is_game_started:
            self.client_connection_statuses[id] = False
        else:
            del self.client_sockets[id]
            del self.client_positions[id]
            del self.client_connection_statuses[id]

            self.update_active_clients()

    def update_active_clients(self):
        for client_id, status in self.client_connection_statuses.items():
                if status:
                    client_socket = self.client_sockets[client_id]
                    client_socket.sendall((
                    json.dumps({
                        "type": "game_data",
                        "content": {
                            "players": [
                                {
                                    "x": int(pos[0]),
                                    "y": int(pos[1]),
                                    "color": CLIENT_COLORS[i],
                                    "is_active": bool(self.client_connection_statuses[i]),
                                }
                                for i, pos in self.client_positions.items()
                            ],
                            "resources": [
                                {
                                    "x": int(pos[0]),
                                    "y": int(pos[1])
                                }
                                for pos in self.resources_positions
                            ]
                        } 
                    }) + "\n").encode()
                )

    def client_thread(self, client_id):
        self.update_active_clients()
        while True:
            data = self.client_sockets[client_id].recv(1024)
            if not data:
                if self.is_game_started:
                    self.client_connection_statuses[client_id] = False
                    self.update_active_clients()
                else:
                    self.remove_client(client_id)
                break

            if self.is_game_started:
                decoded = data.decode()
                json_data = json.loads(decoded)
                action = json_data["action"]
                if action in POSITIONAL_ACTIONS:
                    dx, dy = ACTION_CHANGES[action]
                    x, y = self.client_positions[client_id]
                    x, y = x + dx, y + dy
                    self.client_positions[client_id] = (x, y)
                    self.update_active_clients()
                else:
                    if action == "C":
                        self.take_resource_for_client_if_valid(client_id)

    def spawn_resources_thread(self):
        while True:
            time.sleep(random.randint(3, 10))
            for _ in range(800 * 600):
                position = (random.randint(0, 799), random.randint(0, 599))
                if position not in self.resources_positions:
                    self.resources_positions.append(position)
                    break
            else:
                break

            self.update_active_clients()

    def take_resource_for_client_if_valid(self, client_id):
        client_position = self.client_positions[client_id]
        within_range = [r for r in self.resources_positions
                        if math.sqrt((r[0] - client_position[0])**2 + (r[1] - client_position[1])**2) < 20]
        
        if len(within_range) == 0:
            return

        within_range = sorted(within_range, key=lambda x: math.sqrt((x[0] - client_position[0])**2 + (x[1] - client_position[1])**2))
        first = within_range[0]
        self.resources_positions.pop(self.resources_positions.index(first))

        if self.client_scores.get(client_id) is None:
            self.client_scores[client_id] = 1
        else:
            self.client_scores[client_id] += 1

        print(self.client_scores)

    def main_thread(self):
        while True:
            client_socket, _ = self.server.accept()
            new_client_id = self.add_client(client_socket)
            if new_client_id is not None:
                threading.Thread(target=self.client_thread, args=(new_client_id,), daemon=True).start()
            else:
                client_socket.sendall((json.dumps({"type": "error_status", "content": "This game was already started."}) + "\n").encode())
            

if __name__ == "__main__":
    server = Server()
    