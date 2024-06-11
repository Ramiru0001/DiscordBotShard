import os
import discord
from dotenv import load_dotenv
from discord.ext import commands
from flask import Flask
from keep_alive import keep_alive
import json
from datetime import datetime, time, timedelta  # datetimeモジュールをインポート
import threading
import asyncio

# Flaskサーバーを起動
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

# sharddata.jsonからデータを読み込む
with open('sharddata.json', 'r', encoding='utf-8') as file:
    sharddata = json.load(file)

# timedata.jsonからデータを読み込む
with open('timedata.json', 'r', encoding='utf-8') as file:
    timedata = json.load(file)

# 色の変換辞書を作成
color_translation = {
    "red": "赤",
    "black": "黒",
}
matching_shard = None
display_data = None
today_weekday = None
is_today_off = False
message_channel_mapping = {}  # グローバルスコープで定義
message_command_mapping = {}  # 追加
# メッセージ内容を格納する変数を定義
message_content = ""
# ページごとのチャンネルリストを保存する辞書
page_channels = {}
num_pages=None
chunk_size=None
channels=None
channels_ID=None
channel_chunks=None
send_selection_message_now=False
send_channel_selection_message_now=False
#シャード通知設定コマンドを使用中ならtrue
shard_notify_flag=False
#シャード通知設定で使用するID
shard_notify_channnel_id=None
#シャード通知設定の通知条件設定のインデックス0~2が入っている
shard_notify_options_index=None
shard_notify_options=None
emoji_list = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
# 関数定義: データを更新する関数
async def update_data_at_start():
    #is_today_off   trueなら休み
    global matching_shard, display_data,today_weekday
    global is_today_off,sharddata,timedata,color_translation

    today_weekday = datetime.now().strftime('%A')
    now = datetime.now()
    today_date = now.strftime('%d')
    current_time = now.time()
    is_today_off = False
    matching_shard = None
    display_data = None
    # デバッグ用のログ出力
    print("データ更新")
    # 現在の時刻が16時より前の場合は前日のデータを表示
    if current_time < time(16, 0):
        # 前日の日付を取得
        yesterday = now - timedelta(days=1)
        today_date = yesterday.strftime('%d')
        today_weekday = yesterday.strftime('%A')  # 前日の曜日を取得
    
    # sharddata.jsonから今日のデータを探す
    for shard in sharddata:
        #print(f"shard.get'date': {shard.get('date')}")
        #print(f"today_date': {today_date}")
        if shard.get('date') == today_date:
            matching_shard = shard
            #print(f"matching_shard: {matching_shard}")  # デバッグ用のログ出力
            break
    
    # matching_shardが見つかった場合
    if matching_shard:
        # timedata.jsonから該当するタイプのデータを探す
        for time_event in timedata:
            if time_event.get('type') == matching_shard['type']:
                display_data = time_event
                #print(f"display_data: {display_data}")  # デバッグ用のログ出力
                if today_weekday in display_data['days_off']:
                    is_today_off = True
                break
    #else:
        #print("update_matching_shardなし")

# 関数定義: データ更新とシャード情報の送信
async def send_shard_info(ctx):
    # データを更新
    await update_data_at_start()  
    global matching_shard, display_data,today_weekday
    global is_today_off,sharddata,timedata,color_translation
    print("データ出力処理中")
    # display_dataがある場合はメッセージを送信
    if display_data:
        # 今日が休みかどうかをチェック
        if is_today_off:
            await ctx.send("休み")
        else:
            color_japanese = color_translation.get(display_data['color'], display_data['color'])
            shard_info = (
                f"Area: {matching_shard['area']}\n"
                f"Location: {matching_shard['location']}\n"
                f"Color: {color_japanese}\n"
                f"Time1: {display_data['time1']}\n"
                f"Time2: {display_data['time2']}\n"
                f"Time3: {display_data['time3']}"
            )
            await ctx.send(shard_info)
    else:
        await ctx.send("データが見つかりませんでした。")
# 関数定義: 16時にデータを更新する関数
async def update_data_at_16():

    global matching_shard, display_data
    
    now = datetime.now()
    current_time = now.time()
    
    # 16時になったらデータを更新
    if current_time == time(16, 0):
        await update_data_at_start()
