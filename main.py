import os
import discord
from dotenv import load_dotenv
from discord.ext import commands
from flask import Flask
from keep_alive import keep_alive
import json
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, time, timedelta  # datetimeモジュールをインポート
import threading
import asyncio
import json
import sqlite3
import logging
import traceback
import sys
import ast
import random
import re
import subprocess

# Flaskサーバーを起動
# app = Flask(__name__)

# @app.route('/')
# def hello():
#     return 'Hello, World!'

# if __name__ == '__main__':
#     app.run(debug=False)
    #subprocess.Popen(["gunicorn", "-b", "0.0.0.0:8080", "app:app"])

# .envファイルから環境変数を読み込む
load_dotenv()

# Discordボットのトークン
TOKEN = os.getenv("DISCORD_TOKEN")

# ロギングの設定
logging.basicConfig()
logging.getLogger('apscheduler').setLevel(logging.DEBUG)

# スケジューラの設定
scheduler = AsyncIOScheduler()

# sharddata.jsonからデータを読み込む
with open('sharddata.json', 'r', encoding='utf-8') as file:
    sharddata = json.load(file)

# timedata.jsonからデータを読み込む
with open('timedata.json', 'r', encoding='utf-8') as file:
    timedata = json.load(file)
# データベースの初期化
conn = sqlite3.connect('bot_data.db')
c = conn.cursor()
# テーブルが存在しない場合に作成
c.execute('''
    CREATE TABLE IF NOT EXISTS server_settings (
        guild_id INTEGER PRIMARY KEY,
        update_time TEXT,
        notify_options TEXT,
        channel_id INTEGER,
        notify_options_index TEXT
    )
''')
conn.commit()

# キャッシュ用の辞書
guild_settings_cache = {}
#全てのサーバーのデータをDBから読み込む。初期化時に設定をロード
def load_all_guild_settings():
    global guild_settings_cache
    global c  # 追加
    c.execute('SELECT guild_id, update_time, notify_options, channel_id, notify_options_index FROM server_settings')
    rows = c.fetchall()
    for row in rows:
        guild_id, update_time, notify_options, channel_id, notify_options_index = row
        try:
            notify_options = set(json.loads(notify_options))
        except json.JSONDecodeError:
            notify_options = set()
        try:
            notify_options_index = json.loads(notify_options_index)
        except json.JSONDecodeError:
            notify_options_index = []
        guild_settings_cache[guild_id] = {
            'update_time': update_time if update_time is not None else "17:00",
            'notify_options': notify_options,
            'channel_id': channel_id,
            'notify_options_index': notify_options_index
        }
#キャッシュを更新&サーバー設定を保存する関数
def save_server_settings(guild_id, update_time, notify_options, channel_id, notify_options_index):
    global c
    notify_options = json.dumps(list(notify_options)) if notify_options else '[]'
    notify_options_index = json.dumps(notify_options_index) if notify_options_index else '[]'
    c.execute('''
        INSERT OR REPLACE INTO server_settings (guild_id, update_time, notify_options, channel_id, notify_options_index)
        VALUES (?, ?, ?, ?, ?)
    ''', (guild_id, update_time, notify_options, channel_id, notify_options_index))
    conn.commit()
    # キャッシュを更新
    guild_settings_cache[guild_id] = {
        'update_time': update_time,
        'notify_options': notify_options,
        'channel_id': channel_id,
        'notify_options_index': notify_options_index
    }
#キャッシュを利用して、設定を参照
def get_guild_settings(guild_id):
    return guild_settings_cache.get(guild_id, {
        'update_time': "17:00",
        'notify_options': None,
        'channel_id': None,
        'notify_options_index': None
    })

# ボット起動時にすべてのサーバー設定をロード
load_all_guild_settings()
# JSONファイル名
permissions_file = 'permissions.json'

# 権限保持者の一覧を管理するリスト
allowed_user_ids = []
# ボットの所有者のユーザーID（自分のユーザーIDを設定）
bot_owner_id = "651691797814444034"
# JSONファイルから権限保持者の一覧を読み込む関数
def load_permissions():
    global allowed_user_ids,permissions_file
    try:
        with open(permissions_file, 'r', encoding='utf-8') as file:
            try:
                allowed_user_ids = json.load(file)
            except json.JSONDecodeError:
                allowed_user_ids = []
    except FileNotFoundError:
        allowed_user_ids = []

# 権限保持者の一覧をJSONファイルに保存する関数
def save_permissions():
    with open(permissions_file, 'w') as f:
        json.dump(allowed_user_ids, f, indent=4)

# ボット起動時に権限保持者の一覧を読み込む
load_permissions()
#特定のサーバーの設定をデータベースから明示的にリロードしたい場合
def load_server_settings(guild_id):
    global c
    c.execute('SELECT update_time, notify_options, channel_id, notify_options_index FROM server_settings WHERE guild_id = ?', (guild_id,))
    result = c.fetchone()
    if result:
        update_time, notify_options, channel_id, notify_options_index = result
        try:
            notify_options = set(json.loads(notify_options))
        except json.JSONDecodeError:
            notify_options = set()
        try:
            notify_options_index = json.loads(notify_options_index)
        except json.JSONDecodeError:
            notify_options_index = []
        guild_settings_cache[guild_id] = {
            'update_time': update_time,
            'notify_options': notify_options,
            'channel_id': channel_id,
            'notify_options_index': notify_options_index
        }
    else:
        guild_settings_cache[guild_id] = {
            'update_time': "17:00",
            'notify_options': None,
            'channel_id': None,
            'notify_options_index': None
        }
#6時と17時の更新時間に対応するデータを保持するキャッシュ
update_time_cache = {
    '16:00': {
        'is_today_off': False,
        'updated_time1_start': None,
        'updated_time1_end': None,
        'updated_time2_start': None,
        'updated_time2_end': None,
        'updated_time3_start': None,
        'updated_time3_end': None,
        'matching_shard': None,
        'display_data': None
    },
    '17:00': {
        'is_today_off': False,
        'updated_time1_start': None,
        'updated_time1_end': None,
        'updated_time2_start': None,
        'updated_time2_end': None,
        'updated_time3_start': None,
        'updated_time3_end': None,
        'matching_shard': None,
        'display_data': None
    }
}
# 更新時間が16時の場合のデータを設定する関数
def set_data_for_16(data):
    update_time_cache['16:00']['is_today_off'] = data['is_today_off']
    update_time_cache['16:00']['updated_time1_start'] = data['updated_time1_start']
    update_time_cache['16:00']['updated_time1_end'] = data['updated_time1_end']
    update_time_cache['16:00']['updated_time2_start'] = data['updated_time2_start']
    update_time_cache['16:00']['updated_time2_end'] = data['updated_time2_end']
    update_time_cache['16:00']['updated_time3_start'] = data['updated_time3_start']
    update_time_cache['16:00']['updated_time3_end'] = data['updated_time3_end']
    update_time_cache['16:00']['matching_shard'] = data['matching_shard']
    update_time_cache['16:00']['display_data'] = data['display_data']

# 更新時間が17時の場合のデータを設定する関数
def set_data_for_17(data):
    update_time_cache['17:00']['is_today_off'] = data['is_today_off']
    update_time_cache['17:00']['updated_time1_start'] = data['updated_time1_start']
    update_time_cache['17:00']['updated_time1_end'] = data['updated_time1_end']
    update_time_cache['17:00']['updated_time2_start'] = data['updated_time2_start']
    update_time_cache['17:00']['updated_time2_end'] = data['updated_time2_end']
    update_time_cache['17:00']['updated_time3_start'] = data['updated_time3_start']
    update_time_cache['17:00']['updated_time3_end'] = data['updated_time3_end']
    update_time_cache['17:00']['matching_shard'] = data['matching_shard']
    update_time_cache['17:00']['display_data'] = data['display_data']

# 更新時間に応じたデータを取得する関数
def get_data_for_update_time(update_time):
    if update_time in update_time_cache:
        return update_time_cache[update_time]
    else:
        return None
