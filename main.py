import os
import discord
from dotenv import load_dotenv
from discord.ext import commands
from flask import Flask
from keep_alive import keep_alive

app = Flask(__name__)

@app.route('/')
def hello():
    return 'Hello, World!'

if __name__ == '__main__':
    app.run()

# .envファイルから環境変数を読み込む
load_dotenv()

# Discordボットのトークン
TOKEN = os.getenv("DISCORD_TOKEN")
# Intentsを設定
intents = discord.Intents.default()
intents.message_content = True  # メッセージコンテンツを取得するために必要
# ボットを作成
client = commands.Bot(command_prefix='!',intents=intents)

#s ボットの準備ができたときの処理
@client.event
async def on_ready():
    print(f'{client.user.name} has connected to Discord!')

# メッセージを受信したときの処理
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith('!ping'):
        await message.channel.send('Pong!')

# ボットを実行

keep_alive()
try:
    client.run(os.environ['TOKEN'])
except:
    os.system("kill")