import cv2
import PySimpleGUI as sg
import pyautogui
import numpy as np
import keyboard
import time

# ===================================================================
# --- 設定 (Settings) ---
# ここでプログラムの挙動をカスタマイズできます
# ===================================================================

# --- 基本設定 ---
# GUIウィンドウを表示するか (True: 表示する, False: 裏で動かす)
UI_ENABLED = True
# デバッグ情報をコンソールに出力するか
DEBUG_PRINT_ENABLED = True

# --- マウス制御の閾値 ---
# 最も明るい点の輝度がこの値以上の場合に、マウスが反応します (0〜255の値で指定)
# 例: 暗い部屋でスマートフォンのライトを追従させる場合は 200 前後がおすすめです
BRIGHT_SPOT_THRESHOLD = 200

# --- 動作の微調整 ---
# マウス移動の滑らかさ (秒数)。小さいほど機敏に、大きいほど滑らかに動きます
MOUSE_MOVE_DURATION = 0.1
# カメラ映像の端を無視する割合 (0.0 ~ 0.4)。ノイズによる暴走を防ぎます
SAFETY_MARGIN_PERCENT = 0.1


# ===================================================================
# --- プログラム本体 (ここから下は変更不要です) ---
# ===================================================================

# --- グローバル変数 ---
mouse_control_active = True
pyautogui.FAILSAFE = False

def toggle_mouse_control():
    """ESCキーでマウス制御の手動ON/OFFを切り替える"""
    global mouse_control_active
    mouse_control_active = not mouse_control_active
    if mouse_control_active:
        print("\nマウス制御を手動で再開しました。")
    else:
        print("\nマウス制御を手動で一時停止しました。ESCキーで再開します。")

keyboard.on_press_key("esc", lambda _: toggle_mouse_control())

def main():
    """メイン処理"""
    window = None
    
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        sg.popup_error("エラー: Webカメラを開けませんでした。")
        return

    actual_cam_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_cam_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    CAM_X_MIN = actual_cam_width * SAFETY_MARGIN_PERCENT
    CAM_X_MAX = actual_cam_width * (1 - SAFETY_MARGIN_PERCENT)
    CAM_Y_MIN = actual_cam_height * SAFETY_MARGIN_PERCENT
    CAM_Y_MAX = actual_cam_height * (1 - SAFETY_MARGIN_PERCENT)

    SCREEN_WIDTH, SCREEN_HEIGHT = pyautogui.size()

    if UI_ENABLED:
        sg.theme('Black')
        layout = [
            [sg.Text('Webカメラ映像', size=(60, 1), justification='center')],
            [sg.Text('状態: 起動中...', key='-STATUS-', size=(60, 1), justification='center', text_color='lightgreen')],
            [sg.Image(filename='', key='-IMAGE-')],
            [sg.Button('終了', size=(10, 1))]
        ]
        window = sg.Window('マウス追従プログラム', layout, location=(800, 400), finalize=True)
    
    print("--------------------------------------------------")
    print(f"✅ 画面解像度: {SCREEN_WIDTH} x {SCREEN_HEIGHT} | カメラ解像度: {actual_cam_width} x {actual_cam_height}")
    print(f"✅ マウス制御の輝度しきい値: {BRIGHT_SPOT_THRESHOLD}")
    print("--------------------------------------------------")
    print("プログラムを開始しました。ESCキーで制御を一時停止/再開できます。")

    try:
        while True:
            if UI_ENABLED:
                event, values = window.read(timeout=20)
                if event == '終了' or event == sg.WIN_CLOSED:
                    break
            
            ret, frame = cap.read()
            if not ret:
                print("エラー: フレームを取得できません。")
                break
            
            frame = cv2.flip(frame, 1)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            (minVal, maxVal, minLoc, maxLoc) = cv2.minMaxLoc(gray)
            cam_x_raw, cam_y_raw = maxLoc

            # ★ 変更点: 最も明るい点(maxVal)の輝度がしきい値を超えているかで判断
            is_target_bright_enough = maxVal >= BRIGHT_SPOT_THRESHOLD

            status_text = ""
            if mouse_control_active and is_target_bright_enough:
                status_text = f'状態: 制御中 (検出輝度: {maxVal})'
                
                screen_x = np.interp(cam_x_raw, [CAM_X_MIN, CAM_X_MAX], [0, SCREEN_WIDTH - 1])
                screen_y = np.interp(cam_y_raw, [CAM_Y_MIN, CAM_Y_MAX], [0, SCREEN_HEIGHT - 1])
                
                screen_x = np.clip(screen_x, 0, SCREEN_WIDTH - 1)
                screen_y = np.clip(screen_y, 0, SCREEN_HEIGHT - 1)

                pyautogui.moveTo(screen_x, screen_y, duration=MOUSE_MOVE_DURATION)

                if DEBUG_PRINT_ENABLED:
                    print(f"\r{status_text} | Cam(x,y): ({cam_x_raw}, {cam_y_raw}) -> Screen(x,y): ({int(screen_x)}, {int(screen_y)})    ", end="")

                if UI_ENABLED:
                    window['-STATUS-'].update(status_text, text_color='lightgreen')
                    cv2.circle(frame, maxLoc, 20, (0, 255, 0), 2)
            else:
                if not mouse_control_active:
                    status_text = '状態: 手動で一時停止中 (ESCキーで再開)'
                elif not is_target_bright_enough:
                    # ★ 変更点: 新しい条件に合わせた待機メッセージ
                    status_text = f'状態: 待機中 (検出輝度 {maxVal} がしきい値未満)'
                
                if DEBUG_PRINT_ENABLED:
                    print(f"\r{status_text}                                                                      ", end="")

                if UI_ENABLED:
                    window['-STATUS-'].update(status_text, text_color='orange')
                    cv2.circle(frame, maxLoc, 10, (0, 0, 255), 2)
            
            if UI_ENABLED:
                display_frame = cv2.resize(frame, (640, 480))
                imgbytes = cv2.imencode('.png', display_frame)[1].tobytes()
                window['-IMAGE-'].update(data=imgbytes)
            else:
                time.sleep(0.02)

    except KeyboardInterrupt:
        print("\nプログラムが中断されました。")
    finally:
        print("\nクリーンアップ処理を実行しています...")
        cap.release()
        if UI_ENABLED and window:
            window.close()
        keyboard.unhook_all()
        print("終了しました。")

if __name__ == '__main__':
    main()