def parse_time(time_str):
    # "0時50分"形式の文字列をdatetime.timeオブジェクトに変換する
    hour, minute = map(int, time_str[:-1].split('時'))
    print
    return datetime.strptime(f'{hour}:{minute}', '%H:%M').time()

# 関数定義: シャード開始時間と更新時間にメッセージを送信する非同期タスク
async def send_message_periodically(ctx):
    await client.wait_until_ready()
    while not client.is_closed():
        # 現在の日付と時刻を取得
        now = datetime.now()
        current_time = now.time()
        
        # 休みでない場合、指定された時間になったらメッセージを送信
    if not is_today_off:
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
            await send_shard_info(ctx.channel)
            # タイマーの間隔を設定（30秒ごとにチェック）
    await asyncio.sleep(60)

# チェックメッセージを送信する関数
async def send_check_today_data():
    # メッセージを送信するチャンネルを取得
    channel = client.get_channel(channnel_id)  # 送信先のチャンネルIDを指定する
    # メッセージを送信
    await channel.send("!check_today_data")  # 送信するメッセージを指定する

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
    print(f'{client.user.name} が起動しました')
    await update_data_at_start()
# メッセージを受信したときの処理
# コマンドを定義
@client.command(name='ping')
async def ping(ctx):
    await ctx.send('Pong!')

#コマンドが呼ばれたら、色、場所、時間、エリア、有無等を送信する
@client.command(name='check_today_data')
async def check_today_data(ctx):
    #channel = ctx.channel  # コンテキストからチャンネルオブジェクトを取得
    await send_shard_info(ctx)
# チャンネルを選択するコマンド
# コマンドが呼ばれたら、選択肢を送信する処理
@client.command(name='select_channel')
async def select_channel(ctx):
    global message_command_mapping
    message = await ctx.send("Now Loading")
    await send_channel_selection_message(ctx,message)
    message_command_mapping[message.id] = 'select_channel'  # 追加
# リアクションが追加されたときに実行される処理
@client.event
async def on_reaction_add(reaction, user):
    global message_channel_mapping
    global message_content
    global page_channels,chunk_size,channels
    global emoji_list,num_pages
    global shard_notify_flag,channels_ID
    global shard_notify_channnel_id,send_selection_message_now,message_channel_mapping, message_command_mapping
    # 絵文字オブジェクトを取得
    # ボット自身のリアクションは無視する
    if user.bot:
        return
    # リアクションが追加されたメッセージの ID を取得
    message_id = reaction.message.id
    print(f"on_reaction_add:{reaction.emoji}")
    if message_id in message_command_mapping: 
        command = message_command_mapping[message_id] 
        #チャンネル選択画面の場合
        if command == 'send_channel_selection_message': 
            await handle_select_channel_reaction(reaction, user) 
        #オプション選択画面の場合
        elif command == 'send_selection_message': 
            #何もしない
            await handle_select_option_reaction(reaction, user) 
        elif command == 'shard_notify': 
            await handle_shard_notify_reaction(reaction, user) 
        elif command == 'shard_notify_confirmation': 
            await handle_shard_notify_confirmation_reaction(reaction, user) 
# select_channelコマンドのリアクション処理
async def handle_select_channel_reaction(reaction, user):
    message_id = reaction.message.id
    if message_id in message_channel_mapping:
        page_number = message_channel_mapping[message_id]
        max_page_number = len(channel_chunks) - 1
        #絵文字が1～10の場合
        if str(reaction.emoji) in emoji_list:
            index = emoji_list.index(str(reaction.emoji))
            channel_index = page_number * chunk_size + index
            selected_channel = channels[channel_index]
            print(f"{selected_channel.name} チャンネルが選択されました。")
            await remove_user_reaction(reaction, user)
            shard_notify_channnel_id = channels_ID[channel_index]
            print(f"on_selected_channel_id : {shard_notify_channnel_id}")
        #絵文字が右矢印の場合
        elif str(reaction.emoji) == '➡️' and page_number < max_page_number:
            page_number += 1
            message_channel_mapping[message_id] = page_number
            await update_message(page_number, reaction.message, channel_chunks, emoji_list)
            await remove_user_reaction(reaction, user)
        #絵文字が左矢印の場合
        elif str(reaction.emoji) == '⬅️' and page_number > 0:
            page_number -= 1
            message_channel_mapping[message_id] = page_number
            await update_message(page_number, reaction.message, channel_chunks, emoji_list)
            await remove_user_reaction(reaction, user)
