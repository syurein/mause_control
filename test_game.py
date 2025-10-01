import pygame
import sys
import random
import requests # requestsライブラリをインポート

# 1. ゲームの初期化
pygame.init()

# 画面サイズ
screen_width = 800
screen_height = 600
screen = pygame.display.set_mode((screen_width, screen_height))
pygame.display.set_caption("シューティングゲーム")

# 色の定義 (RGB)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
BLUE = (0, 0, 255) # 敵の色
GREEN = (0, 255, 0) # 敵の移動方向を示す色（デバッグ用、最終的には削除・コメントアウト可）

# マウスカーソルを非表示にする
pygame.mouse.set_visible(False)

# --- スコア関連 ---
score = 0
font = pygame.font.Font(None, 50)  # フォントのサイズを設定

# --- 敵関連 ---
enemies = []
enemy_size = 50
enemy_speed = 1 # 敵の移動速度

class Enemy:
    def __init__(self):
        self.rect = pygame.Rect(random.randint(0, screen_width - enemy_size),
                                random.randint(0, screen_height - enemy_size),
                                enemy_size, enemy_size)
        # 敵の移動方向 (x, y) -1, 0, 1 のいずれか
        self.direction_x = random.choice([-1, 1])
        self.direction_y = random.choice([-1, 1])

    def move(self):
        self.rect.x += self.direction_x * enemy_speed
        self.rect.y += self.direction_y * enemy_speed

        # 画面端での跳ね返り
        if self.rect.left < 0 or self.rect.right > screen_width:
            self.direction_x *= -1
        if self.rect.top < 0 or self.rect.bottom > screen_height:
            self.direction_y *= -1

    def draw(self, surface):
        pygame.draw.rect(surface, BLUE, self.rect)

def add_enemy():
    enemies.append(Enemy())

# 最初に1体敵を追加
add_enemy()

# 射撃エフェクトの状態を管理する変数
shooting = False
shooting_timer = 0
shooting_duration = 5

# ゲームループの制御
clock = pygame.time.Clock()
running = True

# 2. ゲームループ
while running:
    # 3. イベント処理
    for event in pygame.event.get():
        # ウィンドウの閉じるボタンが押されたら終了
        if event.type == pygame.QUIT:
            running = False

        # マウスボタンが押されたら
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # 1は左クリック
                # 射撃エフェクトを開始
                shooting = True
                shooting_timer = shooting_duration

                mouse_pos = event.pos
                for enemy in enemies[:]:
                    if enemy.rect.collidepoint(mouse_pos):
                        enemies.remove(enemy) # 敵を削除
                        score += 1             # スコアを加算
                        enemy_speed+=1
                        add_enemy()            # 新しい敵を追加

                        # --- HTTPリクエスト送信 ---
                        try:
                            requests.get("http://localhost:5000/send/2")
                            requests.get("http://localhost:5000/send/1")
                            print("Request sent to localhost/send/2 and localhost/send/1")
                        except requests.exceptions.ConnectionError:
                            print("Error: Could not connect to localhost. Is the server running?")
                        except Exception as e:
                            print(f"An unexpected error occurred: {e}")
                        # --- HTTPリクエスト送信 END ---

                        break # 1回のクリックで1体のみ倒す

    # 4. ゲームロジック
    # マウスカーソルの現在位置を取得
    mouse_x, mouse_y = pygame.mouse.get_pos()

    # 敵の移動
    for enemy in enemies:
        enemy.move()

    # 射撃エフェクトのタイマーを減らす
    if shooting_timer > 0:
        shooting_timer -= 1
    else:
        shooting = False

    # 5. 描画処理
    # 背景を黒で塗りつぶす
    screen.fill(BLACK)

    # 敵の描画
    for enemy in enemies:
        enemy.draw(screen)

    # レティクル（照準）の描画
    pygame.draw.line(screen, WHITE, (mouse_x, mouse_y - 15), (mouse_x, mouse_y + 15), 2)
    pygame.draw.line(screen, WHITE, (mouse_x - 15, mouse_y), (mouse_x + 15, mouse_y), 2)
    pygame.draw.circle(screen, WHITE, (mouse_x, mouse_y), 3)

    # 射撃エフェクトの描画
    if shooting:
        pygame.draw.circle(screen, RED, (mouse_x, mouse_y), 20, 3)

    # スコアの描画
    score_text = font.render(f"Score: {score}", True, WHITE)
    screen.blit(score_text, (10, 10)) # (10, 10)の位置に表示

    # 画面を更新
    pygame.display.flip()

    # フレームレートを60に設定
    clock.tick(60)

# 6. 終了処理
pygame.quit()
sys.exit()