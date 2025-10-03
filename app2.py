# ===================================================================
# --- ライブラリのインポート (Import Libraries) ---
# ===================================================================
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import serial
import serial.tools.list_ports
import cv2
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
SERIAL_PORT = 'auto' # 'auto'にするとPicoを自動検索します
BAUD_RATE = 115200

# --- Webサーバー設定 ---
FLASK_PORT = 5000

# --- IMU (BNO055) 設定 ---
SENSITIVITY_X = 5.0      # X軸（水平方向）の感度
SENSITIVITY_Y = -10.0    # Y軸（垂直方向）の感度
DEAD_ZONE = 0.5          # IMUの動きを無視する閾値
DELTA_THRESH = 0.5       # カメラの動きを「わずかに動いている」とみなす閾値
# --- カメラ設定 ---
BRIGHT_SPOT_THRESHOLD = 200 # 追跡対象とみなす輝度の閾値
SAFETY_MARGIN_PERCENT = 0.1 # カメラ映像の端を除外する割合

# --- センサーフュージョン設定 ---
ALPHA_NORMAL = 0.4       # 通常時のカメラ追従度
ALPHA_STATIONARY = 0.1   # 静止時のノイズ抑制強度

# ===================================================================
# --- グローバル関数 (Global Functions) ---
# ===================================================================

def find_serial_port():
    """利用可能なシリアルポートを探してPicoと思われるポートを返す"""
    ports = serial.tools.list_ports.comports()
    if not ports:
        return None
    print("利用可能なシリアルポート:")
    for port in ports:
        print(f"  - {port.device} ({port.description})")
    for port in ports:
        if 'USB シリアル' in port.description:
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

