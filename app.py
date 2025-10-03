# ===================================================================
# --- ライブラリのインポート (Import Libraries) ---
# ===================================================================
import serial
import serial.tools.list_ports
import cv2
import PySimpleGUI as sg
import pyautogui
import numpy as np
import keyboard
import time
from flask import Flask
from threading import Thread
import socket

# ===================================================================
# --- 設定項目 (Initial Settings) ---
# これらの値はUIから変更可能です
# ===================================================================

# --- シリアル通信設定 ---
SERIAL_PORT = 'COM12'
BAUD_RATE = 115200

# --- Webサーバー設定 ---
FLASK_PORT = 5000

# --- IMU (BNO055) 設定 ---
SENSITIVITY_X = 5.0   # X軸（水平方向）の感度
SENSITIVITY_Y = -10.0 # Y軸（垂直方向）の感度
DEAD_ZONE = 0.5       # IMUの動きを無視する閾値
DELTA_THRESH = 0.5    # カメラの動きを「わずかに動いている」とみなす閾値
# --- カメラ設定 ---
BRIGHT_SPOT_THRESHOLD = 200 # 追跡対象とみなす輝度の閾値
SAFETY_MARGIN_PERCENT = 0.1 # カメラ映像の端を除外する割合

# --- センサーフュージョン設定 ---
ALPHA_NORMAL = 0.4      # 通常時のカメラ追従度
ALPHA_STATIONARY = 0.1  # 静止時のノイズ抑制強度

# --- UI・デバッグ設定 ---
UI_ENABLED = True # FalseにするとGUIウィンドウを表示しません

# ===================================================================
# --- プログラム本体 (ここから下は原則として変更不要です) ---
# ===================================================================

# --- グローバル変数 ---
mouse_control_active = True
pyautogui.FAILSAFE = False
fused_screen_x, fused_screen_y = pyautogui.size()[0] / 2, pyautogui.size()[1] / 2
last_cam_x, last_cam_y = fused_screen_x, fused_screen_y

def find_serial_port():
    """利用可能なシリアルポートを探してPicoと思われるポートを返す"""
    ports = serial.tools.list_ports.comports()
    if not ports:
        return None
    print("利用可能なシリアルポート:")
    for port in ports:
        print(f"  - {port.device} ({port.description})")
    for port in ports:
        if 'pico' in port.description.lower() or 'usb serial' in port.description.lower():
            print(f"Picoと思われるポート '{port.device}' を選択しました。")
            return port.device
    if ports:
        print(f"Picoが見つからないため、最初のポート '{ports[0].device}' を選択します。")
        return ports[0].device
    return None

