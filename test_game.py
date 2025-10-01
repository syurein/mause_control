import pygame
import sys
import random

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

# マウスカーソルを非表示にする
pygame.mouse.set_visible(False)

# --- スコア関連 ---
score = 0
font = pygame.font.Font(None, 50)  # フォントのサイズを設定

# --- 敵関連 ---
enemies = []
enemy_size = 50

def add_enemy():
    """新しい敵をランダムな位置に追加する関数"""
    x = random.randint(0, screen_width - enemy_size)
    y = random.randint(0, screen_height - enemy_size)
    enemy_rect = pygame.Rect(x, y, enemy_size, enemy_size)
    enemies.append(enemy_rect)

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

                # --- 当たり判定 ---
                # topleft, top-right, bottom-left, bottom-right
                mouse_pos = event.pos
                # enemiesリストのコピーをループして、安全に要素を削除できるようにする
                for enemy_rect in enemies[:]:
                    if enemy_rect.collidepoint(mouse_pos):
                        enemies.remove(enemy_rect) # 敵を削除
                        score += 1                 # スコアを加算
                        add_enemy()                # 新しい敵を追加
                        break # 1回のクリックで1体のみ倒す

    # 4. ゲームロジック
    # マウスカーソルの現在位置を取得
    mouse_x, mouse_y = pygame.mouse.get_pos()

    # 射撃エフェクトのタイマーを減らす
    if shooting_timer > 0:
        shooting_timer -= 1
    else:
        shooting = False

    # 5. 描画処理
    # 背景を黒で塗りつぶす
    screen.fill(BLACK)

    # 敵の描画
    for enemy_rect in enemies:
        pygame.draw.rect(screen, BLUE, enemy_rect)

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