#globa変数
# 色の変換辞書を作成
color_translation = {
    "red": "赤",
    "black": "黒",
}
message_channel_mapping = {}  # グローバルスコープで定義
message_command_mapping = {}  # 追加
# メッセージ内容を格納する変数を定義
message_content = ""
# グローバル変数として設定を保持する
guild_settings = {}
#シャード通知設定の通知条件設定のインデックス0~2が入っている
shard_notify_options_index=[]
guild_semaphore = {}  # サーバーごとのセマフォ管理setup_bot
guild_executing = {}  # 実行中の関数管理setup_bot
emoji_list = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
# 通知オプションの日本語表記
option_labels = {
    "\u30c7\u30a4\u30ea\u30fc\u66f4\u65b0\u6642": "デイリー更新時",
    "\u30b7\u30e3\u30fc\u30c9\u958b\u59cb\u6642\u9593": "シャード開始時間",
    "\u30b7\u30e3\u30fc\u30c9\u7d42\u4e8630\u5206\u524d": "シャード終了30分前"
}
options = ["デイリー更新時", "シャード開始時間", "シャード終了30分前", "決定"]
# ロギングの設定
#logging.basicConfig()
#logging.getLogger('apscheduler').setLevel(logging.DEBUG)
# ルートロガーの設定
logging.basicConfig(level=logging.ERROR)  # ルートロガーのデフォルトレベルをWARNINGに設定

# ロガーの設定
logger = logging.getLogger('discord_bot')
#logger.setLevel(logging.DEBUG) # discord_bot ロガーのログレベルをDEBUGに設定
logger.setLevel(logging.ERROR)

# ハンドラーの設定
handler = logging.StreamHandler()
handler.setLevel(logging.ERROR)# ハンドラーのログレベルをDEBUGに設定

# フォーマッターの設定
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# ハンドラーをロガーに追加
logger.addHandler(handler)


def custom_exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # エラーメッセージを含む詳細なトレースバック情報を取得
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    tb_text = ''.join(tb_lines)

    # トレースバックから行番号と列番号を抽出
    for line in tb_lines:
        if 'File' in line:
            logger.error(f"エラーの詳細: {line.strip()}")
    
    # エラーログを記録
    logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    logger.error(f"トレースバック: \n{tb_text}")

# カスタムエラーハンドラを設定
sys.excepthook = custom_exception_handler

# 非同期のスケジューラを作成
scheduler = AsyncIOScheduler()
#各タイプごとに通知ジョブのIDをリストとして保持
daily_notify_job_ids = {
    'update_time': [],
    'start_time': [],
    'end_30_minutes': [],  
}
# ユーザー名を取得する関数
async def get_username(user_id):
    try:
        user = await client.fetch_user(user_id)
        return user.name  # ユーザーのニックネームを取得
    except discord.errors.NotFound:
        return "未知のユーザー"
# メンションからユーザーIDを抽出する関数
def extract_user_id(mention):
    match = re.match(r'<@!?(\d+)>', mention)
    if match:
        return int(match.group(1))
    return None
# 本日のデータを取得し、16時と17時に毎日データを更新する
async def schedule_update_time_job():
    global scheduler
    await update_data_at_start("16:00")
    await update_data_at_start("17:00")
    try:
        # 16時のジョブをスケジュール
        update_time_obj_16 = datetime.strptime("16:00", "%H:%M")
        job_id_16 = f"update_data_at_start_16"
        scheduler.add_job(update_data_at_start,
                          CronTrigger(hour=update_time_obj_16.hour, 
                                      minute=update_time_obj_16.minute), 
                          id=job_id_16,
                          args=["16:00"])

        # 17時のジョブをスケジュール
        update_time_obj_17 = datetime.strptime("17:00", "%H:%M")
        job_id_17 = f"update_data_at_start_17"
        scheduler.add_job(update_data_at_start,
                          CronTrigger(hour=update_time_obj_17.hour, 
                                      minute=update_time_obj_17.minute), 
                          id=job_id_17,
                          args=["17:00"])

        # ログ出力
        logger.info("データ更新ジョブをスケジュールしました:")
        logger.info(f"  16時の更新ジョブ, ジョブID: {job_id_16}")
        logger.info(f"  17時の更新ジョブ, ジョブID: {job_id_17}")

    except Exception as e:
        logger.info(f"更新ジョブのスケジュール中にエラーが発生しました: {e}")

# 関数定義: データを更新する関数
async def update_data_at_start(update_time):
    #is_today_off   trueなら休み
    global sharddata,timedata,color_translation,update_time_cache
    
    try:
        today_weekday = datetime.now().strftime('%A')
        now = datetime.now()
        today_date = now.strftime('%d')
        current_time = now.strftime("%H:%M")
        is_today_off = False
        matching_shard = None
        display_data = None
        # 実際の処理内容
        logger.info("update_data_at_start 関数を実行中。update_time: %s", update_time)
        # 現在の時刻がupdate_timeより前の場合は前日のデータを表示
        if current_time < update_time:
            # 前日の日付を取得
            yesterday = now - timedelta(days=1)
            today_date = yesterday.strftime('%d')
            today_weekday = yesterday.strftime('%A')  # 前日の曜日を取得
        
        # sharddata.jsonから今日のデータを探す
        for shard in sharddata:
            if shard.get('date') == today_date:
                matching_shard = shard
                #logger.info(f"matching_shard: {matching_shard}")  # デバッグ用のログ出力
                break
        
        # matching_shardが見つかった場合
        if matching_shard:
            # timedata.jsonから該当するタイプのデータを探す
            for time_event in timedata:
                if time_event.get('type') == matching_shard['type']:
                    display_data = time_event
                    #logger.info(f"display_data: {display_data}")  # デバッグ用のログ出力
                    if today_weekday in display_data['days_off']:
                        is_today_off = True
                    else:
                        is_today_off =False
        if display_data:
            # 今日が休みかどうかをチェック
            if is_today_off:
                #await channel.send("休み")
                pass
            else:
                time1_start, time1_end = display_data['time1'].split('~')
                time2_start, time2_end = display_data['time2'].split('~')
                time3_start, time3_end = display_data['time3'].split('~')
                if(update_time=="16:00"):
                # 各時間を1時間前に調整
                    updated_time1_start = (datetime.strptime(time1_start, '%H時%M分') - timedelta(hours=1)).strftime('%H時%M分')
                    updated_time1_end = (datetime.strptime(time1_end, '%H時%M分') - timedelta(hours=1)).strftime('%H時%M分')
                    updated_time2_start = (datetime.strptime(time2_start, '%H時%M分') - timedelta(hours=1)).strftime('%H時%M分')
                    updated_time2_end = (datetime.strptime(time2_end, '%H時%M分') - timedelta(hours=1)).strftime('%H時%M分')
                    updated_time3_start = (datetime.strptime(time3_start, '%H時%M分') - timedelta(hours=1)).strftime('%H時%M分')
                    updated_time3_end = (datetime.strptime(time3_end, '%H時%M分') - timedelta(hours=1)).strftime('%H時%M分')
                else:
                    # update_timeが16時以外の場合、元の時間を使用
                    updated_time1_start, updated_time1_end = time1_start, time1_end
                    updated_time2_start, updated_time2_end = time2_start, time2_end
                    updated_time3_start, updated_time3_end = time3_start, time3_end
                # update_time_cacheにデータを保存
                update_time_cache[update_time] = {
                    'is_today_off': is_today_off,
                    'updated_time1_start': updated_time1_start,
                    'updated_time1_end': updated_time1_end,
                    'updated_time2_start': updated_time2_start,
                    'updated_time2_end': updated_time2_end,
                    'updated_time3_start': updated_time3_start,
                    'updated_time3_end': updated_time3_end,
                    'matching_shard': matching_shard,
                    'display_data': display_data
                }
                return update_time_cache[update_time]
        else:
            # データが見つからない場合
            update_time_cache[update_time] = {
                'is_today_off': False,
                'updated_time1_start': None,
                'updated_time1_end': None,
                'updated_time2_start': None,
                'updated_time2_end': None,
                'updated_time3_start': None,
                'updated_time3_end': None,
                'matching_shard': None,
                'display_data': None
            }
            
            return update_time_cache[update_time]
        
    except Exception as e:
        logger.error(f"update_data_at_start の実行中にエラーが発生しました: {e}")
        update_time_cache[update_time] = {
            'is_today_off': False,
            'updated_time1_start': None,
            'updated_time1_end': None,
            'updated_time2_start': None,
            'updated_time2_end': None,
            'updated_time3_start': None,
            'updated_time3_end': None,
            'matching_shard': None,
            'display_data': None
        }
        return update_time_cache[update_time]
