import socket, threading, json, pygame, sys, time
from collections import deque


KEY_TO_CHAR = {
    pygame.K_a: "A",
    pygame.K_d: "D",
    pygame.K_w: "W",
    pygame.K_s: "S",
    pygame.K_c: "C"
}


class Client:
    def __init__(self, key=None):
        pygame.init()
        self.key = key
        self.screen = pygame.display.set_mode((800, 600))
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.connect(("127.0.0.1", 5100))
        self.q = deque(maxlen=1_000)
        self.receiver_q = deque(maxlen=1_000)
        self.state_lock = threading.Lock()
        self.running = True
        threading.Thread(target=self.sender_thread, args=(self.key,), daemon=True).start()
        threading.Thread(target=self.receiver_thread, daemon=True).start()
        self.main_thread()

    def main_thread(self):
        clock = pygame.time.Clock()
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    break

                if event.type == pygame.KEYDOWN:
                    char = KEY_TO_CHAR.get(event.key)
                    if char is not None:
                        with self.state_lock:
                            self.q.append(json.dumps({"action": char}))

            with self.state_lock:
                if len(self.receiver_q) > 0:
                    players, resources = self.receiver_q[-1]
                    self.receiver_q.clear()
                else:
                    players, resources = None, None

            if players is not None:
                self.render(players, resources)

            clock.tick(60)

    def render(self, players, resources):
        self.screen.fill((0, 0, 0))

        for player in players:
            radius = 10
            alpha = 255 if player["is_active"] else 128
            color = (*player["color"], alpha)
            temp_surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(temp_surface, color, (radius, radius), radius, 10)
            self.screen.blit(temp_surface, (player["x"] - radius, player["y"] - radius))

        for resource in resources:
            x, y = resource["x"], resource["y"]
            pygame.draw.circle(self.screen, (255, 215, 0), (x, y), 3)

        pygame.display.update()

    def receiver_thread(self):
        buffer = b""
        while self.running:
            data = self.server_socket.recv(1024)
            if not data:
                self.running = False
                break
            buffer += data
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                json_data = json.loads(line.decode())
                if json_data["type"] == "key":
                    print(f"Key for current session: {json_data['content']}")
                elif json_data["type"] == "game_data":
                    with self.state_lock:
                        self.receiver_q.append((json_data["content"]["players"], json_data["content"]["resources"]))
                elif json_data["type"] == "error_status":
                    print(f"Connection failed with message: {json_data['content']}")
                    self.running = False
                    return

    def sender_thread(self, key=None):
        if key is not None:
            self.server_socket.sendall((json.dumps({"action": "RECONNECT", "content": key}) + "\n").encode())

        while self.running:
            if len(self.q) > 0:
                with self.state_lock:
                    action = self.q.popleft()
                self.server_socket.sendall((action + "\n").encode())

            else:
                time.sleep(0.005)


if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else None
    client = Client(key)