def get_ip_address():
    """ローカルIPアドレスを取得する"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def toggle_mouse_control(event=None):
    """マウス制御の有効/無効を切り替える"""
    global mouse_control_active
    mouse_control_active = not mouse_control_active
    status = '再開' if mouse_control_active else '一時停止'
    print(f"\n[操作] マウス制御を{status}しました。(ESCキーで切り替え)")

keyboard.on_press_key("esc", toggle_mouse_control)

def run_flask_app(ser_instance):
    """Webサーバーを起動してシリアル通信を中継する"""
    app = Flask(__name__)
    @app.route('/send/<data>')
    def send_data(data):
        if ser_instance and ser_instance.is_open:
            if data in ['1', '2']:
                try:
                    ser_instance.write(data.encode('utf-8'))
                    print(f"📨 [Web] デバイスに '{data}' を送信しました。")
                    return f"<h1>'{data}' をデバイスに送信しました</h1>"
                except serial.SerialException as e:
                    return f"<h1>送信エラー</h1><p>{e}</p>", 500
            else:
                return "<h1>無効なリクエストです</h1>", 400
        else:
            return "<h1>送信エラー</h1><p>サーバー側でシリアルデバイスが接続されていません。</p>", 503
    local_ip = get_ip_address()
    print("\n" + "="*50)
    print("🚀 Webサーバーが起動しました。")
    print(f"   URLにアクセスしてクリック操作ができます:")
    print(f"   - http://{local_ip}:{FLASK_PORT}/send/1 (左クリック相当)")
    print(f"   - http://{local_ip}:{FLASK_PORT}/send/2 (右クリック相当)")
    print("="*50 + "\n")
    app.run(host='0.0.0.0', port=FLASK_PORT, debug=False, use_reloader=False)

def main():
    global fused_screen_x, fused_screen_y, last_cam_x, last_cam_y

    # --- パラメータをローカル変数にコピー ---
    p_sens_x = SENSITIVITY_X
    p_sens_y = SENSITIVITY_Y
    p_dead_zone = DEAD_ZONE
    p_bright_thresh = BRIGHT_SPOT_THRESHOLD
    p_alpha_normal = ALPHA_NORMAL
    p_alpha_stationary = ALPHA_STATIONARY
    delta_threshold = DELTA_THRESH
    noise_flag=False
    # --- Webカメラの初期化 ---
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        sg.popup_error("エラー: Webカメラを開けませんでした。")
        return

    # --- シリアルポートの初期化 ---
    ser = None
    port_to_use = SERIAL_PORT
    if port_to_use.lower() == 'auto':
        port_to_use = find_serial_port()
    if port_to_use:
        try:
            ser = serial.Serial(port=port_to_use, baudrate=BAUD_RATE, timeout=0.1)
            print(f"✅ IMU接続成功: '{port_to_use}' @ {BAUD_RATE} bps")
            time.sleep(2)
            ser.flushInput()
        except serial.SerialException as e:
            print(f"⚠️ 警告: IMUポート '{port_to_use}' を開けません。カメラのみで動作します。\n   {e}")
            ser = None
    else:
        print("⚠️ 警告: IMUが見つかりません。カメラのみで動作します。")

    # --- Webサーバーをバックグラウンドで起動 ---
    flask_thread = Thread(target=run_flask_app, args=(ser,), daemon=True)
    flask_thread.start()

    # --- 画面とカメラのサイズ設定 ---
    cam_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    cam_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    CAM_X_MIN = cam_width * SAFETY_MARGIN_PERCENT
    CAM_X_MAX = cam_width * (1 - SAFETY_MARGIN_PERCENT)
    CAM_Y_MIN = cam_height * SAFETY_MARGIN_PERCENT
    CAM_Y_MAX = cam_height * (1 - SAFETY_MARGIN_PERCENT)
    SCREEN_WIDTH, SCREEN_HEIGHT = pyautogui.size()

    # --- GUIウィンドウの初期化 ---
    window = None
    if UI_ENABLED:
        sg.theme('Black')
        
        # --- UIレイアウト定義 ---
        video_column = [
            [sg.Text('状態: 起動中...', key='-STATUS-', size=(40, 1), justification='center', text_color='lightgreen')],
            [sg.Image(filename='', key='-IMAGE-')]
        ]

        param_column = [
            [sg.Checkbox('IMUセンサーを利用する', default=False, key='-USE_IMU-', disabled=ser is None, enable_events=True)],
            [sg.Frame('IMU設定', [
                [sg.Text('感度 X', size=(10,1)), sg.Slider(range=(-100.0, 100.0), default_value=p_sens_x, resolution=0.1, orientation='h', key='-SENS_X-', enable_events=True, size=(20,15))],
                [sg.Text('感度 Y', size=(10,1)), sg.Slider(range=(-100.0, 100.0), default_value=p_sens_y, resolution=0.1, orientation='h', key='-SENS_Y-', enable_events=True, size=(20,15))],
                [sg.Text('静止閾値', size=(10,1)), sg.Slider(range=(75.0, 80.0), default_value=p_dead_zone, resolution=0.1, orientation='h', key='-DEAD_ZONE-', enable_events=True, size=(20,15))]
            ], key='-IMU_FRAME-')],
            [sg.Frame('カメラ・フュージョン設定', [
                [sg.Checkbox('ノイズ抑制モード', default=False, key='-USE_DELAY-', disabled=ser is None, enable_events=True)],
                [sg.Text('輝度しきい値', size=(10,1)), sg.Slider(range=(50, 255), default_value=p_bright_thresh, resolution=1, orientation='h', key='-BRIGHT-', enable_events=True, size=(20,15))],
                [sg.Text('追従度（ここでスムーズに動くかどうかが決まる）', size=(10,1)), sg.Slider(range=(0.1, 1.0), default_value=p_alpha_normal, resolution=0.05, orientation='h', key='-ALPHA_N-', enable_events=True, size=(20,15))],
                [sg.Text('ノイズ抑制（動かないときのブレを抑える）', size=(10,1)), sg.Slider(range=(0.1, 0.5), default_value=p_alpha_stationary, resolution=0.01, orientation='h', key='-ALPHA_S-', enable_events=True, size=(20,15))],
                [sg.Text('カメラ動作閾値', size=(10,1)), sg.Slider(range=(0, 10), default_value=delta_threshold, resolution=0.01, orientation='h', key='-CAM-', enable_events=True, size=(20,15))]
            ])],
            [sg.VPush()],
            [sg.Button('終了', size=(10, 1))]
        ]

        layout = [[sg.Column(video_column), sg.VSeperator(), sg.Column(param_column)]]
        window = sg.Window('Adaptive Sensor Fusion Mouse Tracker', layout, finalize=True)

    print("プログラムを開始しました。ESCキーでマウス制御を一時停止/再開できます。")

    # --- メインループ ---
    try:
        while True:
            if UI_ENABLED:
                event, values = window.read(timeout=1)
                if event == '終了' or event == sg.WIN_CLOSED:
                    break
                
                # --- UIからパラメータを更新 ---
                p_sens_x = values['-SENS_X-']
                p_sens_y = values['-SENS_Y-']
                p_dead_zone = values['-DEAD_ZONE-']
                p_bright_thresh = values['-BRIGHT-']
                p_alpha_normal = values['-ALPHA_N-']
                p_alpha_stationary = values['-ALPHA_S-']
                use_imu = values['-USE_IMU-']
                noise_flag=values['-USE_DELAY-']
                delta_threshold=values['-CAM-']
                # IMUが無効なら関連スライダーも無効化
                window['-IMU_FRAME-'].update(visible=use_imu)

            else: # UI無効時のダミー変数
                use_imu = ser is not None

            # --- 1. カメラデータの取得 ---
            ret, frame = cap.read()
            if not ret: break
            frame = cv2.flip(frame, 1)

            # --- 2. IMUデータの取得 ---
            delta_h, delta_p, is_imu_moving = 0.0, 0.0, False
            if ser and use_imu and ser.in_waiting > 0:
                try:
                    line = ser.readline().decode('utf-8', 'ignore').strip()
                    if line:
                        parts = line.split(',')
                        if len(parts) == 6:
                            delta_h, delta_p = float(parts[0]), float(parts[2])
                            if abs(delta_h) > p_dead_zone or abs(delta_p) > p_dead_zone:
                                is_imu_moving = True
                except (UnicodeDecodeError, ValueError, IndexError):
                    pass

            # --- 3. カメラ画像処理 ---
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            (_, maxVal, _, maxLoc) = cv2.minMaxLoc(gray)
            is_cam_tracking = maxVal >= p_bright_thresh
            
            camera_screen_x, camera_screen_y = last_cam_x, last_cam_y
            if is_cam_tracking:
                cam_x_raw, cam_y_raw = maxLoc
                camera_screen_x = np.interp(cam_x_raw, [CAM_X_MIN, CAM_X_MAX], [0, SCREEN_WIDTH - 1])
                camera_screen_y = np.interp(cam_y_raw, [CAM_Y_MIN, CAM_Y_MAX], [0, SCREEN_HEIGHT - 1])

            # --- 4. 状況判断とセンサーフュージョン ---
            if mouse_control_active:
                if use_imu and ser: # --- センサーフュージョンモード ---
                    if not is_cam_tracking and is_imu_moving:
                        status_text, status_color = "状態: IMU予測モード", "magenta"
                        fused_screen_x += delta_h * p_sens_x
                        fused_screen_y += delta_p * p_sens_y
                        cv2.putText(frame, "IMU PREDICTION", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,0,255), 2)
                    elif is_cam_tracking:
                        cam_delta = np.sqrt((camera_screen_x - last_cam_x)**2 + (camera_screen_y - last_cam_y)**2)
                        is_cam_moving_slightly = cam_delta > delta_threshold
                        if not is_imu_moving and is_cam_moving_slightly:
                            status_text, status_color = "状態: ノイズ抑制モード", "orange"
                            alpha = p_alpha_stationary
                            cv2.circle(frame, maxLoc, 20, (0, 165, 255), 2)
                        else:
                            status_text, status_color = "状態: 通常追跡モード", "cyan"
                            alpha = p_alpha_normal
                            cv2.circle(frame, maxLoc, 20, (255, 255, 0), 2)
                        fused_screen_x = (1 - alpha) * fused_screen_x + alpha * camera_screen_x
                        fused_screen_y = (1 - alpha) * fused_screen_y + alpha * camera_screen_y
                    else:
                        status_text, status_color = "状態: 追跡対象なし", "red"
                
                else: # --- カメラ単独モード ---
                    if is_cam_tracking:
                        cam_delta = np.sqrt((camera_screen_x - last_cam_x)**2 + (camera_screen_y - last_cam_y)**2)
                        is_cam_moving_slightly = cam_delta > delta_threshold
                        if noise_flag:
                            status_text, status_color = "状態: 単独ノイズ抑制モード", "orange"
                            alpha = p_alpha_stationary
                            
                        else:
                            status_text, status_color = "状態: カメラ単独モード", "lime"
                            alpha = p_alpha_normal
                        fused_screen_x = (1 - alpha) * fused_screen_x + alpha * camera_screen_x
                        fused_screen_y = (1 - alpha) * fused_screen_y + alpha * camera_screen_y
                        cv2.circle(frame, maxLoc, 20, (0, 255, 0), 2)
                    

                    else:
                        status_text, status_color = "状態: 追跡対象なし", "red"
            else:
                status_text, status_color = "状態: 一時停止中 (ESCキーで再開)", "yellow"

            # --- 5. マウス移動 & UI更新 ---
            if mouse_control_active:
                final_x = np.clip(fused_screen_x, 0, SCREEN_WIDTH - 1)
                final_y = np.clip(fused_screen_y, 0, SCREEN_HEIGHT - 1)
                pyautogui.moveTo(final_x, final_y)

            if UI_ENABLED:
                window['-STATUS-'].update(status_text, text_color=status_color)
                display_frame = cv2.resize(frame, (640, 480))
                imgbytes = cv2.imencode('.png', display_frame)[1].tobytes()
                window['-IMAGE-'].update(data=imgbytes)
            
            last_cam_x, last_cam_y = camera_screen_x, camera_screen_y

    finally:
        print("\nクリーンアップ処理を実行しています...")
        cap.release()
        if ser and ser.is_open: ser.close(); print("シリアルポートを閉じました。")
        if UI_ENABLED and window: window.close()
        keyboard.unhook_all()
        print("終了しました。")

if __name__ == '__main__':
    main()