# 関数定義: データの取得とシャード情報の送信
async def send_shard_info(channel_id,guild_id,additional_message=None):
    global guild_settings_cache,color_translation
    # キャッシュからupdate_timeを読み込む
    if guild_id in guild_settings_cache:
        update_time = guild_settings_cache[guild_id]['update_time']
    else:
        # キャッシュに該当guild_idがない場合のデフォルト処理
        update_time = '17:00'
    # データを取得
    data = get_data_for_update_time(update_time)

    # 必要な情報を取り出す
    is_today_off = data['is_today_off']
    matching_shard = data['matching_shard']
    display_data = data['display_data']
    updated_time1_start = data['updated_time1_start']
    updated_time1_end = data['updated_time1_end']
    updated_time2_start = data['updated_time2_start']
    updated_time2_end = data['updated_time2_end']
    updated_time3_start = data['updated_time3_start']
    updated_time3_end = data['updated_time3_end']
    
    # チャンネルを取得
    channel = client.get_channel(channel_id)
    if channel is None:
        logger.info(f"チャンネルID {channel_id} が見つかりません。")
        return
    logger.info("データ出力処理中")
    # display_dataがある場合はメッセージを送信
    if display_data:
        # 今日が休みかどうかをチェック
        if is_today_off:
            await channel.send("休み")
        else:
            color_japanese = color_translation.get(display_data['color'], display_data['color'])
            shard_info = (
                f"Area: {matching_shard['area']}\n"
                f"Location: {matching_shard['location']}\n"
                f"Color: {color_japanese}\n"
                f"Time1: {updated_time1_start}~{updated_time1_end}\n"
                f"Time2: {updated_time2_start}~{updated_time2_end}\n"
                f"Time3: {updated_time3_start}~{updated_time3_end}"
            )
            message = shard_info
            # 追加のメッセージがあれば結合して送信
            if additional_message:
                message = f"{additional_message}\n\n{message}"
            await channel.send(shard_info)
    else:
        await channel.send("データが見つかりませんでした。")
# "0時50分"形式の文字列をdatetime.timeオブジェクトに変換する
async def parse_time(time_str):
    hour, minute = map(int, time_str[:-1].split('時'))
    logger.info
    return datetime.strptime(f'{hour}:{minute}', '%H:%M').time()

# 関数定義: シャード開始時間と更新時間にメッセージを送信する非同期タスク
async def send_message_periodically(ctx):
    global guild_settings_cache,color_translation
    await client.wait_until_ready()
    while not client.is_closed():
        # 現在の日付と時刻を取得
        now = datetime.now()
        current_time = now.time()
        
        # 休みでない場合、指定された時間になったらメッセージを送信
    guild_id = ctx.guild.id
    # キャッシュからupdate_timeを読み込む
    if guild_id in guild_settings_cache:
        update_time = guild_settings_cache[guild_id]['update_time']
    else:
        # キャッシュに該当guild_idがない場合のデフォルト処理
        update_time = '17:00'
    # データを取得
    data = get_data_for_update_time(update_time)

    # 必要な情報を取り出す
    is_today_off = data['is_today_off']
    matching_shard = data['matching_shard']
    display_data = data['display_data']
    updated_time1_start = data['updated_time1_start']
    updated_time1_end = data['updated_time1_end']
    updated_time2_start = data['updated_time2_start']
    updated_time2_end = data['updated_time2_end']
    updated_time3_start = data['updated_time3_start']
    updated_time3_end = data['updated_time3_end']
    
    if not update_time_cache[is_today_off]:
        # display_dataのtime1, time2, time3を取得
        time1 = display_data['time1']
        time2 = display_data['time2']
        time3 = display_data['time3']
        extra_time = time(16, 0)
    
        # 現在の時間がtime1, time2, time3のいずれかに含まれているかをチェックして、その場合にメッセージを送信
        if (current_time == parse_time(time1) or
            current_time == parse_time(time2) or
            current_time == parse_time(time3)or
            current_time == extra_time):
            await send_shard_info(ctx.channel.id,guild_id)
            # タイマーの間隔を設定（30秒ごとにチェック）
    await asyncio.sleep(60)
#更新時間をセットする
async def setup_update_time(ctx):
    # 選択画面のメッセージを送信
    message = await ctx.send("更新時間を選択してください：\n1️⃣ 16:00\n2️⃣ 17:00")
    # メッセージIDとコマンドをマッピング
    message_command_mapping[message.id] = 'setup_update_time'
    # リアクションを追加
    await message.add_reaction('1️⃣')
    await message.add_reaction('2️⃣')
    # リアクションを待機
    def check(reaction, user):
        return user == ctx.author and reaction.message.id == message.id and str(reaction.emoji) in ['1️⃣', '2️⃣']
        
    #logger.info("1")
    try:
        # サーバー設定を読み込む
        for guild in client.guilds:
            settings = get_guild_settings(guild.id)
            update_time = settings['update_time']
            shard_notify_options = settings['notify_options']
            shard_notify_channel_id=settings['channel_id']
            shard_notify_options_index=settings['notify_options_index']
        
        reaction, user = await ctx.bot.wait_for('reaction_add', check=check)
        #logger.info("2")
        # ユーザーが選択したリアクションに応じて処理を行う
        if str(reaction.emoji) == '1️⃣':
            update_time = "16:00"
        elif str(reaction.emoji) == '2️⃣':
            update_time = "17:00"
        #logger.info("3")
        await message.delete()
        # サーバー設定を保存
        save_server_settings(ctx.guild.id, update_time, shard_notify_options,shard_notify_channel_id, shard_notify_options_index)
        await ctx.send(f"更新時間が {update_time} に設定されました！")
        # 通知時間のスケジュール設定
        await schedule_notify_jobs(ctx.guild.id)
        #更新時間を変更
        #logger.info("4")
    except asyncio.TimeoutError:
        await ctx.send("タイムアウトしました。")
#毎日通知するジョブを設定する関数
async def schedule_daily_notify(notify_time, channel_id,guild_id, notify_type,job_function,job_args=()):
    global scheduler, daily_notify_job_ids
    logger.info(f"schedule_daily_notifyが呼ばれました。")
    # 既存のdaily_notify_timeに関するジョブを削除
    job_ids = daily_notify_job_ids.get(notify_type, [])
    for job_id in job_ids:
        # job = scheduler.get_job(job_id)
        # if job:
        #     job.remove()
        # ジョブIDからguild_idを抽出して比較
        parts = job_id.split('_')
        if len(parts) >= 4:  # 最低限のフォーマットの確認
            stored_guild_id = parts[-1]
            if stored_guild_id == guild_id:
                job = scheduler.get_job(job_id)
                if job:
                    job.remove()
    #logger.info("1")
    # 新しい時間でジョブを追加
    try:
        notify_time_obj = datetime.strptime(notify_time, "%H:%M")
        new_job_id = f'{notify_type}_job_{len(job_ids) + 1}_{guild_id}'  # guild_idを含めた新しいジョブIDの作成
        #logger.info("2")
        scheduler.add_job(job_function, CronTrigger(hour=notify_time_obj.hour, minute=notify_time_obj.minute), id=new_job_id, args=job_args)
        #logger.info("2.5")
        # 新しいジョブIDをリストに追加
        daily_notify_job_ids.setdefault(notify_type, []).append(new_job_id)

        #logger.info("3")
        logger.info(f"Scheduled new job: {new_job_id} at {notify_time} for channel {channel_id}")
        # ジョブが追加されたことをログとして出力
        logger.info(f"Added new job:")
        logger.info(f"  Job ID: {new_job_id}")
        logger.info(f"  Notify Time: {notify_time}")
        logger.info(f"  Channel ID: {channel_id}")
        logger.info(f"  Notify Type: {notify_type}")
        logger.info(f"  Guild ID: {guild_id}")  # 追加したGuild IDの出力
        
        #logger.info("4")
    except Exception as e:
        logger.error(f"Error schedule_daily_notifyでエラー発生 {notify_type}: {e}")