async def handle_select_option_reaction(reaction, user):
    #何もしていない
    pass
async def handle_shard_notify_reaction(reaction, user):
    pass
async def handle_shard_notify_confirmation_reaction(reaction, user):
    pass
# 例として、コマンドを作成し、それを呼び出します
# コマンドが呼ばれたら、選択肢を送信する処理
@client.command(name='select')
async def select(ctx):
    await send_selection_message(ctx)
#シャードの通知を設定するコマンド
@client.command(name='shard_notify')
async def shard_notify(ctx):
    global shard_notify_flag,shard_notify_channnel_id,shard_notify_options_index
    global shard_notify_options,message_command_mapping,send_selection_message_now,send_channel_selection_message_now
    shard_notify_flag=True
    shard_notify_channnel_id=None
    shard_notify_options=None
    shard_notify_options_index=None
    all_emojis =[ "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟","⬅️","➡️"]
    options = ["デイリー更新時", "シャード開始時間", "シャード終了30分前", "決定"]
    # 選択画面のメッセージを作成
    select_message = await ctx.send("Now Loading")
    message_command_mapping[select_message.id] = 'shard_notify'
    await send_channel_selection_message(ctx, select_message)
    message_command_mapping[select_message.id] = 'shard_notify'  # 追加
    #shard_notify_channnel_idが入る
    #print(f"shard_notify_channnel_id: {shard_notify_channnel_id}")
    while shard_notify_channnel_id is None:
        await asyncio.sleep(1)  # 1秒待機して再試行する
    send_channel_selection_message_now=False
    #print("shard_notify_channnel_id is not None")
    #すべてのリアクション削除
    emojis =[ "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟","⬅️","➡️"]
    #emojisの絵文字リアクションから削除する
    await remove_bot_reactions(select_message, emojis)
    await send_selection_message(ctx, select_message)
    message_command_mapping[select_message.id] = 'shard_notify'
    send_selection_message_now=False
    #両方入力された場合
    if shard_notify_channnel_id and shard_notify_options_index is not None and shard_notify_options:
        emojis =[ "1️⃣", "2️⃣", "3️⃣", "4️⃣"]
        #emojisのbotの絵文字リアクションから削除する
        await remove_bot_reactions(select_message, emojis)
        # 選択されたチャンネルを取得
        channel = client.get_channel(shard_notify_channnel_id)
        # shard_notify_optionsのすべての要素を文字列として結合して出力
        options_str = ", ".join(shard_notify_options)
        # 確認画面の内容を構築
        confirmation_message = (
            f"以下の設定でシャード通知を行います。\n"
            f"チャンネル：{channel.name}\n"
            f"設定：{options_str}\n"
            f"以上の設定でよろしいですか？"
        )
        # 確認画面を送信
        await select_message.edit(content=confirmation_message)
        message_command_mapping[select_message.id] = 'shard_notify_confirmation'
        # YとNのリアクションを追加
        await select_message.add_reaction('🇾')  # Y
        await select_message.add_reaction('🇳')  # N
        
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ['🇾', '🇳']
        
        try:
            reaction, _ = await client.wait_for('reaction_add', timeout=60.0, check=check)
            if str(reaction.emoji) == '🇾':  # Yを選択した場合
                # 確認メッセージを削除
                await select_message.delete()
                # ユーザーがYを選択した場合の処理をここに記述
            else:  # Nを選択した場合
                await ctx.send("シャード通知の設定をキャンセルしました。")
                shard_notify_flag=False
                return
        except asyncio.TimeoutError:
            shard_notify_flag=False
            await ctx.send("タイムアウトしました。")
        
