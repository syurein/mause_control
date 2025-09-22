import pyautogui
import random
import time

# 画面の解像度を取得
screen_width, screen_height = pyautogui.size()

print(f"画面サイズ: 幅={screen_width} 高さ={screen_height}")
print("5秒後にランダムなマウス操作を開始します。プログラムを停止するには、Ctrl+Cを押してください。")

time.sleep(5)

try:
    # 10回繰り返す
    for i in range(10):
        # ランダムなx座標とy座標を生成
        random_x = random.randint(0, screen_width - 1)
        random_y = random.randint(0, screen_height - 1)

        # ランダムな時間をかけて、ランダムな座標へマウスを移動
        pyautogui.moveTo(random_x, random_y, duration=random.uniform(0.5, 2.0))

        print(f"{i + 1}回目のクリック: ({random_x}, {random_y})")

        # クリック
        pyautogui.click()

        # 次の動作までの待機時間（1秒〜3秒）
        time.sleep(random.uniform(1.0, 3.0))

    print("\n処理が完了しました。")

except KeyboardInterrupt:
    print("\nプログラムが手動で停止されました。")