#一度だけ通知するジョブを設定する関数
async def schedule_one_time_notify(notify_time, channel_id,guild_id,notify_type,message):
    global scheduler
    try:
        # ジョブIDを設定するためのタイムスタンプを生成
        # ジョブIDを設定するためのタイムスタンプを生成
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_suffix = random.randint(1, 1000)  # 1から1000までのランダムな整数
        job_id = f'one_time_notify_job_{notify_type}_{timestamp}_{random_suffix}_{guild_id}'

        # 新しい時間でジョブを追加
        notify_time_obj = datetime.strptime(notify_time, "%Y-%m-%d %H:%M")
        scheduler.add_job(send_shard_info, 
                        CronTrigger(year=notify_time_obj.year, 
                                    month=notify_time_obj.month, 
                                    day=notify_time_obj.day, 
                                    hour=notify_time_obj.hour, 
                                    minute=notify_time_obj.minute), 
                        id=job_id,
                        args=[channel_id,guild_id,message])
        # ログ出力
        logger.info(f"Scheduled one-time job: {job_id}")
        logger.info(f"  Notify Time: {notify_time}")
        logger.info(f"  Channel ID: {channel_id}")
        logger.info(f"  Guild ID: {guild_id}")

    except Exception as e:
        logger.info(f"Error scheduling one-time job: {e}")
# 権限を持っているかどうかをチェックする関数
def has_permission(user_id):
    global allowed_user_ids,bot_owner_id
    logger.info("has_permissionを呼んだ")
    logger.info(f"user_id:{user_id}")
    logger.info(f"bot_owner_id:{bot_owner_id}")
    if str(user_id) == str(bot_owner_id):
        logger.info("user_id == bot_owner_id")
        return True
    if user_id in allowed_user_ids:
        logger.info("user_id in allowed_user_ids")
        return True
    logger.info("user_idなし")
    return False
# Intentsを設定
intents = discord.Intents.default()
intents.message_content = True  # メッセージコンテンツを取得するために必要
intents.reactions = True  # リアクションイベントを受け取るために必要
# ボットを作成
client = commands.Bot(command_prefix='!',intents=intents)

#ボットの準備ができたときの処理
#サーバーの情報を更新
@client.event
async def on_ready():
    global scheduler,guild_settings_cache
    logger.info(f'{client.user.name} が起動しました')
    #現在のデータに更新して、更新時間に更新するスケジュール
    await schedule_update_time_job()
    # サーバー設定を読み込む
    for guild in client.guilds:
        settings = get_guild_settings(guild.id)
        update_time = settings['update_time']
        shard_notify_options = settings['notify_options']
        shard_notify_channel_id=settings['channel_id']
        shard_notify_options_index=settings['notify_options_index']

        logger.info(f"shard_notify_options_index6:{shard_notify_options_index}")
        if isinstance(shard_notify_channel_id, list):
            # もしshard_notify_channel_idがリストであれば、最初の要素を使用するなど適切な方法で文字列に変換する
            shard_notify_channel_id = shard_notify_channel_id[0]  # 例: 最初の要素を使用する
        if shard_notify_channel_id is not None:
            channel = client.get_channel(shard_notify_channel_id)
            if channel:
                # メッセージの内容を作成
                message_content = (
                    f"更新時間: {update_time}\n"
                    f"通知設定: {', '.join(shard_notify_options) if shard_notify_options else 'なし'}"
                )
                await channel.send(message_content)
                if shard_notify_options_index is not None:
                    await schedule_notify_jobs(guild.id)
                    pass
            else:
                logger.info(f"Channel with ID {shard_notify_channel_id} not found.")
        logger.info(f"shard_notify_options_index7:{shard_notify_options_index}")
    logger.info(guild_settings_cache)
    # スケジューラを開始
    scheduler.start()
    # 例外を発生させるコード
    #raise ValueError("これはテストエラーです")
    logger.info(f"")
# ボットが終了する際に設定を保存する
@client.event
async def on_disconnect():
    logger.info('ボットが終了します')
    # 必要に応じて設定を保存する
# メッセージを受信したときの処理
# コマンドを定義
@client.command(name='ping')
async def ping(ctx):
    await ctx.send('Pong!')

# 予定されているジョブを出力する関数
@client.command(name='show_schedule')
async def print_scheduled_jobs(ctx):
    user_id = ctx.author.id  # コマンドを実行したユーザーのIDを取得
    if has_permission(user_id)==False:
        await ctx.send("権限がありません。")
        return

    jobs = scheduler.get_jobs()
    if jobs:
        logger.info("Scheduled Jobs:")
        for job in jobs:
            job_id = job.id
            job_func = job.func.__name__
            job_args = job.args
            job_kwargs = job.kwargs
            job_trigger = job.trigger
            await ctx.send(f"Job ID: {job_id}, Function: {job_func}, Args: {job_args}, Kwargs: {job_kwargs}, Trigger: {job_trigger}")
        else:
            await ctx.send("No scheduled jobs found.")
# !info コマンドの実装
@client.command(name='info')
async def info_command(ctx):
    # コマンドの説明を定義
    command_info = {
        '!info': '各コマンドの説明画面です',
        '!setup_bot': '更新時間とシャードの通知時間の設定ができます',
        '!show_notify_settings': 'シャードの通知時間の設定を確認できます',
        '!show_update_time': '更新時間の確認ができます',
        '!setup_update_time': '更新時間の変更ができます',
        '!schedule_reset': '全ての通知設定を削除します',
        '!check_today_data': '本日のシャード情報の確認ができます',
        # 他のコマンドを追加する場合はここに追加します
    }
    embed = discord.Embed(
        title='コマンドヘルプ',
        description='このBotがサポートするコマンドとその説明です。',
        color=discord.Color.blue()
    )

    for cmd, description in command_info.items():
        embed.add_field(name=f'**{cmd}**', value=f'{description}', inline=False)

    await ctx.send(embed=embed)
# !debug コマンドの実装
@client.command(name='debug_info')
async def debug_info_command(ctx):
    # コマンドを実行したユーザーのIDを取得
    # user_id = ctx.author.id  
    
    # if has_permission(user_id)==False:
    #     await ctx.send("権限がありません。")
    #     return
        
    # コマンドの説明を定義
    command_info = {
        '!show_schedule': 'デバッグ用：全てのスケジュールを確認可能',
        '!schedule_reset_all': 'デバッグ用：全てのスケジュールを削除',
        '!add_permission': 'デバッグ用：権限付与（オーナーのみ使用可能）',
        '!remove_permission': 'デバッグ用：権限剥奪',
        '!list_permissions': 'デバッグ用：権限保持者一覧',
        # 他のコマンドを追加する場合はここに追加します
    }
    embed = discord.Embed(
        title='コマンドヘルプ',
        description='このBotがサポートするコマンドとその説明です。',
        color=discord.Color.blue()
    )

    for cmd, description in command_info.items():
        embed.add_field(name=f'**{cmd}**', value=f'{description}', inline=False)

    await ctx.send(embed=embed)
# 権限保持者の追加コマンド
@client.command(name='add_permission')
async def add_permission(ctx, mention: str= None):
    global allowed_user_ids,bot_owner_id
    user_id = ctx.author.id  # コマンドを実行したユーザーのIDを取得
    # if not has_permission(user_id):
    #     await ctx.send("権限がありません。")
    #     return
    if str(user_id)!=str(bot_owner_id):
        logger.info(f"user_id :{user_id}:bot_owner_id:{bot_owner_id}")
        await ctx.send("権限がありません。botオーナーのみ実行可能です。")
        return
    if not mention:
        await ctx.send("コマンドのあとに空白を開けてメンションしてください。")
        return
    user_id = extract_user_id(mention)
    if user_id is None:
        await ctx.send("ユーザーIDが指定されていません。")
        return
    if str(user_id) == str(bot_owner_id):
        await ctx.send("ボットの所有者は権限を変更できません。")
        return
    # if str(user_id) in allowed_user_ids:
    #     await ctx.send(f"ユーザー {mention} は権限を持っています。")
    #     return
    if user_id  in allowed_user_ids:
        await ctx.send(f"ユーザー {mention} は権限を持っています。")
        return
    if user_id not in allowed_user_ids:
        allowed_user_ids.append(user_id)
        save_permissions()
        username = await get_username(user_id)
        await ctx.send(f"ユーザー {user_id} : ({username}) の権限を追加しました。")
    else:
        username = await get_username(user_id)
        await ctx.send(f"ユーザー {user_id} : ({username}) は既に権限を持っています。")

