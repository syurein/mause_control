import serial
import serial.tools.list_ports
import cv2
import PySimpleGUI as sg
import pyautogui
import numpy as np
import keyboard
import time

# ===================================================================
# --- 設定 (Settings) ---
# ===================================================================

# --- 状況判断のための「しきい値」設定 ---
# この値以下のIMUの加速度なら「静止」とみなす (m/s^2)
STATIONARY_IMU_ACCEL_THRESHOLD = 0.0001
# 1フレームでこのピクセル数以下のカメラの動きなら「静止/ノイズ」とみなす
STATIONARY_CAM_PIXEL_THRESHOLD = 5.0

# --- センサーフュージョン設定 ---
# 状態1(通常時)に、どのくらいカメラの値を信じるかの割合
ALPHA_NORMAL = 0.5
# 状態3(静止時)に、カメラのノイズをどのくらい無視するかの割合 (非常に小さい値)
ALPHA_STATIONARY = 0.1
# IMUの移動量に対するマウスの感度
IMU_SENSITIVITY = 150000.0

# --- シリアル通信設定 ---
SERIAL_PORT = 'COM12' 
BAUD_RATE = 115200

# --- マウス・カメラ設定 ---
BRIGHT_SPOT_THRESHOLD = 200
MOUSE_MOVE_DURATION = 0.0 # 0にすることで最も機敏に反応
SAFETY_MARGIN_PERCENT = 0.1

# --- UI・デバッグ設定 ---
UI_ENABLED = True

# ===================================================================
# --- プログラム本体 (ここから下は変更不要です) ---
# ===================================================================

# --- グローバル変数 ---
mouse_control_active = True
pyautogui.FAILSAFE = False
fused_screen_x, fused_screen_y = pyautogui.size()[0] / 2, pyautogui.size()[1] / 2
last_cam_x, last_cam_y = fused_screen_x, fused_screen_y

def find_serial_port():
    ports = serial.tools.list_ports.comports()
    if not ports: return None
    print("利用可能なシリアルポート:")
    for port in ports: print(f"  - {port.device}")
    return ports[0].device

def toggle_mouse_control():
    global mouse_control_active
    mouse_control_active = not mouse_control_active
    print(f"\nマウス制御を{'再開' if mouse_control_active else '一時停止'}しました。")

keyboard.on_press_key("esc", lambda _: toggle_mouse_control())

