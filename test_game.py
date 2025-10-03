import pygame
import sys
import random
import requests
import math # 爆弾の当たり判定で使用

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
BLUE = (0, 0, 255)
GREEN = (0, 255, 0)
YELLOW = (255, 255, 0) # 【新機能】爆発エフェクト用
MAGENTA = (255, 0, 255) # 【新機能】ビーム用

# マウスカーソルを非表示にする
pygame.mouse.set_visible(False)

# --- フォント関連 ---
score_font = pygame.font.Font(None, 50)
ammo_font = pygame.font.Font(None, 50)
reload_font = pygame.font.Font(None, 80)

# --- スコア関連 ---
score = 0

# --- 弾薬（Ammo）とリロード関連 ---
max_ammo = 10
ammo = max_ammo
reloading = False
reload_duration = 150
reload_timer = 0

# --- 敵関連 ---
enemies = []
enemy_size = 50
enemy_speed = 1
enemy_spawn_interval = 20000
last_enemy_spawn_time = pygame.time.get_ticks()

class Enemy:
    def __init__(self):
        self.rect = pygame.Rect(random.randint(0, screen_width - enemy_size),
                                  random.randint(0, screen_height - enemy_size),
                                  enemy_size, enemy_size)
        self.direction_x = random.choice([-1, 1])
        self.direction_y = random.choice([-1, 1])

    def move(self):
        self.rect.x += self.direction_x * enemy_speed
        self.rect.y += self.direction_y * enemy_speed
        if self.rect.left < 0 or self.rect.right > screen_width:
            self.direction_x *= -1
        if self.rect.top < 0 or self.rect.bottom > screen_height:
            self.direction_y *= -1

    def draw(self, surface):
        pygame.draw.rect(surface, BLUE, self.rect)

def add_enemy():
    enemies.append(Enemy())

for _ in range(5):
    add_enemy()

# 射撃エフェクトの状態を管理する変数
shooting = False
shooting_timer = 0
shooting_duration = 5

# --- 【新機能】連続クリック判定関連 ---
left_click_count = 0
last_left_click_time = 0
right_click_count = 0
last_right_click_time = 0
click_interval_threshold = 300 # 連続クリックとみなす時間間隔 (ミリ秒)

# --- 【新機能】極太ビーム関連 ---
beam_active = False
beam_timer = 0
beam_duration = 25 # ビームの表示時間 (フレーム)
beam_width = 80

# --- 【新機能】爆弾関連 ---
bombs = []
BOMB_COST = 5
BEAM_COST = 5