# 他の関数の中で呼び出され、選択肢を送信し、ユーザーの選択を待機する処理
async def send_selection_message(ctx,message):
    global emoji_list ,shard_notify_options_index,shard_notify_flag,shard_notify_options,send_selection_message_now
    send_selection_message_now=True
    # 選択肢のリスト
    options = ["デイリー更新時", "シャード開始時間", "シャード終了30分前", "決定"]
    message_command_mapping[message.id] = 'send_selection_message'
    # 選択肢を含むメッセージの作成
    message_content = "選択してください：\n"
    for index, option in enumerate(options):
        message_content += f"{emoji_list[index]}{option}\n"

    # メッセージを編集
    await message.edit(content=message_content)
    message_command_mapping[message.id] = 'send_selection_message'
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
        return user == ctx.author and str(reaction.emoji) in emoji_list[:len(options)]

    try:
        while True:
            reaction, user = await client.wait_for('reaction_add', timeout=600.0, check=check)
            
            # ユーザーの選択を取得
            selected_option_index = emoji_list.index(str(reaction.emoji))
            selected_option = options[selected_option_index]

            # 「決定」が選択された場合
            if selected_option == "決定":
                if selected_options:
                    if shard_notify_flag==True:
                        shard_notify_options_index=selected_option_index
                        shard_notify_options=selected_options
                    #await ctx.send(f"選択されたオプション：{', '.join(selected_options)}")
                #else:
                    #await ctx.send("何も選択されていません。")
                break
            else:
                if selected_option in selected_options:
                    selected_options.remove(selected_option)
                else:
                    selected_options.add(selected_option)
                #await ctx.send(f"現在の選択：{', '.join(selected_options) if selected_options else 'なし'}")

    except asyncio.TimeoutError:
        await ctx.send("タイムアウトしました。")
#ボットが追加したリアクションをすべて削除する
async def remove_non_listed_bot_reactions(message):
    for reaction in message.reactions:
        async for user in reaction.users():
            await reaction.remove(user)
# 他の関数の中で呼び出され、指定されたページのチャンネルリストを表示する処理
async def send_channel_selection_message(ctx,message=None):
    global message_channel_mapping 
    global message_content
    global page_channels, chunk_size, channels
    global emoji_list, num_pages
    global channel_chunks,channels_ID
    global shard_notify_channnel_id,send_channel_selection_message_now
    send_channel_selection_message_now=True
    print("send_channel_selection_messageが呼ばれました")
    message_command_mapping[message.id] = 'send_channel_selection_message'
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

    # メッセージを送信してリアクションをつける
    emoji_list = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    if message is None:
        message_content = f"**Page {current_page + 1}/{num_pages}**\n\n"
        for index, channel in enumerate(channel_chunks[current_page]):
            message_content += f"{emoji_list[index]} {channel.name}\n" 
        message = await ctx.send(message_content)
    else:
        # メッセージを編集
        message_content = f"**Page {current_page + 1}/{num_pages}**\n\n"
        for index, channel in enumerate(channel_chunks[current_page]):
            message_content += f"{emoji_list[index]} {channel.name}\n" 
        await message.edit(content=message_content)
    message_command_mapping[message.id] = 'send_channel_selection_message'
    # リアクションを追加
    for emoji in emoji_list[:min(len(channel_chunks[current_page]), len(emoji_list))]:
        await message.add_reaction(emoji)
    # ページが最初のページでない場合は、前のページへのリアクションを追加
    if current_page > 0:
        await message.add_reaction('⬅️')
    # ページが最後のページでない場合は、次のページへのリアクションを追加
    if current_page < num_pages - 1:
        await message.add_reaction('➡️')

    # メッセージとページのマッピングを保存
    message_channel_mapping[message.id] = current_page
# ページを更新する関数
async def update_message(page, message, channel_chunks, emoji_list):
    #print(f"ページ {page} のメッセージを更新しています")
    temp_content = message.content
    message_content = f"**Page {page + 1}/{len(channel_chunks)}**\n\n"
    for index, channel in enumerate(channel_chunks[page]):
        message_content += f"{emoji_list[index]} {channel.name}\n"
        #print(f"Channel name: {channel.name}")  # チャンネル名を出力
    #print(f"更新後のメッセージ内容: {message_content}")
    #print(f"変更前のメッセージ内容: {temp_content}")  # 変更前のメッセージ内容を出力
    await message.edit(content=message_content)
    # 左向きの矢印リアクションを追加
    if page > 0:
        if '⬅️' not in [reaction.emoji for reaction in message.reactions]:
            await message.add_reaction('⬅️')
            #print("左追加")
    else:
        # ページが最初の場合は左向きの矢印リアクションを削除
        await message.clear_reaction('⬅️')
        #print("左削除")
    # 右向きの矢印リアクションを追加
    if page < len(channel_chunks) - 1:
        if '➡️' not in [reaction.emoji for reaction in message.reactions]:
            await message.add_reaction('➡️')
            #print("右追加")
    else:
        # ページが最後の場合は右向きの矢印リアクションを削除
        await message.clear_reaction('➡️')
        #print("右削除")
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