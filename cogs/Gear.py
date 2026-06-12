import discord
from discord.ext import commands
from groq import Groq
import collections

class Gear(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 注意: APIキーは環境変数等で管理するのが最も安全です
        self.client = Groq(api_key="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")
        self.model_name = "llama-3.3-70b-versatile"
        # 各ユーザー最大15往復（30メッセージ）まで履歴を保持
        self.history = collections.defaultdict(list)
        self.target_channel_id = 1511550050805747803

    def get_system_prompt(self):
        return {"role": "system", "content": "あなたは「ぎあ」という名前のDiscord Botです。親しみやすく、可愛い口調で話してください。"}

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user: return
        if not (self.bot.user.mentioned_in(message) or message.channel.id == self.target_channel_id):
            return

        user_text = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
        if not user_text: return
        
        await self.chat_with_groq(message, user_text)

    async def chat_with_groq(self, message, user_text):
        user_id = message.author.id
        
        # 履歴が存在しない場合の初期化
        if not self.history[user_id]:
            self.history[user_id].append(self.get_system_prompt())
        
        # ユーザー入力を履歴に追加
        self.history[user_id].append({"role": "user", "content": user_text})
        
        # 履歴制限 (システムプロンプトを除いて最新10メッセージに絞る)
        if len(self.history[user_id]) > 11:
            self.history[user_id] = [self.history[user_id][0]] + self.history[user_id][-10:]

        async with message.channel.typing():
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=self.history[user_id]
                )
                
                reply_text = response.choices[0].message.content
                
                # AIの回答を履歴に追加
                self.history[user_id].append({"role": "assistant", "content": reply_text})
                await message.reply(reply_text)
                
            except Exception as e:
                print(f"Groq Error: {e}")
                # 履歴が壊れている可能性を考慮して履歴をクリアする対策
                if "invalid" in str(e).lower():
                    self.history[user_id] = []
                await message.reply("💦 ちょっと考えすぎて疲れちゃった…もう一度話しかけてくれる？")

async def setup(bot):
    await bot.add_cog(Gear(bot))