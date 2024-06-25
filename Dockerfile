FROM python:3.12.4

# 以下はKoyebで運用する際に必要


WORKDIR /app


# ローカルのすべてのファイルをコンテナの/botにコピー
COPY . /bot
# 必要なPythonパッケージをインストール
RUN pip install -r requirements.txt

# CMD ["gunicorn", "-b", "0.0.0.0:8000", "main:app"]

# ポート番号8080解放
EXPOSE 8000
# Flaskを使用しない場合、代わりにコマンドを指定する（例：Pythonスクリプトを直接実行する）
# DiscordBotとFastAPIのサーバ起動
CMD [ "python", "-u", "main.py" ]