# 権限保持者の削除コマンド
@client.command(name='remove_permission')
async def remove_permission(ctx, mention: str= None):
    global allowed_user_ids,bot_owner_id
    user_id = ctx.author.id  # コマンドを実行したユーザーのIDを取得
    if has_permission(user_id)==False:
        await ctx.send("権限がありません。")
        return
    if not mention:
        await ctx.send("コマンドのあとに空白を開けてメンションしてください。")
        return
    user_id = extract_user_id(mention)
    if user_id is None:
        await ctx.send("ユーザーIDが指定されていません。")
        return
    if str(user_id) == str(bot_owner_id):
        await ctx.send("ボットの所有者の権限は削除できません。")
        return
    # if str(user_id) not in allowed_user_ids:
    #     await ctx.send(f"ユーザー {mention} は権限を持っていません。")
    #     return
    if user_id not in allowed_user_ids:
        await ctx.send(f"ユーザー {mention} は権限を持っていません。")
        return
    if user_id in allowed_user_ids:
        allowed_user_ids.remove(user_id)
        save_permissions()
        username = await get_username(user_id)
        await ctx.send(f"ユーザー {user_id} : ({username}) の権限を削除しました。")
    else:
        username = await get_username(user_id)
        await ctx.send(f"ユーザー {user_id} : ({username}) は権限を持っていません。")

# 権限保持者一覧を表示するコマンド
@client.command(name='list_permissions')
async def list_permissions(ctx):
    global allowed_user_ids,bot_owner_id
    # 現在の権限保持者の一覧を表示
    if allowed_user_ids:
        permissions_info = []
        for user_id in allowed_user_ids:
            username = await get_username(user_id)
            permissions_info.append(f"ユーザー : {user_id} : ({username})")
        permissions_list = '\n'.join(permissions_info)
        await ctx.send(f"現在の権限保持者:\n{permissions_list}")
    else:
        await ctx.send("現在、権限保持者はいません。")
# スケジューラをリセットする関数を作成
@client.command(name='schedule_reset')
async def schedule_reset(ctx):
    await remove_jobs_by_guild_id(ctx.guild.id)
    ctx.send("スケジュールを削除しました")
# スケジューラをリセットする関数を作成
@client.command(name='schedule_reset_all')
async def schedule_reset_all(ctx):
    user_id = ctx.author.id  # コマンドを実行したユーザーのIDを取得
    
    if has_permission(user_id)==False:
        await ctx.send("権限がありません。")
        return
    
    await reschedule_all_job(ctx)
#初期設定のコマンド
@client.command(name='setup_bot')
async def setup_bot(ctx):
    global guild_settings_cache,guild_semaphore,guild_executing
    
    guild_id=ctx.guild.id
    
    # セマフォがなければ初期化
    if guild_id not in guild_semaphore:
        guild_semaphore[guild_id] = asyncio.Semaphore(1)
    # 実行中の処理があればキャンセル
    if guild_id in guild_executing and guild_executing[guild_id]:
        await ctx.send("Error: 他の処理が実行中です。しばらくしてから再度お試しください。")
        return
    # 実行中フラグをセット
    guild_executing[guild_id] = True
    
    # キャッシュからupdate_timeを読み込む
    if guild_id in guild_settings_cache:
        update_time = guild_settings_cache[guild_id]['update_time']
    else:
        # キャッシュに該当guild_idがない場合のデフォルト処理
        update_time = '17:00'
    try:
        # ここに初期設定のロジックを追加する
        message_content=(
            "シャード通知botへようこそ\n"
            "\n"
            "こちらは、『sky星を紡ぐ子どもたち』というゲームの『シャード（闇の破片）』というイベントの通知をするbotです。\n"
            "まず、Botの初期設定を行います。\n"
            "次のメッセージで現在の更新時間を設定してください。\n"
        )
        message= await ctx.send(content=message_content)
        await setup_update_time(ctx)
        while update_time is None:
                await asyncio.sleep(1)  # 1秒待機して再試行する
        message_content=(
            "次は、通知する時間を設定してください\n"
            "バグ対策の為、制限時間が設定してあります。タイムアウトした場合『!shard_nofity』のコマンドで再度設定してください。\n"
        )
        await message.edit(content=message_content)
        await shard_notify(ctx)
        # 通知時間のスケジュール設定
        await schedule_notify_jobs(ctx.guild.id)
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
    finally:
        # 実行中フラグをクリア
        guild_executing[guild_id] = False
# 通知時間の設定を確認するコマンドを追加
@client.command(name='show_notify_settings')
async def show_notify_settings(ctx):
    global options


    # コマンドが実行されたギルドを取得
    guild = ctx.guild
    settings = get_guild_settings(guild.id)
    shard_notify_options = settings['notify_options']
    shard_notify_options_index = settings['notify_options_index']
    
    logger.info(f"shard_notify_options_index8:{shard_notify_options_index}")
    
    if shard_notify_options is None or not shard_notify_options:
        await ctx.send("通知時間の設定はまだされていません。")
    else:
        #  f"通知設定: {', '.join(shard_notify_options) if shard_notify_options else 'なし'}"
        #japanese_options = [option_labels.get(option, option) for option in shard_notify_options]
        #options_str = ", ".join(japanese_options)
        if isinstance(shard_notify_options_index, str):
            # 文字列の場合リストとして評価
            shard_notify_options_index = ast.literal_eval(shard_notify_options_index)
            logger.info(f"shard_notify_options_index9:{shard_notify_options_index}")
            #logger.info("shard_notify_options_indexを文字列->リストに変更")
            #logger.info(f"shard_notify_options_index: {', '.join(map(str, shard_notify_options_index))}")
        else:
            if not isinstance(shard_notify_options_index, list):
                shard_notify_options_index = [shard_notify_options_index]
                logger.info(f"shard_notify_options_index10:{shard_notify_options_index}")
                #logger.info("shard_notify_options_indexを？ｰ>リストに変更")
                #logger.info(f"shard_notify_options_index: {', '.join(map(str, shard_notify_options_index))}")
        options = ["デイリー更新時", "シャード開始時間", "シャード終了30分前", "決定"]
        options_str = ", ".join(options[index] for index in shard_notify_options_index if 0 <=index < len(options))
        options_str_op = ", ".join(shard_notify_options)
        logger.info(f"shard_notify_options_index11 : {shard_notify_options_index}")
        logger.info(f"rd_bot:shard_notify_options_index12 : {options_str_op}")
        await ctx.send(f"現在の通知時間の設定: {options_str}")
# 更新時間を確認するコマンド
@client.command(name='show_update_time')
async def show_update_time(ctx):
    global guild_settings_cache
    guild_id=ctx.guild.id
    # キャッシュからupdate_timeを読み込む
    if guild_id in guild_settings_cache:
        update_time = guild_settings_cache[guild_id]['update_time']
    else:
        # キャッシュに該当guild_idがない場合のデフォルト処理
        update_time = '17:00'
    if update_time is None:
        await ctx.send("更新時間は設定されていません。")
    else:
        await ctx.send(f"現在の更新時間は {update_time} です。")
# 更新時間を設定するコマンド
@client.command(name='setup_update_time')
async def setup_time(ctx):
    await setup_update_time(ctx)
#コマンドが呼ばれたら、色、場所、時間、エリア、有無等を送信する
@client.command(name='check_today_data')
async def check_today_data(ctx):
    #channel = ctx.channel  # コンテキストからチャンネルオブジェクトを取得
    await send_shard_info(ctx.channel.id,ctx.guild.id)

# リアクションが追加されたときに実行される処理
@client.event
async def on_reaction_add(reaction, user):
    global message_command_mapping
    # 絵文字オブジェクトを取得
    # ボット自身のリアクションは無視する
    if user.bot:
        return
    # リアクションが追加されたメッセージの ID を取得
    message_id = reaction.message.id
    logger.info(f"リアクション追加: {reaction.emoji}")
    if message_id in message_command_mapping: 
        command = message_command_mapping[message_id] 
        logger.info(f"リアクションコマンド: {command}")
        #チャンネル選択画面の場合
        if command == 'send_channel_selection_message': 
            #logger.info("オプション選択画面のリアクションを処理しています")
            await handle_select_channel_reaction(reaction, user) 
        #オプション選択画面の場合
        elif command == 'send_selection_message': 
            #logger.info(f"on_reaction_add : send_selection_message")
            await handle_select_option_reaction(reaction, user) 
        elif command == 'shard_notify': 
            #logger.info("シャード通知のリアクションを処理しています")
            await handle_shard_notify_reaction(reaction, user) 
        elif command == 'shard_notify_confirmation': 
            #logger.info("シャード通知確認のリアクションを処理しています")
            await handle_shard_notify_confirmation_reaction(reaction, user) 
        elif command == 'setup_update_time':
            #logger.info("更新時間設定のリアクションを処理しています")
            await handle_update_time_reaction(reaction, user)
    else:
        logger.debug(f"メッセージID {message_id} に対応するコマンドが見つかりませんでした。")