def main():
    global fused_screen_x, fused_screen_y, last_cam_x, last_cam_y
    
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        sg.popup_error("エラー: Webカメラを開けませんでした。")
        return

    ser = None
    port_to_use = SERIAL_PORT
    if port_to_use == 'auto': port_to_use = find_serial_port()
    if port_to_use:
        try:
            ser = serial.Serial(port_to_use, BAUD_RATE, timeout=0.1)
            print(f"✅ IMU接続成功: '{port_to_use}'")
            time.sleep(2)
        except serial.SerialException as e:
            print(f"⚠️ 警告: IMUポートを開けません。カメラのみで動作します。\n{e}")
    else:
        print("⚠️ 警告: IMUが見つかりません。カメラのみで動作します。")

    actual_cam_width, actual_cam_height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    CAM_X_MIN, CAM_X_MAX = actual_cam_width * SAFETY_MARGIN_PERCENT, actual_cam_width * (1 - SAFETY_MARGIN_PERCENT)
    CAM_Y_MIN, CAM_Y_MAX = actual_cam_height * SAFETY_MARGIN_PERCENT, actual_cam_height * (1 - SAFETY_MARGIN_PERCENT)
    SCREEN_WIDTH, SCREEN_HEIGHT = pyautogui.size()

    window = None
    if UI_ENABLED:
        sg.theme('Black')
        layout = [
            [sg.Text('適応型センサーフュージョン マウス追従', size=(60, 1), justification='center')],
            [sg.Text('状態: 起動中...', key='-STATUS-', size=(60, 1), justification='center', text_color='lightgreen')],
            [sg.Image(filename='', key='-IMAGE-')],
            [sg.Button('終了', size=(10, 1))]
        ]
        window = sg.Window('Adaptive Sensor Fusion Mouse Tracker', layout, location=(800, 400), finalize=True)

    print("プログラムを開始しました。")
    
    try:
        while True:
            if UI_ENABLED:
                event, values = window.read(timeout=1)
                if event == '終了' or event == sg.WIN_CLOSED: break

            # --- データの取得 ---
            ret, frame = cap.read()
            if not ret: break
            frame = cv2.flip(frame, 1)
            
            # 1. IMUデータの読み取り
            is_imu_moving = False
            imu_delta_x, imu_delta_y = 0.0, 0.0
            if ser and ser.in_waiting > 0:
                try:
                    line = ser.readline().decode('utf-8').strip()
                    parts = line.split(',') # Time,PosX,PosY,PosZ,VelX,VelY,VelZ,AccX,AccY,AccZ
                    if len(parts) >= 10:
                        # 差分ではなく、加速度の大きさで動きを判断
                        acc_x, acc_y = float(parts[7]), float(parts[8])
                        if abs(acc_x) > STATIONARY_IMU_ACCEL_THRESHOLD or abs(acc_y) > STATIONARY_IMU_ACCEL_THRESHOLD:
                            is_imu_moving = True
                        
                        # 位置の差分も計算
                        pos_x, pos_y = float(parts[1]), float(parts[2])
                        # 初回データはスキップ
                        if 'last_imu_x' in locals():
                            imu_delta_x = pos_x - last_imu_x
                            imu_delta_y = pos_y - last_imu_y
                        last_imu_x, last_imu_y = pos_x, pos_y
                except (UnicodeDecodeError, ValueError, IndexError):
                    pass

            # 2. カメラデータの読み取り
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            (minVal, maxVal, minLoc, maxLoc) = cv2.minMaxLoc(gray)
            is_cam_tracking = maxVal >= BRIGHT_SPOT_THRESHOLD
            
            camera_screen_x, camera_screen_y = 0, 0
            if is_cam_tracking:
                cam_x_raw, cam_y_raw = maxLoc
                camera_screen_x = np.interp(cam_x_raw, [CAM_X_MIN, CAM_X_MAX], [0, SCREEN_WIDTH - 1])
                camera_screen_y = np.interp(cam_y_raw, [CAM_Y_MIN, CAM_Y_MAX], [0, SCREEN_HEIGHT - 1])

            # --- 状況判断とフュージョンロジック ---
            status_text, status_color = "待機中", "gray"
            
            if mouse_control_active:
                # 状態2: IMU予測モード (カメラロスト & IMUは動いている)
                if not is_cam_tracking and is_imu_moving and imu_delta_x != 0:
                    status_text, status_color = "状態: IMU予測モード (カメラロスト)", "magenta"
                    fused_screen_x += imu_delta_x * IMU_SENSITIVITY
                    fused_screen_y -= imu_delta_y * IMU_SENSITIVITY # Y軸反転
                    cv2.putText(frame, "IMU PREDICTION", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 255), 2)
                
                # カメラが追跡できている場合
                elif is_cam_tracking:
                    cam_delta = np.sqrt((camera_screen_x - last_cam_x)**2 + (camera_screen_y - last_cam_y)**2)
                    is_cam_moving = cam_delta > STATIONARY_CAM_PIXEL_THRESHOLD
                    
                    # 状態3: カメラノイズ抑制モード (IMU静止 & カメラは微動)
                    if not is_imu_moving and is_cam_moving:
                        status_text, status_color = "状態: ノイズ抑制モード (IMU静止)", "orange"
                        # IMUを信じて、カメラの補正を非常に弱くする
                        alpha = ALPHA_STATIONARY
                        fused_screen_x = (1 - alpha) * fused_screen_x + alpha * camera_screen_x
                        fused_screen_y = (1 - alpha) * fused_screen_y + alpha * camera_screen_y
                        cv2.circle(frame, maxLoc, 20, (0, 165, 255), 2)
                    
                    # 状態1: 通常追跡モード (両方が動いている、または両方が静止)
                    else:
                        status_text, status_color = "状態: 通常追跡モード", "cyan"
                        alpha = ALPHA_NORMAL
                        fused_screen_x = (1 - alpha) * fused_screen_x + alpha * camera_screen_x
                        fused_screen_y = (1 - alpha) * fused_screen_y + alpha * camera_screen_y
                        cv2.circle(frame, maxLoc, 20, (255, 255, 0), 2)

            # --- マウス移動 & UI更新 ---
            if mouse_control_active:
                final_x = np.clip(fused_screen_x, 0, SCREEN_WIDTH - 1)
                final_y = np.clip(fused_screen_y, 0, SCREEN_HEIGHT - 1)
                pyautogui.moveTo(final_x, final_y, duration=MOUSE_MOVE_DURATION)

            if UI_ENABLED:
                window['-STATUS-'].update(status_text, text_color=status_color)
                display_frame = cv2.resize(frame, (640, 480))
                imgbytes = cv2.imencode('.png', display_frame)[1].tobytes()
                window['-IMAGE-'].update(data=imgbytes)
            
            last_cam_x, last_cam_y = camera_screen_x, camera_screen_y

    finally:
        print("\nクリーンアップ処理を実行しています...")
        cap.release()
        if ser: ser.close()
        if UI_ENABLED and window: window.close()
        keyboard.unhook_all()
        print("終了しました。")

if __name__ == '__main__':
    main()