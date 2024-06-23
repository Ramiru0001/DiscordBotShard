FROM python:3.12.4

# 以下はKoyebで運用する際に必要
# ポート番号8080解放

EXPOSE 8000

WORKDIR /app
# ローカルのすべてのファイルをコンテナの/appにコピー
COPY . .
# 必要なPythonパッケージをインストール
RUN pip install -r requirements.txt

# CMD ["gunicorn", "-b", "0.0.0.0:8000", "main:app"]

# Flaskを使用しない場合、代わりにコマンドを指定する（例：Pythonスクリプトを直接実行する）
CMD ["python", "main.py"]