#シャード開始時通知のスケジュール追加する関数
async def schedule_shard_start_times(shard_notify_channel_id,notify_type,message):
    logger.info("schedule_shard_end_30_timesが呼ばれました")
    try:
        # クライアントからチャンネルオブジェクトを取得
        channel = await client.fetch_channel(shard_notify_channel_id)
        if not channel:
            logger.error(f"チャンネルID {shard_notify_channel_id} の取得に失敗しました。")
            return
        guild_id = channel.guild.id  # ここでギルドIDを取得
        # ギルド設定を取得
        guild_settings = get_guild_settings(guild_id)
        if not guild_settings:
            logger.error(f"ギルド設定の取得に失敗しました。ギルドID: {guild_id}")
            return
        # ギルド設定から必要な情報を取得
        update_time = guild_settings['update_time']
        
        # データを取得
        data = get_data_for_update_time(update_time)

        # 必要な情報を取り出す
        is_today_off = data['is_today_off']
        updated_times = [
            data.get('updated_time1_start', None),
            data.get('updated_time2_start', None),
            data.get('updated_time3_start', None)
        ]
        if is_today_off:
            return

        current_date = datetime.now().date()  # 現在の日付を取得
        update_time_obj = datetime.strptime(update_time, '%H:%M').time()
        # 実際の処理内容
        logger.info("シャード開始時間の通知ジョブを実行します")
        
         # 時刻を計算して、過去の時間はスケジュールしない
        for time_str in updated_times:
            if not time_str:
                continue
            notify_time = datetime.strptime(time_str, '%H時%M分').replace(year=current_date.year, month=current_date.month, day=current_date.day)
            
            if notify_time.time() >= update_time_obj:
                # 過去の時間でなければスケジュールする
                notify_time = notify_time.strftime('%Y-%m-%d %H:%M')
                await schedule_one_time_notify(notify_time, shard_notify_channel_id,guild_id,notify_type,message)
    
    except Exception as e:
        logger.error(f"シャード開始時間の通知ジョブのスケジュール中にエラーが発生しました: {e}")
#シャード終了30分前通知のスケジュール追加する関数
async def schedule_shard_end_30_times(shard_notify_channel_id,notify_type,message):
    logger.info("schedule_shard_end_30_timesが呼ばれました")
    try:
        # クライアントからチャンネルオブジェクトを取得
        channel = await client.fetch_channel(shard_notify_channel_id)
        if not channel:
            logger.error(f"チャンネルID {shard_notify_channel_id} の取得に失敗しました。")
            return
        # チャンネルオブジェクトからギルドIDを取得
        guild_id = channel.guild.id
        #logger.info("1")
        # ギルド設定を取得
        guild_settings = get_guild_settings(guild_id)
        if not guild_settings:
            logger.error(f"ギルド設定の取得に失敗しました。ギルドID: {guild_id}")
            return
        
        # ギルド設定から必要な情報を取得
        update_time = guild_settings['update_time']
        
        #logger.info("2")
        # データを取得
        data = get_data_for_update_time(update_time)

        # 必要な情報を取り出す
        is_today_off = data['is_today_off']
        updated_times = [
            data.get('updated_time1_end', None),
            data.get('updated_time2_end', None),
            data.get('updated_time3_end', None)
        ]
        
        #logger.info("3")
        #logger.info(f"is_today_off の値: {is_today_off}")  # ログ出力
        
        if  is_today_off:
            return
        
        #logger.info("4")
        current_date = datetime.now().date()  # 現在の日付を取得
        update_time_obj = datetime.strptime(update_time, '%H:%M').time()
        
        #logger.info("5")
        # 実際の処理内容
        logger.info("シャード終了30分前の通知ジョブを実行します")
        
        # 時刻を計算して、過去の時間はスケジュールしない
        for time_str in updated_times:
            if not time_str:
                continue
            
            #logger.info("6")
            notify_time = datetime.strptime(time_str, '%H時%M分').replace(year=current_date.year, month=current_date.month, day=current_date.day)
            notify_time -= timedelta(minutes=30)
            
            if notify_time.time() >= update_time_obj:
                # 過去の時間でなければスケジュールする
                notify_time = notify_time.strftime('%Y-%m-%d %H:%M')
                await schedule_one_time_notify(notify_time, shard_notify_channel_id,guild_id,notify_type,message)
                
                #logger.info("7")
        
        #logger.info("8")
    except Exception as e:
        logger.error(f"シャード終了30分前の通知ジョブのスケジュール中にエラーが発生しました: {e}")
#全てのスケジュールをリセット
async def reschedule_all_job(ctx):
    global scheduler
    # 既存のジョブを削除
    scheduler.remove_all_jobs()
    #更新時間に更新する関数追加
    await schedule_update_time_job()
    await ctx.send("通知設定をリセットしました")
# リアクション削除用の関数
async def handle_select_channel_reaction(reaction, user):
    await remove_user_reaction(reaction, user)
async def handle_select_option_reaction(reaction, user):
    pass
    # logger.info(f"handle_select_option_reaction")
    # try:
    #     # メッセージのすべてのリアクションを取得
    #     message = reaction.message
    #     all_reactions = message.reactions
        
    #     # ユーザーの「4️⃣」のリアクションが現れるまで待機
    #     while not any(str(reaction.emoji) == "4️⃣" for reaction in all_reactions):
    #         await asyncio.sleep(1)  # 1秒待機して再試行
    #         # メッセージのリアクションを更新
    #         message = message.channel.fetch_message(message.id)
    #         all_reactions = message.reactions
        
    #     await remove_user_reaction(reaction, user)

    #     # コマンドを設定
    #     message_command_mapping[reaction.message.id] = 'shard_notify'
    #     logger.info(f"message_command_mapping3 : {message_command_mapping[reaction.message.id]}")
        
    # except asyncio.TimeoutError:
    #     logger.info("タイムアウトしました。")
    # except Exception as e:
    #     logger.info(f"エラーが発生しました: {e}")      
async def handle_shard_notify_reaction(reaction, user):
    pass
async def handle_shard_notify_confirmation_reaction(reaction, user):
    pass
async def handle_update_time_reaction(reaction, user):
    pass