class Bomb:
    def __init__(self, pos):
        self.pos = pos
        self.timer = 180 # 爆発までの時間 (フレーム, 60fpsで3秒)
        self.explosion_radius = 150
        self.explosion_timer = 20 # 爆発エフェクトの表示時間
        self.state = 'ticking' # 'ticking', 'exploding', 'done'
    
    def update(self):
        global score, enemy_speed
        if self.state == 'ticking':
            self.timer -= 1
            if self.timer <= 0:
                self.state = 'exploding'
                # 爆発範囲内の敵を削除
                for enemy in enemies[:]:
                    distance = math.sqrt((enemy.rect.centerx - self.pos[0])**2 + (enemy.rect.centery - self.pos[1])**2)
                    if distance <= self.explosion_radius:
                        enemies.remove(enemy)
                        score += 1
                        enemy_speed += 0.2 # 敵の速度を少し上げる
                        add_enemy()

        elif self.state == 'exploding':
            self.explosion_timer -= 1
            if self.explosion_timer <= 0:
                self.state = 'done'

    def draw(self, surface):
        if self.state == 'ticking':
            # 爆弾本体と点滅するインジケータを描画
            pygame.draw.circle(surface, RED, self.pos, 10)
            if (self.timer // 20) % 2 == 0: # 点滅
                 pygame.draw.circle(surface, YELLOW, self.pos, 5)
        elif self.state == 'exploding':
            # 爆発エフェクトを描画
            alpha = max(0, 255 * (self.explosion_timer / 20))
            explosion_surf = pygame.Surface((self.explosion_radius*2, self.explosion_radius*2), pygame.SRCALPHA)
            pygame.draw.circle(explosion_surf, (255, 200, 0, alpha), (self.explosion_radius, self.explosion_radius), self.explosion_radius)
            surface.blit(explosion_surf, (self.pos[0] - self.explosion_radius, self.pos[1] - self.explosion_radius))

# ゲームループの制御
clock = pygame.time.Clock()
running = True

# 2. ゲームループ
while running:
    current_time_ticks = pygame.time.get_ticks()
    mouse_pos = pygame.mouse.get_pos()
    
    # 3. イベント処理
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if event.type == pygame.MOUSEBUTTONDOWN:
            # --- 【変更点】左クリックの処理 ---
            if event.button == 1 and not reloading:
                # 連続クリック判定
                if current_time_ticks - last_left_click_time < click_interval_threshold:
                    left_click_count += 1
                else:
                    left_click_count = 1
                last_left_click_time = current_time_ticks
                
                # 【新機能】4回連続クリックでビーム発射
                if left_click_count >= 4 and ammo >= BEAM_COST:
                    ammo -= BEAM_COST
                    beam_active = True
                    beam_timer = beam_duration
                    left_click_count = 0 # カウントリセット
                    
                    # ビームの当たり判定
                    beam_rect = pygame.Rect(mouse_pos[0] - beam_width // 2, 0, beam_width, screen_height)
                    for enemy in enemies[:]:
                        if beam_rect.colliderect(enemy.rect):
                            enemies.remove(enemy)
                            score += 1
                            enemy_speed += 0.5
                            add_enemy()

                # 通常の射撃
                elif ammo > 0:
                    shooting = True
                    shooting_timer = shooting_duration
                    ammo -= 1
                    for enemy in enemies[:]:
                        if enemy.rect.collidepoint(mouse_pos):
                            enemies.remove(enemy)
                            score += 1
                            enemy_speed += 0.2
                            add_enemy()
                            try:
                                requests.get("http://localhost:5000/send/2")
                                print("Request sent to localhost/send/2")
                            except requests.exceptions.ConnectionError:
                                print("Error: Could not connect to localhost.")
                            except Exception as e:
                                print(f"An unexpected error occurred: {e}")
                            break

            # --- 【変更点】右クリックの処理 ---
            elif event.button == 3: # 3は右クリック
                if not reloading:
                    # 連続クリック判定
                    if current_time_ticks - last_right_click_time < click_interval_threshold:
                        right_click_count += 1
                    else:
                        right_click_count = 1
                    last_right_click_time = current_time_ticks

                    # 【新機能】4回連続クリックで爆弾設置
                    if right_click_count >= 4 and ammo >= BOMB_COST:
                        ammo -= BOMB_COST
                        bombs.append(Bomb(mouse_pos))
                        right_click_count = 0 # カウントリセット
                    
                    # 通常のリロード
                    elif ammo < max_ammo:
                        reloading = True
                        reload_timer = reload_duration
                        right_click_count = 0 # リロードしたらカウントリセット

    # 4. ゲームロジック
    # 敵の移動
    for enemy in enemies:
        enemy.move()
    
    # 時間経過で敵を自動追加
    if current_time_ticks - last_enemy_spawn_time > enemy_spawn_interval:
        add_enemy()
        last_enemy_spawn_time = current_time_ticks

    # 射撃エフェクトのタイマー
    if shooting_timer > 0:
        shooting_timer -= 1
    else:
        shooting = False

    # 【新機能】ビームのタイマー
    if beam_timer > 0:
        beam_timer -= 1
    else:
        beam_active = False

    # 【新機能】爆弾の更新
    for bomb in bombs[:]:
        bomb.update()
        if bomb.state == 'done':
            bombs.remove(bomb)

    # リロード処理
    if reloading:
        reload_timer -= 1
        if reload_timer <= 0:
            reloading = False
            ammo = max_ammo

    # 5. 描画処理
    screen.fill(BLACK)

    for enemy in enemies:
        enemy.draw(screen)

    # 【新機能】爆弾の描画
    for bomb in bombs:
        bomb.draw(screen)

    # 【新機能】ビームの描画
    if beam_active:
        # ビームの中心をマウスのX座標に合わせる
        beam_rect = pygame.Rect(mouse_pos[0] - beam_width // 2, 0, beam_width, screen_height)
        pygame.draw.rect(screen, MAGENTA, beam_rect)

    # レティクルの描画
    pygame.draw.line(screen, WHITE, (mouse_pos[0], mouse_pos[1] - 15), (mouse_pos[0], mouse_pos[1] + 15), 2)
    pygame.draw.line(screen, WHITE, (mouse_pos[0] - 15, mouse_pos[1]), (mouse_pos[0] + 15, mouse_pos[1]), 2)
    pygame.draw.circle(screen, WHITE, mouse_pos, 3)

    # 射撃エフェクトの描画
    if shooting:
        pygame.draw.circle(screen, RED, mouse_pos, 20, 3)

    # スコアの描画
    score_text = score_font.render(f"Score: {score}", True, WHITE)
    screen.blit(score_text, (10, 10))

    # 弾薬数の描画
    ammo_text_color = RED if ammo == 0 else WHITE
    ammo_text = ammo_font.render(f"Ammo: {ammo}/{max_ammo}", True, ammo_text_color)
    screen.blit(ammo_text, (screen_width - 220, 10))

    # リロード中の描画
    if reloading:
        reload_text_surface = reload_font.render("Reloading...", True, RED)
        text_rect = reload_text_surface.get_rect(center=(screen_width/2, screen_height/2))
        screen.blit(reload_text_surface, text_rect)

    pygame.display.flip()
    clock.tick(60)

# 6. 終了処理
pygame.quit()
sys.exit()