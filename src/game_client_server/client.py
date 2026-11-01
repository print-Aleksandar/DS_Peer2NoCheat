import socket, threading, json, pygame, sys


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
        threading.Thread(target=self.sender_thread, args=(self.key,), daemon=True).start()
        self.reciver_thread()

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

    def reciver_thread(self):
        buffer = b""
        while True:
            data = self.server_socket.recv(1024)
            if not data: break
            buffer += data
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                json_data = json.loads(line.decode())
                if json_data["type"] == "key":
                    print(f"Key for current session: {json_data["content"]}")
                elif json_data["type"] == "game_data":
                    self.render(json_data["content"]["players"], json_data["content"]["resources"])
                elif json_data["type"] == "error_status":
                    print(f"Connection failed with message: {json_data["content"]}")
                    break

    def sender_thread(self, key=None):
        if key is not None:
            self.server_socket.sendall(json.dumps(({"action": "RECONNECT", "content": key}), + "\n").encode())
        
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    break

                if event.type == pygame.KEYDOWN:
                    char = KEY_TO_CHAR.get(event.key)
                    if char is not None:
                        self.server_socket.sendall((json.dumps({"action": char}) + "\n").encode())


if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else None
    client = Client(key)