#シャードの通知を設定する関数
async def shard_notify(ctx):
    async def setup_shard_notification():
        global message_command_mapping, guild_settings_cache
        shard_notify_options=None
        shard_notify_channel_id=None
        shard_notify_options_index=None
        all_emojis =[ "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟","⬅️","➡️"]
        options = ["デイリー更新時", "シャード開始時間", "シャード終了30分前", "決定"]
        #キャッシュからupdate_timeを読み込む
        if ctx.guild.id in guild_settings_cache:
            update_time = guild_settings_cache[ctx.guild.id]['update_time']
        else:
        # キャッシュに該当guild_idがない場合のデフォルト処理
            update_time = '17:00'
        
        # 選択画面のメッセージを作成
        #select_message = await ctx.send("Now Loading")
        #message_command_mapping[select_message.id] = 'shard_notify'
        #logger.info(f"message_command_mapping1 : {message_command_mapping[select_message.id]}")
        
        # send_channel_selection_messageでチャンネルを選択
        shard_notify_channel_id = await send_channel_selection_message(ctx)
        if not shard_notify_channel_id:
            await ctx.send("タイムアウトしました。")
            return
        
        #shard_notify_channnel_idが入る
        #logger.info(f"shard_notify_channnel_id: {shard_notify_channel_id}")
        #logger.info(f"message_command_mapping2 : {message_command_mapping[select_message.id]}")
        
        #すべてのリアクション削除
        emojis =[ "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟","⬅️","➡️"]
        #emojisの絵文字リアクションから削除する
        #await remove_bot_reactions(select_message, emojis)
        
        shard_notify_options_index, shard_notify_options = await send_selection_message(ctx)
        if not shard_notify_options_index or not shard_notify_options:
            await ctx.send("タイムアウトしました。")
            return
        logger.info(f"shard_notify_options_index1:{shard_notify_options_index}")
        #両方入力された場合
        if shard_notify_channel_id and shard_notify_options_index is not None and shard_notify_options:
            emojis =[ "1️⃣", "2️⃣", "3️⃣", "4️⃣"]
            #emojisのbotの絵文字リアクションから削除する
            #await remove_bot_reactions(select_message, emojis)
            # 選択されたチャンネルを取得
            channel = client.get_channel(shard_notify_channel_id)
            # shard_notify_optionsのすべての要素を文字列として結合して出力
            options_str = ", ".join(shard_notify_options)
            # 確認画面の内容を構築
            confirmation_message = (
                f"以下の設定でシャード通知を行います。\n"
                f"更新時間：{update_time}\n"
                f"チャンネル：{channel.name}\n"
                f"設定：{options_str}\n"
                f"以上の設定でよろしいですか？"
            )
            # 確認画面を送信
            select_message=await ctx.send(content=confirmation_message)
            message_command_mapping[select_message.id] = 'shard_notify_confirmation'
            #logger.info(f"message_command_mapping10 : {message_command_mapping[select_message.id]}")
            # YとNのリアクションを追加
            await select_message.add_reaction('🇾')  # Y
            await select_message.add_reaction('🇳')  # N
            
            def check(reaction, user):
                return user == ctx.author and reaction.message.id == select_message.id and str(reaction.emoji) in ['🇾', '🇳']
            try:
                reaction, _ = await client.wait_for('reaction_add', check=check)
                if str(reaction.emoji) == '🇾':  # Yを選択した場合
                    # 保存処理
                    shard_option_list=list(shard_notify_options)
                    save_server_settings(ctx.guild.id, update_time, shard_option_list,shard_notify_channel_id,shard_notify_options_index)
                    # 確認メッセージを送信
                    confirmation_message = (
                        f"シャード通知が実行されます。\n"
                        f"チャンネル：{channel.name}\n"
                        f"設定：{options_str}\n"
                    )
                    await ctx.send(content=confirmation_message)
                    await select_message.delete()
                    # ユーザーがYを選択した場合の処理をここに記述
                else:  # Nを選択した場合
                    await select_message.delete()
                    await ctx.send("シャード通知の設定をキャンセルしました。")
                    #setup_botの関数の実行をキャンセルする
                    return
            except asyncio.TimeoutError:
                await ctx.send("タイムアウトしました。")
                return
        return
    try:
        await asyncio.wait_for(setup_shard_notification(), timeout=600)
    except asyncio.TimeoutError:
        await ctx.send("タイムアウトしました。")
        return
        # タイムアウト時の処理を行います
    except Exception as e:
        await ctx.send(f"エラーが発生しました: {str(e)}")
        # その他のエラー処理を行います
    return
#ギルドIDが一致する全てのスケジュールを削除する
async def remove_jobs_by_guild_id(guild_id):
    global scheduler
    """
    スケジューラーから特定のギルドIDに関連付けられたすべてのジョブを削除します。

    パラメータ:
    - scheduler (apscheduler.schedulers.background.BackgroundScheduler): APScheduler のインスタンスです。
    - guild_id (int または str): 削除したいジョブのギルドIDです。

    返り値:
    - None
    """
    jobs = scheduler.get_jobs()
    for job in jobs:
        job_guild_id = job.id.split('_')[-1]  # ジョブIDの最後の部分にギルドIDが含まれていると仮定
        if job_guild_id == str(guild_id):
            scheduler.remove_job(job.id)

#通知時間のスケジュール設定部分
async def schedule_notify_jobs(guild_id):
    global scheduler, guild_settings_cache
    # サーバー設定を読み込む
    # キャッシュからギルド設定を取得
    logger.info("schedule_notify_jobsが呼ばれました")
    settings = get_guild_settings(guild_id)
    if not settings:
        logger.warning(f"ギルド設定が見つかりません。ギルドID: {guild_id}")
        return

    update_time = settings['update_time']
    shard_notify_options_index = settings['notify_options_index']
    shard_notify_channel_id = settings['channel_id']
    
    logger.info("スケジュールの通知ジョブを設定します")
    logger.info("schedule_notify_jobs 開始")
    logger.info(f"update_time: {update_time}")
    logger.info(f"shard_notify_options_index2: {shard_notify_options_index}")
    logger.info(f"shard_notify_channel_id: {shard_notify_channel_id}")

    # 既存のジョブを削除
    jobs = scheduler.get_jobs()
    for job in jobs:
        job_guild_id = job.id.split('_')[-1]  # ジョブIDの最後の部分にギルドIDが含まれていると仮定
        if job_guild_id == str(guild_id):
            scheduler.remove_job(job.id)

    
    # 通知時間のスケジュール設定
    if shard_notify_options_index is None:
        logger.warning("shard_notify_options_index が None です。何もスケジュールされません。")
        return
    if isinstance(shard_notify_options_index, str):
        # 文字列の場合リストとして評価
        shard_notify_options_index = ast.literal_eval(shard_notify_options_index)
        logger.info("shard_notify_options_indexを文字列->リストに変更")
        logger.info(f"shard_notify_options_index3: {', '.join(map(str, shard_notify_options_index))}")
    else:
        if not isinstance(shard_notify_options_index, list):
            shard_notify_options_index = [shard_notify_options_index]
            logger.info("shard_notify_options_indexを？ｰ>リストに変更")
            logger.info(f"shard_notify_options_index4: {', '.join(map(str, shard_notify_options_index))}")
    for option_index in shard_notify_options_index:
        try:
            logger.info(f"shard_notify_options_index5: {shard_notify_options_index}")
            logger.info(f"option_index: {option_index}")
            
            if option_index == 0:  # デイリー更新時
                logger.info("デイリー更新時の通知ジョブをスケジュールします")
                message="デイリー更新時間です。\n今日のシャード情報"
                job_args = (shard_notify_channel_id,guild_id,message)
                await schedule_daily_notify(update_time, shard_notify_channel_id,guild_id, 'update_time', send_shard_info, job_args)

            elif option_index == 1:  # シャード開始時間
                logger.info("シャード開始時間の通知ジョブをスケジュールします")
                # job_args に渡す引数をタプルで定義
                message="シャード開始時間です。\n今日のシャード情報"
                job_args = (shard_notify_channel_id,'start_time',message)
                if isinstance(shard_notify_channel_id, list):
                    # もしshard_notify_channel_idがリストであれば、最初の要素を使用するなど適切な方法で文字列に変換する
                    shard_notify_channel_id = shard_notify_channel_id[0]  # 例: 最初の要素を使用する
                # schedule_daily_notify を使ってジョブをスケジュール
                print("1")
                await schedule_daily_notify(update_time, shard_notify_channel_id,guild_id, 'start_time', schedule_shard_start_times, job_args)
                print("2")
                await schedule_shard_start_times(shard_notify_channel_id,'start_time',message)
                print("3")

            elif option_index == 2:  # シャード終了30分前
                logger.info("シャード終了30分前の通知ジョブをスケジュールします")
                # job_args に渡す引数をタプルで定義
                message="シャード終了時間30分前です。\n今日のシャード情報"
                job_args = (shard_notify_channel_id,"end_30_minutes",message)
                # schedule_daily_notify を使ってジョブをスケジュール
                print("4")
                await schedule_daily_notify(update_time, shard_notify_channel_id,guild_id, 'end_30_minutes', schedule_shard_end_30_times, job_args)
                print("5")
                await schedule_shard_end_30_times(shard_notify_channel_id,"end_30_minutes",message)
                print("6")
            else:
                pass
        except Exception as e:
            logger.error(f"オプションインデックス {option_index} のジョブのスケジュール中にエラーが発生しました: {e}")