# ===================================================================
# --- アプリケーションクラス (Application Class) ---
# ===================================================================

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Adaptive Sensor Fusion Mouse Tracker (Tkinter)")

        # --- グローバル変数をインスタンス変数として初期化 ---
        self.mouse_control_active = True
        pyautogui.FAILSAFE = False
        self.fused_screen_x, self.fused_screen_y = pyautogui.size()[0] / 2, pyautogui.size()[1] / 2
        self.last_cam_x, self.last_cam_y = self.fused_screen_x, self.fused_screen_y
        self.ser = None

        # --- Tkinter変数の設定 ---
        self.use_imu_var = tk.BooleanVar(value=False) # ★ 変更点: デフォルトをFalseに
        self.noise_flag_var = tk.BooleanVar(value=False)
        self.sens_x_var = tk.DoubleVar(value=SENSITIVITY_X)
        self.sens_y_var = tk.DoubleVar(value=SENSITIVITY_Y)
        self.dead_zone_var = tk.DoubleVar(value=DEAD_ZONE)
        self.bright_thresh_var = tk.IntVar(value=BRIGHT_SPOT_THRESHOLD)
        self.alpha_n_var = tk.DoubleVar(value=ALPHA_NORMAL)
        self.alpha_s_var = tk.DoubleVar(value=ALPHA_STATIONARY)
        self.cam_delta_thresh_var = tk.DoubleVar(value=DELTA_THRESH)

        # --- UIの作成 ---
        self.create_widgets()

        # --- 初期化処理 ---
        self.init_camera()
        self.init_serial()
        self.start_flask_server()

        # --- キーボードフック ---
        keyboard.on_press_key("esc", self.toggle_mouse_control)

        # --- メインループの開始 ---
        self.update()
        
        # --- 終了処理 ---
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        """TkinterのUIウィジェットを作成・配置する"""
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # --- 左側：ビデオ表示 ---
        video_frame = ttk.Frame(main_frame)
        video_frame.grid(row=0, column=0, padx=10, sticky="ns")
        
        self.status_label = ttk.Label(video_frame, text="状態: 起動中...", font=("Helvetica", 12), foreground="lightgreen")
        self.status_label.pack(pady=5)
        
        self.image_label = ttk.Label(video_frame)
        self.image_label.pack()

        # --- セパレータ ---
        ttk.Separator(main_frame, orient=tk.VERTICAL).grid(row=0, column=1, sticky="ns", padx=10)

        # --- 右側：パラメータ設定 ---
        param_frame = ttk.Frame(main_frame)
        param_frame.grid(row=0, column=2, sticky="ns")

        # IMU設定フレーム
        self.use_imu_check = ttk.Checkbutton(param_frame, text="IMUセンサーを利用する", variable=self.use_imu_var, command=self.toggle_imu_frame)
        self.use_imu_check.pack(anchor='w', pady=5)
        
        self.imu_frame = ttk.LabelFrame(param_frame, text="IMU設定")
        
        # --- ★ 変更点: スライダーと値表示ラベルをセットで作成 ---
        # 感度 X
        sens_x_frame = ttk.Frame(self.imu_frame)
        sens_x_frame.pack(fill='x', padx=5, pady=2)
        ttk.Label(sens_x_frame, text="感度 X", width=20).pack(side='left')
        sens_x_val_label = ttk.Label(sens_x_frame, text=f"{self.sens_x_var.get():.1f}", width=5, anchor='e')
        sens_x_val_label.pack(side='right', padx=(5,0))
        ttk.Scale(sens_x_frame, from_=-100.0, to=100.0, orient='horizontal', variable=self.sens_x_var,
                  command=lambda v: sens_x_val_label.config(text=f"{float(v):.1f}")).pack(side='right', expand=True, fill='x')

        # 感度 Y
        sens_y_frame = ttk.Frame(self.imu_frame)
        sens_y_frame.pack(fill='x', padx=5, pady=2)
        ttk.Label(sens_y_frame, text="感度 Y", width=20).pack(side='left')
        sens_y_val_label = ttk.Label(sens_y_frame, text=f"{self.sens_y_var.get():.1f}", width=5, anchor='e')
        sens_y_val_label.pack(side='right', padx=(5,0))
        ttk.Scale(sens_y_frame, from_=-100.0, to=100.0, orient='horizontal', variable=self.sens_y_var,
                  command=lambda v: sens_y_val_label.config(text=f"{float(v):.1f}")).pack(side='right', expand=True, fill='x')

        # 静止閾値
        dead_zone_frame = ttk.Frame(self.imu_frame)
        dead_zone_frame.pack(fill='x', padx=5, pady=2)
        ttk.Label(dead_zone_frame, text="静止閾値", width=20).pack(side='left')
        dead_zone_val_label = ttk.Label(dead_zone_frame, text=f"{self.dead_zone_var.get():.1f}", width=5, anchor='e')
        dead_zone_val_label.pack(side='right', padx=(5,0))
        ttk.Scale(dead_zone_frame, from_=0.0, to=5.0, orient='horizontal', variable=self.dead_zone_var,
                  command=lambda v: dead_zone_val_label.config(text=f"{float(v):.1f}")).pack(side='right', expand=True, fill='x')

        # カメラ・フュージョン設定フレーム
        self.cam_fusion_frame = ttk.LabelFrame(param_frame, text="カメラ・フュージョン設定")
        self.cam_fusion_frame.pack(fill='x', padx=5, pady=10, anchor='n')
        
        ttk.Checkbutton(self.cam_fusion_frame, text="ノイズ抑制モード (カメラ単独時)", variable=self.noise_flag_var).pack(anchor='w', padx=5)
        
        # 輝度しきい値
        bright_thresh_frame = ttk.Frame(self.cam_fusion_frame)
        bright_thresh_frame.pack(fill='x', padx=5, pady=(10,0))
        ttk.Label(bright_thresh_frame, text="輝度しきい値", width=20).pack(side='left')
        bright_thresh_val_label = ttk.Label(bright_thresh_frame, text=f"{self.bright_thresh_var.get()}", width=5, anchor='e')
        bright_thresh_val_label.pack(side='right', padx=(5,0))
        ttk.Scale(bright_thresh_frame, from_=50, to=255, orient='horizontal', variable=self.bright_thresh_var,
                  command=lambda v: bright_thresh_val_label.config(text=f"{int(float(v))}")).pack(side='right', expand=True, fill='x')

        # 追従度
        alpha_n_frame = ttk.Frame(self.cam_fusion_frame)
        alpha_n_frame.pack(fill='x', padx=5, pady=2)
        ttk.Label(alpha_n_frame, text="追従度（スムーズさ）", width=20).pack(side='left')
        alpha_n_val_label = ttk.Label(alpha_n_frame, text=f"{self.alpha_n_var.get():.2f}", width=5, anchor='e')
        alpha_n_val_label.pack(side='right', padx=(5,0))
        ttk.Scale(alpha_n_frame, from_=0.1, to=1.0, orient='horizontal', variable=self.alpha_n_var,
                  command=lambda v: alpha_n_val_label.config(text=f"{float(v):.2f}")).pack(side='right', expand=True, fill='x')

        # ノイズ抑制
        alpha_s_frame = ttk.Frame(self.cam_fusion_frame)
        alpha_s_frame.pack(fill='x', padx=5, pady=2)
        ttk.Label(alpha_s_frame, text="ノイズ抑制（静止時のブレ）", width=20).pack(side='left')
        alpha_s_val_label = ttk.Label(alpha_s_frame, text=f"{self.alpha_s_var.get():.2f}", width=5, anchor='e')
        alpha_s_val_label.pack(side='right', padx=(5,0))
        ttk.Scale(alpha_s_frame, from_=0.01, to=0.5, orient='horizontal', variable=self.alpha_s_var,
                  command=lambda v: alpha_s_val_label.config(text=f"{float(v):.2f}")).pack(side='right', expand=True, fill='x')

        # カメラ動作閾値
        cam_delta_frame = ttk.Frame(self.cam_fusion_frame)
        cam_delta_frame.pack(fill='x', padx=5, pady=2)
        ttk.Label(cam_delta_frame, text="カメラ動作閾値", width=20).pack(side='left')
        cam_delta_val_label = ttk.Label(cam_delta_frame, text=f"{self.cam_delta_thresh_var.get():.1f}", width=5, anchor='e')
        cam_delta_val_label.pack(side='right', padx=(5,0))
        ttk.Scale(cam_delta_frame, from_=0.0, to=10.0, orient='horizontal', variable=self.cam_delta_thresh_var,
                  command=lambda v: cam_delta_val_label.config(text=f"{float(v):.1f}")).pack(side='right', expand=True, fill='x')
        
        # 終了ボタン
        ttk.Button(param_frame, text="終了", command=self.on_closing).pack(pady=20, anchor='n')

    def toggle_imu_frame(self):
        """IMU利用チェックボックスに応じて、IMU設定フレームの表示を切り替える"""
        if self.use_imu_var.get():
            self.imu_frame.pack(fill='x', padx=5, pady=5, before=self.cam_fusion_frame)
        else:
            self.imu_frame.pack_forget()

    def init_camera(self):
        """Webカメラを初期化する"""
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            messagebox.showerror("エラー", "Webカメラを開けませんでした。")
            self.root.destroy()
            return
        
        cam_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        cam_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.CAM_X_MIN = cam_width * SAFETY_MARGIN_PERCENT
        self.CAM_X_MAX = cam_width * (1 - SAFETY_MARGIN_PERCENT)
        self.CAM_Y_MIN = cam_height * SAFETY_MARGIN_PERCENT
        self.CAM_Y_MAX = cam_height * (1 - SAFETY_MARGIN_PERCENT)
        self.SCREEN_WIDTH, self.SCREEN_HEIGHT = pyautogui.size()

    def init_serial(self):
        """シリアルポートを初期化する"""
        port_to_use = SERIAL_PORT
        if port_to_use.lower() == 'auto':
            port_to_use = find_serial_port()
        
        if port_to_use:
            try:
                self.ser = serial.Serial(port=port_to_use, baudrate=BAUD_RATE, timeout=0.1)
                print(f"✅ IMU接続成功: '{port_to_use}' @ {BAUD_RATE} bps")
                time.sleep(2)
                self.ser.flushInput()
                self.use_imu_check.config(state=tk.NORMAL)
                # ★ 変更点: IMUが接続されても、デフォルトでは有効にしない
                # self.use_imu_var.set(True) # この行を削除
            except serial.SerialException as e:
                print(f"⚠️ 警告: IMUポート '{port_to_use}' を開けません。カメラのみで動作します。\n   {e}")
                self.ser = None
                self.use_imu_check.config(state=tk.DISABLED)
                self.use_imu_var.set(False)
        else:
            print("⚠️ 警告: IMUが見つかりません。カメラのみで動作します。")
            self.use_imu_check.config(state=tk.DISABLED)
            self.use_imu_var.set(False)
        self.toggle_imu_frame()

    def run_flask_app(self):
        """Webサーバーを起動してシリアル通信を中継する"""
        app = Flask(__name__)
        @app.route('/send/<data>')
        def send_data(data):
            if self.ser and self.ser.is_open:
                if data in ['1', '2']:
                    try:
                        self.ser.write(data.encode('utf-8'))
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

    def start_flask_server(self):
        """Flaskサーバーを別スレッドで起動する"""
        flask_thread = Thread(target=self.run_flask_app, daemon=True)
        flask_thread.start()

    def toggle_mouse_control(self, event=None):
        """マウス制御の有効/無効を切り替える"""
        self.mouse_control_active = not self.mouse_control_active
        status = '再開' if self.mouse_control_active else '一時停止'
        print(f"\n[操作] マウス制御を{status}しました。(ESCキーで切り替え)")

    def update(self):
        """メインの更新処理ループ"""
        # --- 1. カメラデータの取得 ---
        ret, frame = self.cap.read()
        if not ret:
            self.root.after(10, self.update)
            return
        frame = cv2.flip(frame, 1)

        # --- 2. IMUデータの取得 ---
        delta_h, delta_p, is_imu_moving = 0.0, 0.0, False
        if self.ser and self.use_imu_var.get() and self.ser.in_waiting > 0:
            try:
                line = self.ser.readline().decode('utf-8', 'ignore').strip()
                if line:
                    parts = line.split(',')
                    if len(parts) == 6: # 元のコードに合わせてインデックス0と2を使用
                        delta_h, delta_p = float(parts[0]), float(parts[2])
                        if abs(delta_h) > self.dead_zone_var.get() or abs(delta_p) > self.dead_zone_var.get():
                            is_imu_moving = True
            except (UnicodeDecodeError, ValueError, IndexError):
                pass
        
        # --- 3. カメラ画像処理 ---
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        (_, maxVal, _, maxLoc) = cv2.minMaxLoc(gray)
        is_cam_tracking = maxVal >= self.bright_thresh_var.get()
        
        camera_screen_x, camera_screen_y = self.last_cam_x, self.last_cam_y
        if is_cam_tracking:
            cam_x_raw, cam_y_raw = maxLoc
            camera_screen_x = np.interp(cam_x_raw, [self.CAM_X_MIN, self.CAM_X_MAX], [0, self.SCREEN_WIDTH - 1])
            camera_screen_y = np.interp(cam_y_raw, [self.CAM_Y_MIN, self.CAM_Y_MAX], [0, self.SCREEN_HEIGHT - 1])

        # --- 4. 状況判断とセンサーフュージョン ---
        status_text, status_color = "", ""
        if self.mouse_control_active:
            # --- センサーフュージョンモード ---
            if self.use_imu_var.get() and self.ser:
                if not is_cam_tracking and is_imu_moving:
                    status_text, status_color = "状態: IMU予測モード", "magenta"
                    self.fused_screen_x += delta_h * self.sens_x_var.get()
                    self.fused_screen_y += delta_p * self.sens_y_var.get()
                    cv2.putText(frame, "IMU PREDICTION", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 255), 2)
                elif is_cam_tracking:
                    cam_delta = np.sqrt((camera_screen_x - self.last_cam_x)**2 + (camera_screen_y - self.last_cam_y)**2)
                    is_cam_moving_slightly = cam_delta > self.cam_delta_thresh_var.get()
                    
                    if not is_imu_moving and is_cam_moving_slightly:
                        status_text, status_color = "状態: ノイズ抑制モード", "orange"
                        alpha = self.alpha_s_var.get()
                        cv2.circle(frame, maxLoc, 20, (0, 165, 255), 2)
                    else:
                        status_text, status_color = "状態: 通常追跡モード", "cyan"
                        alpha = self.alpha_n_var.get()
                        cv2.circle(frame, maxLoc, 20, (255, 255, 0), 2)
                    self.fused_screen_x = (1 - alpha) * self.fused_screen_x + alpha * camera_screen_x
                    self.fused_screen_y = (1 - alpha) * self.fused_screen_y + alpha * camera_screen_y
                else:
                    status_text, status_color = "状態: 追跡対象なし", "red"
            
            # --- カメラ単独モード ---
            else:
                if is_cam_tracking:
                    if self.noise_flag_var.get():
                        status_text, status_color = "状態: 単独ノイズ抑制モード", "orange"
                        alpha = self.alpha_s_var.get()
                    else:
                        status_text, status_color = "状態: カメラ単独モード", "lime"
                        alpha = self.alpha_n_var.get()
                    self.fused_screen_x = (1 - alpha) * self.fused_screen_x + alpha * camera_screen_x
                    self.fused_screen_y = (1 - alpha) * self.fused_screen_y + alpha * camera_screen_y
                    cv2.circle(frame, maxLoc, 20, (0, 255, 0), 2)
                else:
                    status_text, status_color = "状態: 追跡対象なし", "red"
        else:
            status_text, status_color = "状態: 一時停止中 (ESCキーで再開)", "yellow"

        # --- 5. マウス移動 & UI更新 ---
        if self.mouse_control_active:
            final_x = np.clip(self.fused_screen_x, 0, self.SCREEN_WIDTH - 1)
            final_y = np.clip(self.fused_screen_y, 0, self.SCREEN_HEIGHT - 1)
            pyautogui.moveTo(final_x, final_y)

        # UIの更新
        self.status_label.config(text=status_text, foreground=status_color)
        
        # OpenCVの画像をTkinter用に変換
        display_frame = cv2.resize(frame, (640, 480))
        cv2image = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGBA)
        img = Image.fromarray(cv2image)
        imgtk = ImageTk.PhotoImage(image=img)
        self.image_label.imgtk = imgtk
        self.image_label.configure(image=imgtk)
        
        self.last_cam_x, self.last_cam_y = camera_screen_x, camera_screen_y

        # 次のフレームの更新をスケジュール
        self.root.after(10, self.update)

    def on_closing(self):
        """ウィンドウが閉じられる際のクリーンアップ処理"""
        print("\nクリーンアップ処理を実行しています...")
        if hasattr(self, 'cap') and self.cap.isOpened():
            self.cap.release()
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("シリアルポートを閉じました。")
        keyboard.unhook_all()
        self.root.destroy()
        print("終了しました。")

if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.mainloop()