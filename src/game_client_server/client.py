import socket, threading, json, pygame


KEY_TO_CHAR = {
    pygame.K_a: "A",
    pygame.K_d: "D",
    pygame.K_w: "W",
    pygame.K_s: "S",
    pygame.K_c: "C"
}


class Client:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((800, 600))
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.connect(("127.0.0.1", 5100))
        threading.Thread(target=self.reciver_thread, daemon=True).start()
        self.sender_thread()

    def render(self, players):
        self.screen.fill((0, 0, 0))
        for player in players:
            pygame.draw.circle(self.screen, player["color"], (player["x"], player["y"]), 10, 10)
        pygame.display.update()

    def reciver_thread(self):
        while True:
            data = self.server_socket.recv(1024)
            decoded = data.decode()
            json_data = json.loads(decoded)
            self.render(json_data["players"])

    def sender_thread(self):
        while True:
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN:
                    char = KEY_TO_CHAR[event.key]
                    self.server_socket.sendall(json.dumps({"action": char}).encode())


if __name__ == "__main__":
    client = Client()
