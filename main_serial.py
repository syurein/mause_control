import serial
from flask import Flask

# --- 設定項目 ---
# ご自身の環境に合わせて変更してください
#SERIAL_PORT = '/dev/tty.usbmodem14201'  # Macの場合の例
SERIAL_PORT = 'COM10'                  # Windowsの場合の例
# SERIAL_PORT = '/dev/ttyUSB0'          # Linuxの場合の例
BAUD_RATE = 9600
# ---------------

# Flaskアプリケーションの初期化
app = Flask(__name__)

# シリアルポートを開く
try:
    ser = serial.Serial(port=SERIAL_PORT, baudrate=BAUD_RATE, parity= 'N')
    print(f"✅ シリアルポート {SERIAL_PORT} を {BAUD_RATE} bps で開きました。")
except serial.SerialException as e:
    print(f"❌ エラー: シリアルポート {SERIAL_PORT} を開けませんでした。")
    print(e)
    # ポートが開けない場合はプログラムを終了する
    exit()

# http://<IPアドレス>:5000/send/1 や /send/2 にアクセスされたときの処理
@app.route('/send/<data>')
def send_data(data):
    """URLに応じてシリアルポートにデータを送信する"""
    if data == '1' or data == '2':
        try:
            # '1' または '2' をバイトデータに変換して送信
            ser.write(data.encode('utf-8'))
            print(f"📨 デバイスに '{data}' を送信しました。")
            return f"<h1>'{data}' を送信しました</h1>"
        except serial.SerialException as e:
            print(f"❌ エラー: データの送信に失敗しました。: {e}")
            return f"<h1>送信エラー</h1><p>{e}</p>", 500
    else:
        # '1' '2' 以外が指定された場合はエラーメッセージを返す
        print(f"🤔 無効なデータ '{data}' がリクエストされました。")
        return "<h1>無効なリクエストです</h1><p>'/send/1' または '/send/2' にアクセスしてください。</p>", 400

# メインの処理
if __name__ == '__main__':
    # 外部のコンピューターからもアクセスできるように host='0.0.0.0' を指定
    app.run(host='0.0.0.0', port=5000, debug=True,use_reloader=False)