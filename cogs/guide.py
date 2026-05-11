import discord
from discord.ext import commands

class Guide(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 各チャンネルごとの「最後に送ったメッセージID」を保存する辞書
        self.guide_messages = {} 

        # --- ⚙️ ここに設定を自由に追加してください ---
        self.CHANNELS_CONFIG = {
            1497015992927129670: {  # チャンネルID その1（コインガチャ用）
                "title": "💰 コイン確認の使い方",
                "description": "\n**「コイン確認」と打つだけ※「」不要**",
                "color": 0xF1C32C
            },
            1496409485563003011: {  # チャンネルID その2（チケット用）
                "title": "🃏 チケット確認の使い方",
                "description": "\n**「チケット確認」※「」不要**",
                "color": 0xE74C3C
            },
            1502449092436037702: {  # チャンネルID その3（ランキング用）
                "title": "🏆 ランキング確認の使い方 ※「」不要",
                "description": (
                    "チャット欄に以下の言葉を打つと、それぞれのランキングを表示します！\n\n"
                    "**🏅 「ランキング」**\n"
                    "└ 全ての情報をまとめて表示」\n\n"
                    "**💰 「コインランキング」**\n"
                    "└ 所持コインが多い順\n\n"
                    "**🎟️ 「チケットランキング」**\n"
                    "└ 所持チケットが多い順\n\n"
                    "**💸 「消費ランキング」**\n"
                    "└ 今週もっともコインを使ったTOP5\n\n"
                    "**👑 「月間ランキング」**\n"
                    "└ 今月もっともコインを使ったTOP5"
                ),
                "color": 0x9B59B6 # 豪華な紫色に変更してみました
            },
            1502492777324347562: {  # チャンネルID その4（ランク確認用）
                "title": "🛡️ ランク確認の使い方",
                "description": "\n**「ランク確認」※「」不要**",
                "color": 0xE74C3C
            },
            # 3つ目、4つ目も同じように増やせます
        }

    @commands.Cog.listener()
    async def on_message(self, message):
        # ボット自身の発言、または設定していないチャンネルは無視
        if message.author.bot or message.channel.id not in self.CHANNELS_CONFIG:
            return

        config = self.CHANNELS_CONFIG[message.channel.id]

        # 1. そのチャンネルの「前のガイド」があれば削除
        old_msg_id = self.guide_messages.get(message.channel.id)
        if old_msg_id:
            try:
                old_msg = await message.channel.fetch_message(old_msg_id)
                await old_msg.delete()
            except:
                pass

        # 2. 新しいガイドを送信
        embed = discord.Embed(
            title=config["title"],
            description=config["description"],
            color=config["color"]
        )
        
        new_msg = await message.channel.send(embed=embed)
        # メッセージIDを保存
        self.guide_messages[message.channel.id] = new_msg.id

async def setup(bot):
    await bot.add_cog(Guide(bot))