# 他の関数の中で呼び出され、選択肢を送信し、ユーザーの選択を待機する処理
async def send_selection_message(ctx):
    global emoji_list
    logger.info("send_selection_messageが呼ばれました")
    shard_notify_options_index = []  # リストとして初期化する
    # 選択肢のリスト
    options = ["デイリー更新時", "シャード開始時間", "シャード終了30分前", "決定"]
    # 選択肢を含むメッセージの作成
    message_content = (
        "通知する時間をすべて選択してください：\n"
        "選択し終わったら、決定のリアクションを押してください：\n"
    )
    for index, option in enumerate(options):
        message_content += f"{emoji_list[index]}{option}\n"

    # メッセージを編集
    message=await ctx.send(content=message_content)
    message_command_mapping[message.id] = 'send_selection_message'
    #logger.info(f"message_command_mapping5 : {message_command_mapping[message.id]}")
    # メッセージから指定されたリストに含まれないボットが追加したリアクションをすべて削除する
    await remove_non_listed_bot_reactions(message)
    # 絵文字のリアクションを追加
    for emoji in emoji_list[:len(options)]:
        # メッセージに絵文字が存在しない場合のみリアクションを追加
        if not any(reaction.emoji == emoji for reaction in message.reactions):
            await message.add_reaction(emoji)
    # 選択されたオプションを追跡するためのセット
    selected_options = set()
    # ユーザーのリアクションを待機
    def check(reaction, user):
        return user == ctx.author and reaction.message.id == message.id and str(reaction.emoji) in emoji_list[:len(options)]

    try:
        while True:
            reaction, user = await client.wait_for('reaction_add', check=check)
            
            # ユーザーの選択を取得
            selected_option_index = emoji_list.index(str(reaction.emoji))
            selected_option = options[selected_option_index]

            # 「決定」が選択された場合
            if selected_option == "決定":
                if selected_options:
                    shard_notify_options=selected_options
                    # すべてのリアクションを削除
                    #await message.clear_reactions()
                    #メッセージ削除
                    message.delete()
                    return shard_notify_options_index, selected_options
                else:
                    return None, None
            else:
                if selected_option in selected_options:
                    selected_options.remove(selected_option)
                    shard_notify_options_index.remove(selected_option_index)  
                else:
                    selected_options.add(selected_option)
                    shard_notify_options_index.append(selected_option_index)  # リストにインデックスを追加
    except asyncio.TimeoutError:
        await ctx.send("タイムアウトしました。")
        return None, None
#ボットが追加したリアクションをすべて削除する
async def remove_non_listed_bot_reactions(message):
    for reaction in message.reactions:
        async for user in reaction.users():
            await reaction.remove(user)
# 他の関数の中で呼び出され、指定されたページのチャンネルリストを表示する処理
async def send_channel_selection_message(ctx):
    global message_channel_mapping 
    global message_content
    global emoji_list
    logger.info("send_channel_selection_messageが呼ばれました")
    
    # サーバー内の全てのテキストチャンネルを取得
    channels = [channel for channel in ctx.guild.channels if isinstance(channel, discord.TextChannel)]
    # チャンネルのリストからIDを取得してchannels_IDに追加
    channels_ID = [channel.id for channel in channels]
    # ページごとにチャンネルを分割
    chunk_size = 10
    channel_chunks = [channels[i:i+chunk_size] for i in range(0, len(channels), chunk_size)]
    
    # ページ数を取得
    num_pages = len(channel_chunks)
    # 現在のページ番号を初期化
    current_page = 0
    
    # メッセージ内容の構築
    emoji_list = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    message_content = f"**Page {current_page + 1}/{num_pages}**\n\n"
    message_content += "通知を送信するチャンネルを選択するページです。\n"
    message_content += "以下のチャンネルから、更新時間を通知するチャンネルを選択し、そのリアクションを付けてください。\n\n"
    message_content += "右矢印のリアクションで次のページ、左矢印のリアクションで前のページを参照できます。\n\n"
    
    # チャンネルリストを表示
    for index, channel in enumerate(channel_chunks[current_page]):
        if index < len(emoji_list):
            message_content += f"{emoji_list[index]} {channel.name}\n"
    
    # メッセージを送信または編集
    #if message is None:
    message = await ctx.send(message_content)
    message_command_mapping[message.id] = 'send_channel_selection_message'
    #logger.info(f"message_command_mapping6 : {message_command_mapping[message.id]}")
    # else:
    #     await message.edit(content=message_content)
    #     message_command_mapping[message.id] = 'send_channel_selection_message'
    #     logger.info(f"message_command_mapping6 : {message_command_mapping[message.id]}")
    
    # リアクションを追加
    for emoji in emoji_list[:min(len(channel_chunks[current_page]), len(emoji_list))]:
        await message.add_reaction(emoji)
    #ページが最初のページでない場合は、前のページへのリアクションを追加
    if current_page > 0:
        await message.add_reaction('⬅️')
    #ページが最後のページでない場合は、次のページへのリアクションを追加
    if current_page < num_pages - 1:
        await message.add_reaction('➡️')

    # メッセージとページのマッピングを保存
    message_channel_mapping[message.id] = current_page
    message_command_mapping[message.id] = 'send_channel_selection_message'
    #logger.info(f"message_command_mapping7 : {message_command_mapping[message.id]}")
    
    while True:
        try:
            # ユーザーのリアクションを待機
            reaction, user = await ctx.bot.wait_for('reaction_add', check=lambda r, u: u == ctx.author and r.message.id == message.id and str(r.emoji) in emoji_list + ['⬅️', '➡️'])

            
        except asyncio.TimeoutError:
            await ctx.send("タイムアウトしました。もう一度やり直してください。")
            break

        # ページを変更
        if str(reaction.emoji) == '⬅️' and current_page > 0:
            current_page -= 1
        elif str(reaction.emoji) == '➡️' and current_page < num_pages - 1:
            current_page += 1
        elif str(reaction.emoji) in emoji_list:
            index = emoji_list.index(str(reaction.emoji))
            channel_index = current_page * chunk_size + index
            if channel_index < len(channels):
                message.delete()
                selected_channel = channels[channel_index]
                shard_notify_channel_id = channels_ID[channel_index]
                logger.info(f"{selected_channel.name} チャンネルが選択されました。")
                logger.info(f"on_selected_channel_id : {shard_notify_channel_id}")
                await ctx.send(f"チャンネル `{selected_channel.name}` が選択されました。")
                return shard_notify_channel_id
        await update_message(current_page, message, channel_chunks, emoji_list)
    return None
# ページを更新する関数
async def update_message(page, message, channel_chunks, emoji_list):
    message_content = f"**Page {page + 1}/{len(channel_chunks)}**\n\n"
    message_content += "こちらは、通知を送信するチャンネルを選択するページです。\n"
    message_content += "以下のチャンネルから、更新時間を通知するチャンネルを選択し、そのリアクションを付けてください。\n\n"
    message_content += "右矢印のリアクションで次のページ、左矢印のリアクションで前のページを参照できます。\n\n"
    for index, channel in enumerate(channel_chunks[page]):
        message_content += f"{emoji_list[index]} {channel.name}\n"
        
    await message.edit(content=message_content)
    message_command_mapping[message.id] = 'send_channel_selection_message'
    # 左向きの矢印リアクションを追加
    if page > 0:
        if '⬅️' not in [reaction.emoji for reaction in message.reactions]:
            await message.add_reaction('⬅️')
            #logger.info("左追加")
    else:
        # ページが最初の場合は左向きの矢印リアクションを削除
        await message.clear_reaction('⬅️')
        #logger.info("左削除")
    # 右向きの矢印リアクションを追加
    if page < len(channel_chunks) - 1:
        if '➡️' not in [reaction.emoji for reaction in message.reactions]:
            await message.add_reaction('➡️')
            #logger.info("右追加")
    else:
        # ページが最後の場合は右向きの矢印リアクションを削除
        await message.clear_reaction('➡️')
        #logger.info("右削除")
# メッセージのbotの絵文字のリアクションを削除
async def remove_bot_reactions(message, emojis):
    try:
        # メッセージから指定された絵文字のリアクションを削除
        for emoji in emojis:
            await message.remove_reaction(emoji, message.guild.me)
    except discord.NotFound:
        # メッセージまたはリアクションが見つからない場合の処理
        pass
    except discord.Forbidden:
        # ボットがリアクションを削除する権限がない場合の処理
        pass
    except discord.HTTPException:
        # リクエストが失敗した場合の処理
        pass
# メッセージのユーザーの絵文字のリアクションを削除
async def remove_user_reaction(reaction, user):
    async for user_in_reaction in reaction.users():
        if user_in_reaction == user:
            await reaction.remove(user_in_reaction)
# shard_notifyコマンドのリアクション処理
# ボットを実行
# デフォルトのコマンド処理を呼び出す
keep_alive()
try:
    client.run(os.environ['TOKEN'])
except:
    os.system("kill")

# イベントループを開始
async def main():
    while True:
        await asyncio.sleep(10)  # スケジューラがバックグラウンドで実行されるようにする
# 非同期処理を開始
asyncio.run(main())