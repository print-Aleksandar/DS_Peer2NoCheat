import socket, threading, json, random, time, math
from collections import deque


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

        self.state_lock = threading.Lock()

        self.is_game_started = False

        self.client_sockets = {}
        self.client_positions = {}
        self.client_connection_statuses = {}
        self.client_keys = {}

        self.resources_positions = []
        self.client_scores = {}

        self.q = deque(maxlen=1_000)
        self.receiver_q = deque(maxlen=1_000)
        threading.Thread(target=self.process_received_q_thread, daemon=True).start()
        threading.Thread(target=self.q_sender_thread, daemon=True).start()

        self.main_thread()

    def add_client(self, client_socket):
        with self.state_lock:
            is_game_started = self.is_game_started

        if not is_game_started:
            with self.state_lock:
                for i in range(3):
                    if (i not in self.client_sockets.keys() or
                        not self.client_connection_statuses[i]):
                        client_id = i
                        break
                else:
                    return None
                        
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
                    "content": key
                    }) + "\n"
                ).encode()
            )

            with self.state_lock:
                to_start = len(self.client_sockets) == 3 and not self.is_game_started
                if to_start:
                    self.is_game_started = True

            if to_start:
                threading.Thread(target=self.spawn_resources_thread, daemon=True).start()

            return client_id

        else:
            with self.state_lock:
                reconnect_allowed = self.is_game_started and \
                    len([v for v in self.client_connection_statuses.values() if v]) < 3

            if reconnect_allowed:
                client_socket.settimeout(2.0)
                try:
                    buffer = b""
                    while b"\n" not in buffer:
                        data = client_socket.recv(1024)

                        if not data:
                            return None

                        buffer += data

                    line, buffer = buffer.split(b"\n", 1)
                    json_data = json.loads(line)
                    client_socket.settimeout(None)

                except socket.timeout:
                    return None

                with self.state_lock:
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
        with self.state_lock:
            if self.is_game_started:
                self.client_connection_statuses[id] = False
            else:
                del self.client_sockets[id]
                del self.client_positions[id]
                del self.client_connection_statuses[id]

        self.put_game_state_in_q()

    def put_game_state_in_q(self):
        with self.state_lock:
            game_state = json.dumps({
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
            })

            self.q.append(game_state)

    def q_sender_thread(self):
        while True:
            socket_with_game_state = dict()
            with self.state_lock:
                if len(self.q) > 0:
                    game_state = self.q.popleft()
                    for client_id, status in self.client_connection_statuses.items():
                        if status:
                            client_socket = self.client_sockets[client_id]
                            socket_with_game_state[client_socket] = game_state

            for client_socket, game_state in socket_with_game_state.items():
                client_socket.sendall((game_state + "\n").encode())

            if len(socket_with_game_state) == 0:
                time.sleep(0.005)

    def client_thread(self, client_id):
        self.put_game_state_in_q()
        buffer = b""
        while True:
            with self.state_lock:
                client_socket = self.client_sockets[client_id]
            data = client_socket.recv(1024)
            if not data:
                with self.state_lock:
                    is_started = self.is_game_started
                    if is_started:
                        self.client_connection_statuses[client_id] = False
                if is_started:
                    self.put_game_state_in_q()
                else:
                    self.remove_client(client_id)
                break

            buffer += data
            while b"\n" in buffer:
                with self.state_lock:
                    is_game_started = self.is_game_started
                if is_game_started:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        json_data = json.loads(line.decode())
                    except json.JSONDecodeError as _:
                        continue
                    action = json_data["action"]

                    with self.state_lock:
                        self.receiver_q.append((client_id, action))

                else:
                    buffer = b""

    def process_received_q_thread(self):
        while True:
            needs_update = False
            to_sleep = False
            with self.state_lock:
                if len(self.receiver_q) > 0:
                    client_id, action = self.receiver_q.popleft()

                    if action in POSITIONAL_ACTIONS:
                        dx, dy = ACTION_CHANGES[action]
                        x, y = self.client_positions[client_id]
                        x, y = x + dx, y + dy
                        self.client_positions[client_id] = (x, y)
                        needs_update = True
                    else:
                        if action == "C":
                            needs_update = self.take_resource_for_client_if_valid(client_id)

                else:
                    to_sleep = True

            if to_sleep:
                time.sleep(0.005)

            if needs_update:
                self.put_game_state_in_q()

    def spawn_resources_thread(self):
        while True:
            time.sleep(random.randint(3, 10))
            for _ in range(800 * 600):
                position = (random.randint(0, 799), random.randint(0, 599))
                with self.state_lock:
                    if position not in self.resources_positions:
                        self.resources_positions.append(position)
                        break
            else:
                break

        self.put_game_state_in_q()

    def take_resource_for_client_if_valid(self, client_id):
        client_position = self.client_positions[client_id]
        within_range = [r for r in self.resources_positions
                        if math.sqrt((r[0] - client_position[0])**2 + (r[1] - client_position[1])**2) < 20]
        
        if len(within_range) == 0:
            return False

        within_range = sorted(within_range, key=lambda x: math.sqrt((x[0] - client_position[0])**2 + (x[1] - client_position[1])**2))
        first = within_range[0]
        self.resources_positions.pop(self.resources_positions.index(first))

        if self.client_scores.get(client_id) is None:
            self.client_scores[client_id] = 1
        else:
            self.client_scores[client_id] += 1

        print(self.client_scores)
        return True

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
    