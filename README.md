### 共通セットアップ
このコードはゲームコントローラーを動かすためのコードである。
```code
python -m venv venv
venv/Scripts/activate
pip install -r requirements.txt
```

### Tkinter
もしTkinterを実行する場合は下記を実行してください

```code 
python app2.py
```



### PysimpleGUI
もし  pysimpleGUI  で実行するばあいは、下記のコードをすべてが終わった後に実行してください

```code
python -m pip uninstall PySimpleGUI
python -m pip cache purge
 python -m pip install --upgrade --extra-index-url https://PySimpleGUI.net/install PySimpleGUI
 python app.py
 ```


### テスト用ゲーム

```code 
python test_game.py
```