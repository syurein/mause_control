import serial
import pyautogui
import time

# --- 設定項目 ---
# Arduinoが接続されているシリアルポート名
# Windowsの場合: "COM3", "COM4" など
# Macの場合: "/dev/tty.usbmodemXXXX" や "/dev/tty.usbserial-XXXX" など
# Linuxの場合: "/dev/ttyACM0" や "/dev/ttyUSB0" など
SERIAL_PORT = 'COM12'  # ★★★★★ ご自身の環境に合わせて必ず変更してください ★★★★★
BAUD_RATE = 115200

# マウスの感度（この値を大きくすると、少しの傾きでマウスが大きく動きます）
SENSITIVITY_X = 5.0  # X軸（水平方向）。Headingの変化とカーソルの動きが逆の場合は、符号を逆にします。
SENSITIVITY_Y = -10.0   # Y軸（垂直方向）。Pitchの変化とカーソルの動きが逆の場合は、符号を逆にします。

# 小さなブレや振動を無視するための閾値（デッドゾーン）
# この値以下の角度変化ではマウスは動きません。
DEAD_ZONE = 0.5

# ----------------

# マウスの暴走を防ぐフェイルセーフ機能（pyautoguiの標準機能）
pyautogui.FAILSAFE = False

# 画面サイズの取得（参考情報）
screen_width, screen_height = pyautogui.size()
print(f"画面サイズ: {screen_width} x {screen_height}")
print("BNO055マウスコントローラーを開始します。終了するには Ctrl + C を押してください。")

try:
    # シリアルポートへの接続
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    print(f"シリアルポート '{SERIAL_PORT}' に接続しました。")
    # Arduinoのリセット直後はデータが不安定な場合があるため、少し待機
    time.sleep(2)
    ser.flushInput()

    # メインループ
    while True:
        
            try:
                # シリアルポートから1行読み込み、UTF-8文字列に変換
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                print(f"受信データ: {line}")  # 受信データを表示（デバッグ用）
                # データをカンマで分割
                parts = line.split(',')

                # データが6つの要素を持っているか確認
                if len(parts) == 6:
                    # Arduinoから送られてきた各値を取得
                    # 1番目: delta_h, 3番目: delta_p を使います
                    delta_h = float(parts[0])
                    delta_p = float(parts[2])

                    # --- マウスの移動量を計算 ---
                    move_x = 0
                    move_y = 0

                    # デッドゾーン（不感帯）処理
                    if abs(delta_h) > DEAD_ZONE:
                        move_x = delta_h * SENSITIVITY_X
                    
                    if abs(delta_p) > DEAD_ZONE:
                        move_y = delta_p * SENSITIVITY_Y

                    # マウスカーソルを相対的に移動
                    if move_x != 0 or move_y != 0:
                        pyautogui.moveRel(move_x, move_y)

                    # （デバッグ用）現在の値と移動量をコンソールに表示したい場合は、以下の行のコメントを外してください
                    # print(f"DeltaH: {delta_h:6.2f}, DeltaP: {delta_p:6.2f}  ->  MoveX: {move_x:6.1f}, MoveY: {move_y:6.1f}")

            except (UnicodeDecodeError, ValueError):
                # データ形式が不正な行は無視します
                # print(f"不正なデータをスキップ: {line}")
                pass
            except Exception as e:
                print(f"予期せぬエラーが発生しました: {e}")
                break

except serial.SerialException as e:
    print(f"エラー: シリアルポート '{SERIAL_PORT}' を開けません。")
    print("  - ポート名が正しいか、デバイスマネージャー等で確認してください。")
    print("  - デバイスがPCに正しく接続されているか確認してください。")
    print("  - 他のプログラム（Arduino IDEのシリアルモニタ等）がポートを使用中でないか確認してください。")

except KeyboardInterrupt:
    # Ctrl + C が押されたらループを抜ける
    print("\nプログラムを終了します。")

finally:
    # プログラム終了時にシリアルポートを必ず閉じる
    if 'ser' in locals() and ser.is_open:
        ser.close()
        print(f"シリアルポート '{SERIAL_PORT}' をクローズしました。")