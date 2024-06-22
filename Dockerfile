FROM python:3.12.4

WORKDIR /app

COPY . .

RUN pip install -r requirements.txt

# CMD ["gunicorn", "-b", "0.0.0.0:8000", "main:app"]

# Flaskを使用しない場合、代わりにコマンドを指定する（例：Pythonスクリプトを直接実行する）
CMD ["python", "main.py"]
